"""Pipeline 核心命令：run / prepare / transcribe / clean / segment / align / export / resume / retry / demo / cleanup."""

from __future__ import annotations

import json
import logging
import os
import signal
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from subtap.cli._utils import _handle_error
from subtap.metrics.profiler import PipelineProfiler
from subtap.core.user_resources import default_glossary_path
from subtap.schemas.task_request import SubtitleTaskRequest

REMOTE_ASR_BACKENDS = {"http-asr"}
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from subtap.core.pipeline import Pipeline
    from subtap.metrics.run_log import RunLog
    from subtap.schemas.config import SubtapConfig


def _process_group_exists(process_group: int) -> bool:
    """Return whether the observer child process group still exists."""
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    return True


def _stop_observer_child(process: subprocess.Popen) -> None:
    """Stop the pipeline child and every process it started."""
    process_group = process.pid
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    if _process_group_exists(process_group):
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            return
    if process.poll() is None:
        process.wait(timeout=5)


def check_first_run_wizard(config) -> bool:
    """检查并执行首次运行向导。

    当检测到 API 配置存在但 llm_proofread 未设置时，提示用户是否开启 AI 校对和热词功能。

    Returns:
        bool: 是否执行了向导
    """
    # 检查条件：API 配置存在且 llm_proofread 未设置
    remote_api = getattr(config, "remote_api", None)
    if remote_api is None:
        return False

    if not getattr(remote_api, "base_url", ""):
        return False

    # 检查环境变量是否存在
    api_key_env = getattr(remote_api, "api_key_env", "")
    if not api_key_env or not os.environ.get(api_key_env):
        return False

    if getattr(config, "llm_proofread", None) is not None:
        return False

    # 执行向导
    typer.echo("\n检测到 API 配置，但未设置 AI 校对选项。")

    response = input("是否开启 AI 校对功能？(Y/n): ").strip().lower()
    config.llm_proofread = response in ("y", "yes", "")

    response = input("是否开启 AI 热词功能？(Y/n): ").strip().lower()
    config.llm_hotword = response in ("y", "yes", "")

    return True


def _apply_cli_overrides(
    config,
    llm_proofread: bool | None = None,
    llm_hotword: bool | None = None,
) -> None:
    """将 CLI 独立配置项写入 config，供 clean 阶段读取。"""
    if llm_proofread is not None:
        config.llm_proofread = llm_proofread
    if llm_hotword is not None:
        config.llm_hotword = llm_hotword


# ── Run 命令 ───────────────────────────────────────────────


def _count_jsonl(path: Path) -> int:
    """统计 JSONL 文件行数。"""
    if not path.is_file():
        raise FileNotFoundError(f"Required pipeline artifact not found: {path}")
    count = 0
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}:{line_number}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        count += 1
    if count == 0:
        raise ValueError(f"Required pipeline artifact is empty: {path}")
    return count


def _generate_metrics(
    config: "SubtapConfig",
    timings: dict,
    work_dir: Path,
    output_dir: Path,
    enhance: str,
    event_log_path: Path,
) -> None:
    """生成性能指标并写入文件。"""
    if not config.output.generate_metrics:
        return

    from subtap.metrics.performance import (
        build_subtitle_performance_metrics,
        load_pipeline_measurements,
    )

    asr_config = getattr(config, "asr", None)
    align_config = getattr(config, "align", None)
    measurements = load_pipeline_measurements(
        work_dir / "media_info.json",
        work_dir / "run_meta.json",
        event_log_path,
    )
    performance_metrics = build_subtitle_performance_metrics(
        timings=timings,
        total_runtime_sec=measurements["total_runtime_sec"],
        audio_duration_sec=measurements["audio_duration_sec"],
        chunks_total=_count_jsonl(work_dir / "chunks" / "chunks.jsonl"),
        subtitles_total=_count_jsonl(work_dir / "aligned.jsonl"),
        alignment_enabled=True,
        asr_model=getattr(asr_config, "model", "asr_0.6b"),
        aligner_model=getattr(align_config, "model", "aligner"),
        quantization=getattr(asr_config, "quantization", "q8"),
        enhance_mode=enhance,
        asr_model_load_time_sec=measurements["asr_model_load_time_sec"],
        aligner_model_load_time_sec=measurements["aligner_model_load_time_sec"],
        keep_model_alive=bool(
            getattr(asr_config, "keep_model_alive", False)
            or getattr(align_config, "keep_model_alive", False)
        ),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_payload = performance_metrics | {"output_contract": "final"}
    metrics_path = work_dir / config.metrics.output_path
    metrics_path.write_text(
        json.dumps(metrics_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _execute_pipeline(
    pipeline: "Pipeline",
    input_path: Path,
    output_dir: Path,
    fmt: str,
    enhance: str,
    translate_to: str | None,
    bilingual: str,
    json_output: bool,
    run_log: "RunLog",
) -> dict:
    """执行 pipeline 并返回 timings。"""
    from subtap.ui.tui import RichRunner

    runner = RichRunner()
    timings = {}
    import time

    _run_start = time.monotonic()
    try:
        if json_output:
            with redirect_stdout(StringIO()):
                result = runner.run_pipeline(
                    pipeline,
                    input_path,
                    output_dir,
                    fmt=fmt,
                    enhance=enhance,
                    translate_to=translate_to,
                    bilingual=bilingual,
                )
        else:
            result = runner.run_pipeline(
                pipeline,
                input_path,
                output_dir,
                fmt=fmt,
                enhance=enhance,
                translate_to=translate_to,
                bilingual=bilingual,
            )
        timings = result.get("timings", {})
        _run_elapsed = time.monotonic() - _run_start
        for _stage_name, _stage_dur in timings.items():
            run_log.stage(_stage_name, "success", duration_sec=_stage_dur)
        _output_stem = input_path.stem
        run_log.finalize(
            True,
            total_duration_sec=_run_elapsed,
            output_path=str(output_dir / f"{_output_stem}.{fmt}"),
        )
    except SystemExit:
        raise
    except Exception as e:
        _run_elapsed = time.monotonic() - _run_start
        import traceback

        run_log.finalize(
            False,
            total_duration_sec=_run_elapsed,
            error=traceback.format_exc(),
        )
        _handle_error(f"处理失败：{e}")

    return timings


def _apply_run_config(
    config: "SubtapConfig",
    request: SubtitleTaskRequest,
    timestamp: bool | None,
    punctuation: bool | None,
    max_chars: int | None,
    min_chars: int | None,
    script_mode: str,
    hotwords: str | None,
    work_dir: Path | None,
) -> Path:
    """应用 CLI 参数到配置，返回 work_dir。"""
    if timestamp is not None:
        config.output.timestamp = timestamp
    if punctuation is not None:
        config.output.subtitle_punctuation = punctuation
    if request.subtitle_language is not None:
        config.output.subtitle_language = request.subtitle_language
    if max_chars is not None or min_chars is not None:
        from subtap.schemas.config import with_output_character_limits

        config.output = with_output_character_limits(
            config.output, max_chars=max_chars, min_chars=min_chars
        )
    config.output.subtitle_stem = request.input_path.stem

    if request.disable_script:
        config.output.script_path = None
    elif request.script_path is not None:
        config.output.script_path = str(request.script_path)
        config.output.script_mode = script_mode

    config.asr.model = "asr_1.7b" if request.mode == "quality" else "asr_0.6b"

    if request.reset_hotwords:
        config.asr.hotwords = []
    elif hotwords:
        config.asr.hotwords = [w.strip() for w in hotwords.split(",") if w.strip()]
    glossary_path = request.resolved_glossary_path()
    if glossary_path is not None:
        config.clean.glossary_path = str(glossary_path)

    if work_dir is None:
        work_dir = Path(config.workspace.root)

    return work_dir


def _validate_run_params(
    enhance: str,
    local_only: bool,
    translate_to: str | None,
    bilingual: str,
    asr_backend: str = "mlx-qwen-asr",
) -> None:
    """验证 run 命令参数。"""
    if enhance not in ("local", "api"):
        _handle_error(f"错误：--enhance 必须是 local/api，收到：{enhance}")

    if local_only and asr_backend in REMOTE_ASR_BACKENDS:
        _handle_error(
            f"错误：--local-only 模式下不能使用会外发音频的 ASR 后端：{asr_backend}"
        )

    if local_only and enhance == "api":
        _handle_error("错误：--local-only 模式下不能使用 --enhance api")

    if local_only and translate_to:
        _handle_error("错误：--local-only 模式下不能使用 --translate-to")

    if bilingual not in ("off", "source-first", "target-first"):
        _handle_error(
            f"错误：--bilingual 必须是 off/source-first/target-first，收到：{bilingual}"
        )

    if bilingual != "off" and not translate_to:
        _handle_error("错误：--bilingual 需要同时使用 --translate-to")


def _warn_external_api_use(
    enhance: str, translate_to: str | None, asr_backend: str = "mlx-qwen-asr"
) -> None:
    """Warn before any stage can send data to an external API."""
    if asr_backend in REMOTE_ASR_BACKENDS:
        typer.echo("⚠ 将使用外部 ASR API 处理音频。", err=True)
    if enhance == "api" or translate_to:
        typer.echo("⚠ 将使用外部 LLM API 处理字幕文本。", err=True)


def _run(
    input_path: Path = typer.Argument(
        ..., help="输入媒体文件路径（支持 mp3/mp4/wav/mkv 等）"
    ),
    work_dir: Path | None = typer.Option(
        None, "-w", "--work-dir", help="工作目录（默认读取配置文件）"
    ),
    output_dir: Path = typer.Option(
        Path("./output"), "-o", "--output-dir", help="输出目录"
    ),
    fmt: str = typer.Option(
        "srt",
        "--format",
        "-f",
        help="输出清单标记：srt / vtt / json / tsv；精对齐默认生成 final.srt/final.vtt/final.json/final.tsv",
    ),
    mode: str = typer.Option("fast", "--mode", "-m", help="执行模式：fast / quality"),
    enhance: str = typer.Option(
        "local",
        "--enhance",
        "-e",
        help="字幕增强模式：local（默认）/ api（需配置 API Key）",
    ),
    local_only: bool = typer.Option(
        False, "--local-only", help="仅本地运行，禁止所有外部 API 调用"
    ),
    translate_to: str | None = typer.Option(
        None, "--translate-to", help="翻译目标语言：en / ja / zh"
    ),
    bilingual: str = typer.Option(
        "off",
        "--bilingual",
        help="双语字幕顺序：off / source-first / target-first",
    ),
    punctuation: bool | None = typer.Option(
        None, "--punctuation", help="字幕带标点符号（默认读取配置文件）"
    ),
    subtitle_language: str | None = typer.Option(
        None, "--subtitle-language", help="字幕输出语种（zh/en/ja），默认读取配置文件"
    ),
    max_chars: int | None = typer.Option(
        None,
        "--max-chars",
        help="每行字幕最大字符数（10-60），默认读取配置文件",
        min=10,
        max=60,
    ),
    min_chars: int | None = typer.Option(
        None,
        "--min-chars",
        help="每行字幕最小字符数（4-30），默认读取配置文件",
        min=4,
        max=30,
    ),
    no_git_check: bool = typer.Option(
        False, "--no-git-check", help="跳过 Git 状态检查"
    ),
    no_cleanroom: bool = typer.Option(
        False, "--no-cleanroom", help="跳过工作环境卫生检查"
    ),
    timestamp: bool | None = typer.Option(
        None,
        "--timestamp/--no-timestamp",
        help="输出目录是否带时间戳（默认读取配置文件）",
    ),
    script: str | None = typer.Option(None, "--script", help="文稿文件路径（可选）"),
    script_mode: str = typer.Option(
        "follow_script",
        "--script-mode",
        help="文稿匹配模式：follow_script / correct_only",
    ),
    json_output: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
    llm_proofread: bool | None = typer.Option(
        None,
        "--llm-proofread/--no-llm-proofread",
        help="启用/禁用 LLM 校对（默认根据配置自动判断）",
    ),
    llm_hotword: bool | None = typer.Option(
        None,
        "--llm-hotword/--no-llm-hotword",
        help="启用/禁用 LLM 热词（默认根据配置自动判断）",
    ),
    hotwords: str | None = typer.Option(
        None,
        "--hotwords",
        help="ASR 热词列表，逗号分隔（如：瑞幸,CapCut,TikTok）",
    ),
    glossary: Path | None = typer.Option(
        None, "--glossary", help="本次任务使用的热词表路径"
    ),
    default_glossary: bool = typer.Option(
        False, "--default-glossary", help="本次任务使用默认热词表"
    ),
    no_script: bool = typer.Option(False, "--no-script", help="本次任务不使用参考文稿"),
    reset_hotwords: bool = typer.Option(
        False, "--reset-hotwords", hidden=True, help="内部参数：清除配置中的额外热词"
    ),
    tui: bool = typer.Option(False, "--tui", help="使用 TUI 观察者运行"),
    observer_child: bool = typer.Option(
        False, "--observer-child", hidden=True, help="内部参数：观察者子进程"
    ),
    no_tui: bool = typer.Option(
        False, "--no-tui", hidden=True, help="内部参数：禁用 TUI 父进程"
    ),
) -> None:
    """运行完整字幕生成流程

    [bold]流程：[/bold] 音频标准化 → 切段 → 语音识别 → 文本清洗 → 智能断句 → 时间轴对齐 → 字幕导出

    [bold]模式：[/bold]
      fast     — 快速模式，使用 0.6B 模型（默认）
      quality  — 高质量模式，使用 1.7B 模型

    [bold]增强：[/bold]
      local    — 本地规则增强（默认，始终执行）
      api      — LLM API 增强（需配置 API Key）

    [bold]输出：[/bold] final.srt / final.vtt / final.json / final.tsv

    [bold]示例：[/bold]
      subtap run video.mp3
      subtap run video.mp3 --enhance api
      subtap run video.mp3 --translate-to en
      subtap run input.mp3 --mode quality -o ./subtitles
    """
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if reset_hotwords and hotwords:
        _handle_error("错误：不能同时使用 --reset-hotwords 和 --hotwords")
    request = SubtitleTaskRequest(
        input_path=input_path,
        output_dir=output_dir.expanduser(),
        mode=mode,
        glossary_path=glossary,
        use_default_glossary=default_glossary,
        script_path=Path(script) if script else None,
        disable_script=no_script,
        reset_hotwords=reset_hotwords,
        subtitle_format=fmt,
        subtitle_language=subtitle_language,
        show_observer=tui,
    )
    try:
        request.validate()
    except ValueError as error:
        _handle_error(f"错误：{error}")
    output_dir = request.output_dir
    fmt = request.subtitle_format
    tui = request.show_observer

    # ── 加载配置并应用回退 ───────────────────────────────────
    config = load_config(Path.home() / ".subtap" / "config.yaml")
    check_first_run_wizard(config)

    # Config mode → local_only merge (config sets baseline, CLI can override)
    if getattr(config, "mode", "online") == "offline" and not local_only:
        local_only = True

    # translate_to: CLI overrides config; if CLI not provided, fall back to config
    if translate_to is None and getattr(config, "translate_to", ""):  # type: ignore[arg-type]
        translate_to = config.translate_to

    asr_backend = getattr(getattr(config, "asr", None), "backend", "mlx-qwen-asr")
    _validate_run_params(enhance, local_only, translate_to, bilingual, asr_backend)
    _warn_external_api_use(enhance, translate_to, asr_backend)

    work_dir = _apply_run_config(
        config,
        request,
        timestamp,
        punctuation,
        max_chars,
        min_chars,
        script_mode,
        hotwords,
        work_dir,
    )

    if tui and not observer_child and not no_tui:
        from subtap.cli import _build_observer_child_command

        process = subprocess.Popen(
            _build_observer_child_command(sys.argv),
            start_new_session=True,
        )
        from subtap.ui.observer import _make_observer_dashboard

        output_path = output_dir / f"{input_path.stem}.{fmt}"
        result = _make_observer_dashboard(
            work_dir / "run.log.jsonl",
            process,
            output_path=output_path,
        ).run()
        if result == "interrupt":
            _stop_observer_child(process)
            typer.echo("已中断子进程。")
            raise typer.Exit(130)
        elif result == "quit" and process.poll() is None:
            typer.echo("已退出观察，子进程继续运行。")
        returncode = process.poll()
        if returncode not in (None, 0):
            typer.echo(f"观察者子进程失败：退出码 {returncode}", err=True)
            raise typer.Exit(returncode if returncode is not None else 1)
        if returncode == 0 and not output_path.is_file():
            typer.echo(f"任务异常：未找到字幕文件：{output_path}", err=True)
            raise typer.Exit(1)
        return

    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    # ── Run Log ────────────────────────────────────────────
    from subtap.metrics.run_log import RunLog

    from datetime import datetime

    run_log = RunLog(work_dir=work_dir)
    run_log._start_time = datetime.now().astimezone()
    run_log.system()
    run_log.input(
        path=input_path,
        size_bytes=input_path.stat().st_size if input_path.exists() else 0,
        format=input_path.suffix.lstrip("."),
    )
    asr_cfg = getattr(config, "asr", None)
    align_cfg = getattr(config, "align", None)
    run_log.config_snapshot(
        {
            "mode": mode,
            "enhance": enhance,
            "asr_model": getattr(asr_cfg, "model", "asr_0.6b"),
            "aligner_model": getattr(align_cfg, "model", "aligner"),
            "quantization": getattr(asr_cfg, "quantization", "q8"),
            "translate_to": translate_to or "",
            "bilingual": bilingual,
            "script": script or "",
            "llm_proofread": getattr(config, "llm_proofread", None),
            "llm_hotword": getattr(config, "llm_hotword", False),
        }
    )

    # Record hotword glossary info
    _hw_path = (
        Path(config.clean.glossary_path)
        if config.clean.glossary_path
        else default_glossary_path()
    )
    if _hw_path.exists():
        try:
            from subtap.glossary.hotword import load_glossary

            _hw_g = load_glossary(_hw_path, "zh")
            run_log.hotwords(path=_hw_path, count=len(_hw_g.hotwords), loaded=True)
        except Exception:
            logger.exception("热词表加载失败：%s", _hw_path)
            run_log.hotwords(path=_hw_path, loaded=False)
    else:
        run_log.hotwords(loaded=False)

    # ── Pre-flight checks ──────────────────────────────────
    # Cleanroom check
    if not no_cleanroom:
        from subtap.engine.cleanroom import Cleanroom

        cleanroom = Cleanroom(work_dir)
        cr_result = cleanroom.check_workspace()
        if not cr_result["is_clean"]:
            typer.echo("▸ 工作环境卫生检查...")
            for issue in cr_result["issues"]:
                typer.echo(f"  ⚠ {issue}")
            clean_report = cleanroom.clean_workspace()
            typer.echo(f"  ✓ 已清理 {clean_report['cleaned_count']} 项")

    # Git guard check
    if not no_git_check:
        from subtap.engine.git_guard import GitGuard

        git_guard = GitGuard(work_dir)
        if git_guard.is_git_repo():
            gg_result = git_guard.pre_task_check()
            if not gg_result["ok"]:
                typer.echo("▸ Git 状态检查...")
                for issue in gg_result["issues"]:
                    typer.echo(f"  ⚠ {issue}")
                # Auto-commit dirty state
                commit_result = git_guard.auto_commit_if_needed()
                if commit_result["committed"]:
                    typer.echo(f"  ✓ 已自动提交: {commit_result['commit_hash']}")

    # ── Pipeline execution ──────────────────────────────────
    from subtap.metrics.events import EventBus

    # 创建 Event Bus 和 Profiler
    # 支持 SUBTAP_EVENT_LOG 环境变量指定日志路径（TUI 进度渲染用）
    _env_log = os.environ.get("SUBTAP_EVENT_LOG")
    event_log_path = Path(_env_log) if _env_log else work_dir / "run.log.jsonl"
    # truncate 而非 unlink，避免 inode 变化导致渲染线程丢失事件
    if event_log_path.exists():
        with event_log_path.open("w"):
            pass
    event_bus = EventBus(log_path=event_log_path)
    pipeline.event_bus = event_bus
    profiler = PipelineProfiler(event_bus)
    profiler.wrap_pipeline(pipeline)

    _apply_cli_overrides(config, llm_proofread, llm_hotword)

    timings = _execute_pipeline(
        pipeline,
        input_path,
        output_dir,
        fmt,
        enhance,
        translate_to,
        bilingual,
        json_output,
        run_log,
    )
    pipeline.cleanup()

    _generate_metrics(
        config,
        timings,
        work_dir,
        output_dir,
        enhance,
        event_log_path,
    )

    if json_output:
        output_path = output_dir / "final.srt"
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "input_path": str(input_path),
                    "work_dir": str(work_dir),
                    "output_dir": str(output_dir),
                    "output_path": str(output_path),
                    "alignment_enabled": True,
                    "timings": timings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


# ── 单阶段命令 ─────────────────────────────────────────────


def _prepare(
    input_path: Path = typer.Argument(..., help="输入媒体文件路径"),
    output: Path = typer.Option(Path("./work"), "-o", "--output", help="工作目录"),
) -> None:
    """提取音频并切段（单阶段执行）"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not input_path.exists():
        _handle_error(f"文件未找到：{input_path}")

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=output)

    typer.echo("▸ 音频标准化...")
    result = pipeline.run_stage("prepare", input_path=input_path)
    typer.echo(
        f"  ✓ {result['media_info']['duration']:.1f}s, {result['media_info']['sample_rate']}Hz"
    )

    typer.echo("▸ 音频切段...")
    result = pipeline.run_stage("chunk")
    typer.echo(f"  ✓ {result['chunk_count']} 段 → {result['chunks_jsonl']}")

    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


def _transcribe(
    audio_path: Path = typer.Argument(..., help="音频文件路径"),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    backend: str | None = typer.Option(None, "-b", "--backend", help="ASR 后端覆盖"),
) -> None:
    """语音识别（单阶段执行）"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not audio_path.exists():
        _handle_error(f"文件未找到：{audio_path}")

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    typer.echo(f"▸ 语音识别（{backend or config.asr.backend}）...")
    try:
        result = pipeline.run_stage("asr", backend_name=backend)
    except (ImportError, NotImplementedError) as e:
        _handle_error(f"错误：{e}")

    typer.echo(f"  ✓ {result['segment_count']} 条 → {result['asr_jsonl']}")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


def _clean(
    asr_path: Path = typer.Argument(..., help="asr.jsonl 路径"),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    llm: str | None = typer.Option(
        None, "--llm", help="LLM 后端（如 openai:gpt-4o-mini）"
    ),
    glossary: Path | None = typer.Option(None, "--glossary", help="术语表 YAML 路径"),
    output: Path | None = typer.Option(
        None, "-o", "--output", help="输出 cleaned.jsonl 路径"
    ),
) -> None:
    """文本清洗：术语替换 + LLM 纠错（单阶段执行）"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not asr_path.exists():
        _handle_error(f"文件未找到：{asr_path}")

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    if asr_path.resolve() != pipeline.workspace.asr_jsonl.resolve():
        shutil.copy2(asr_path, pipeline.workspace.asr_jsonl)

    typer.echo(f"▸ 文本清洗（{llm or config.clean.backend}）...")
    try:
        result = pipeline.run_stage(
            "clean", llm_backend=llm, glossary_path=str(glossary) if glossary else None
        )
    except ValueError as e:
        _handle_error(f"错误：{e}")

    cleaned_path = Path(result["cleaned_jsonl"])
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        if cleaned_path.resolve() != output.resolve():
            shutil.copy2(cleaned_path, output)
        cleaned_path = output

    typer.echo(f"  ✓ {result['segment_count']} 条 → {cleaned_path}")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


def _segment(
    cleaned_path: Path = typer.Argument(..., help="cleaned.jsonl 路径"),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    output: Path | None = typer.Option(
        None, "-o", "--output", help="输出 sentences.jsonl 路径"
    ),
) -> None:
    """智能断句（单阶段执行）"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not cleaned_path.exists():
        _handle_error(f"文件未找到：{cleaned_path}")

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    if cleaned_path.resolve() != pipeline.workspace.cleaned_jsonl.resolve():
        shutil.copy2(cleaned_path, pipeline.workspace.cleaned_jsonl)

    typer.echo("▸ 智能断句...")
    try:
        result = pipeline.run_stage("segment")
    except ValueError as e:
        _handle_error(f"错误：{e}")

    sentences_path = Path(result["sentences_jsonl"])
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        if sentences_path.resolve() != output.resolve():
            shutil.copy2(sentences_path, output)
        sentences_path = output

    typer.echo(f"  ✓ {result['sentence_count']} 句 → {sentences_path}")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


def _align(
    sentences_path: Path = typer.Argument(..., help="sentences.jsonl 路径"),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    backend: str | None = typer.Option(None, "-b", "--backend", help="对齐后端覆盖"),
    output: Path | None = typer.Option(
        None, "-o", "--output", help="输出 aligned.jsonl 路径"
    ),
) -> None:
    """时间轴对齐（单阶段执行）"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not sentences_path.exists():
        _handle_error(f"文件未找到：{sentences_path}")

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    if sentences_path.resolve() != pipeline.workspace.sentences_jsonl.resolve():
        shutil.copy2(sentences_path, pipeline.workspace.sentences_jsonl)

    typer.echo(f"▸ 时间轴对齐（{backend or config.align.backend}）...")
    try:
        result = pipeline.run_stage("align", backend_name=backend)
    except (ImportError, ValueError) as e:
        _handle_error(f"错误：{e}")

    aligned_path = Path(result["aligned_jsonl"])
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        if aligned_path.resolve() != output.resolve():
            shutil.copy2(aligned_path, output)
        aligned_path = output

    typer.echo(f"  ✓ {result['aligned_count']} 条 → {aligned_path}")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


def _export(
    aligned_path: Path = typer.Argument(..., help="aligned.jsonl 路径"),
    output_dir: Path = typer.Option(
        Path("./output"), "-o", "--output-dir", help="输出目录"
    ),
    fmt: str = typer.Option("srt", "--format", "-f", help="导出格式：srt / ass / txt"),
    stem: str = typer.Option("output", "--stem", help="输出文件名前缀"),
) -> None:
    """导出字幕文件（单阶段执行）"""
    from subtap.core.export import run_export

    if not aligned_path.exists():
        _handle_error(f"文件未找到：{aligned_path}")

    typer.echo(f"▸ 字幕导出（{fmt.upper()}）...")
    try:
        result = run_export(aligned_path, output_dir, fmt=fmt, stem=stem)
    except ValueError as e:
        _handle_error(f"错误：{e}")

    typer.echo(f"  ✓ {result['output_path']}（{result['segment_count']} 条）")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


# ── Resume / Retry 命令 ────────────────────────────────────


def _resume(
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    input_path: Path = typer.Argument(..., help="输入媒体文件路径"),
    output_dir: Path = typer.Option(
        Path("./output"), "-o", "--output-dir", help="输出目录"
    ),
    fmt: str = typer.Option("srt", "--format", "-f", help="导出格式"),
) -> None:
    """从中断点恢复执行（跳过已完成的阶段）"""
    from subtap.schemas.config import load_config
    from subtap.engine.controller import PipelineController

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    ctrl = PipelineController(config, work_dir)

    typer.echo("▸ 恢复执行...")
    try:
        result = ctrl.resume_pipeline(input_path, output_dir, fmt=fmt)
        if result:
            typer.echo(f"  ✓ 总耗时：{result.get('total_time_sec', 0):.1f}s")
    except Exception as e:
        _handle_error(f"恢复失败：{e}")


def _retry(
    stage_name: str = typer.Argument(
        ..., help="要重试的阶段名称（asr/align/export 等）"
    ),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
) -> None:
    """重试失败的阶段"""
    from subtap.schemas.config import load_config
    from subtap.engine.controller import PipelineController

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    ctrl = PipelineController(config, work_dir)

    typer.echo(f"▸ 重试 {stage_name}...")
    try:
        ctrl.retry_stage(stage_name)
        typer.echo(f"  ✓ {stage_name} 重试成功")
    except ValueError as e:
        _handle_error(str(e))
    except Exception as e:
        _handle_error(f"重试失败：{e}")


# ── Demo 命令 ──────────────────────────────────────────────


def _demo(
    output_dir: Path = typer.Option(
        Path("./demo_output"), "-o", "--output-dir", help="输出目录"
    ),
    skip_tui: bool = typer.Option(False, "--skip-tui", help="跳过 TUI 展示"),
) -> None:
    """运行演示：使用内置测试音频展示完整流程

    自动查找项目内置测试音频，默认本地运行，不调用 LLM API，并输出 final.srt。
    """
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    # 查找内置测试音频
    samples_dir = Path(__file__).resolve().parents[3] / "samples"
    test_files = list(samples_dir.glob("*.mp3")) + list(samples_dir.glob("*.wav"))

    if not test_files:
        _handle_error(f"未找到内置测试音频，请将测试音频放入：{samples_dir}")

    input_file = test_files[0]
    typer.echo("═══ Subtap 演示 ═══")
    typer.echo(f"  输入：{input_file.name}")
    typer.echo()

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=Path("./demo_work"))
    pipeline.workspace.ensure_dirs()

    from subtap.ui.tui import RichRunner

    runner = RichRunner()

    try:
        runner.run_pipeline(
            pipeline,
            input_file,
            output_dir,
            fmt="srt",
        )
    except SystemExit:
        raise
    except Exception as e:
        _handle_error(f"演示失败：{e}")

    _show_srt_preview(output_dir)


def _show_srt_preview(output_dir: Path) -> None:
    """显示示例 SRT 内容（前 20 行）"""
    srt_path = output_dir / "final.srt"
    if srt_path.exists():
        typer.echo()
        typer.echo("═══ 示例 SRT（前 20 行）═══")
        lines = srt_path.read_text(encoding="utf-8").splitlines()
        for line in lines[:20]:
            typer.echo(f"  {line}")
        if len(lines) > 20:
            typer.echo(f"  ...（共 {len(lines)} 行）")


# ── Cleanup 命令 ──────────────────────────────────────────


def _clean_workspace(
    work_dir: Path = typer.Argument(..., help="工作目录路径"),
    all: bool = typer.Option(False, "--all", "-a", help="清理所有中间文件（L1 + L2）"),
) -> None:
    """清理工作区文件。

    默认只清理临时文件（L1）：
    - chunk WAV 文件
    - source WAV 文件
    - 系统文件（.DS_Store 等）

    使用 --all 清理所有中间文件（L1 + L2）：
    - 上述所有文件
    - asr.jsonl
    - cleaned.jsonl
    - sentences.jsonl

    永远不会清理：
    - aligned.jsonl（用户输出）
    - metrics.json（用户输出）
    - output/ 目录（用户输出）
    """
    from subtap.engine.cleanroom import Cleanroom

    if not work_dir.exists():
        _handle_error(f"工作目录不存在：{work_dir}")

    cleanroom = Cleanroom(work_dir)

    if all:
        result = cleanroom.clean_all()
    else:
        result = cleanroom.clean_temp_files()

    # 使用 format_summary() 显示清理结果
    summary = cleanroom.format_summary(result)
    typer.echo(summary)
