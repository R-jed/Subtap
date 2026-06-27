"""Subtap CLI — 中文优先字幕生成引擎入口."""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

import typer

from subtap import __version__

app = typer.Typer(
    name="subtap",
    help="Subtap — 本地优先的 AI 字幕生成引擎",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ── 基础命令 ──────────────────────────────────────────────


@app.command()
def version() -> None:
    """显示版本信息"""
    typer.echo(f"subtap v{__version__}")
    typer.echo(
        f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    typer.echo(f"系统 {platform.system()} {platform.machine()}")


@app.command(hidden=True)
def init() -> None:
    """初始化工作空间（~/.subtap/）"""
    home = Path.home()
    subtap_dir = home / ".subtap"
    config_path = subtap_dir / "config.yaml"
    glossary_dir = subtap_dir / "glossary"
    db_path = subtap_dir / "subtap.db"

    subtap_dir.mkdir(parents=True, exist_ok=True)
    glossary_dir.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        default_config = (
            Path(__file__).resolve().parents[2] / "configs" / "default.yaml"
        )
        if default_config.exists():
            shutil.copy2(default_config, config_path)
        else:
            config_path.write_text("# Subtap 配置\n")

    if not db_path.exists():
        db_path.touch()

    glossary_global = glossary_dir / "global.yaml"
    if not glossary_global.exists():
        glossary_global.write_text("# 全局术语表\nentries: []\n")

    typer.echo(f"✓ 工作空间已初始化：{subtap_dir}")
    typer.echo(f"  配置文件：{config_path}")
    typer.echo(f"  术语表：  {glossary_dir}")
    typer.echo(f"  数据库：  {db_path}")


# ── Doctor 命令 ────────────────────────────────────────────


@app.command()
def doctor(
    release: bool = typer.Option(False, "--release", help="执行发布前完整检查"),
    workspace: bool = typer.Option(False, "--workspace", "-ws", help="检查工作区状态"),
    json_output: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
) -> None:
    """检查系统依赖和运行环境"""
    # ── Workspace mode ──────────────────────────────────────
    if workspace:
        _doctor_workspace()
        return

    checks: list[tuple[str, str, bool, str]] = []

    # 基础依赖
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    checks.append(
        (
            "ffmpeg",
            "音视频处理",
            ffmpeg_ok,
            "" if ffmpeg_ok else "未找到，请安装：brew install ffmpeg",
        )
    )

    ffprobe_ok = shutil.which("ffprobe") is not None
    checks.append(
        (
            "ffprobe",
            "媒体探测",
            ffprobe_ok,
            "" if ffprobe_ok else "未找到，请安装：brew install ffmpeg",
        )
    )

    py_ver = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    py_ok = sys.version_info >= (3, 10)
    checks.append(
        (
            "python",
            "Python 版本",
            py_ok,
            f"v{py_ver}" if py_ok else f"v{py_ver}（需要 >= 3.10）",
        )
    )

    # 工作空间
    subtap_dir = Path.home() / ".subtap"
    ws_ok = (
        subtap_dir.exists() and os.access(str(subtap_dir), os.W_OK)
        if subtap_dir.exists()
        else False
    )
    checks.append(
        (
            "workspace",
            "工作空间",
            ws_ok,
            "" if ws_ok else f"不可写或不存在：{subtap_dir}",
        )
    )

    # --release 模式：增加模型和 TUI 检查
    if release:
        import importlib.util

        # MLX 运行时
        mlx_ok = importlib.util.find_spec("mlx") is not None
        checks.append(
            (
                "mlx",
                "MLX 运行时",
                mlx_ok,
                "" if mlx_ok else "未安装，请：pip install mlx",
            )
        )

        # mlx-audio
        mla_ok = importlib.util.find_spec("mlx_audio") is not None
        checks.append(
            (
                "mlx-audio",
                "MLX Audio",
                mla_ok,
                "" if mla_ok else "未安装，请：pip install mlx-audio",
            )
        )

        # rich
        rich_ok = importlib.util.find_spec("rich") is not None
        checks.append(
            (
                "rich",
                "Rich TUI",
                rich_ok,
                "" if rich_ok else "未安装，请：pip install rich",
            )
        )

    # 打印结果
    all_ok = True
    report: dict[str, Any] = {
        "ok": True,
        "release": release,
        "checks": [],
        "config": {},
        "models": [],
    }
    for _name, label, ok, detail in checks:
        report["checks"].append(
            {"name": _name, "label": label, "ok": ok, "detail": detail}
        )
        icon = (
            typer.style("✓", fg=typer.colors.GREEN)
            if ok
            else typer.style("✗", fg=typer.colors.RED)
        )
        msg = f"  {icon} {label}"
        if detail:
            msg += f" — {detail}"
        if not json_output:
            typer.echo(msg)
        if not ok:
            all_ok = False

    # ── 配置状态 ───────────────────────────────────────────
    if not json_output:
        typer.echo("\n▸ 配置状态")
    config_path = subtap_dir / "config.yaml"
    if config_path.exists():
        report["config"] = {"path": str(config_path), "exists": True, "valid": False}
        if not json_output:
            typer.echo(f"  ✓ {config_path} 存在")
        try:
            from subtap.schemas.config import load_config

            load_config(config_path)
            report["config"]["valid"] = True
            if not json_output:
                typer.echo("  ✓ 配置文件有效")
        except Exception as e:
            report["config"]["error"] = str(e)
            if not json_output:
                typer.echo(f"  ✗ 配置文件无效：{e}")
            all_ok = False
    else:
        report["config"] = {"path": str(config_path), "exists": False, "valid": False}
        if not json_output:
            typer.echo(f"  ✗ {config_path} 不存在")
        all_ok = False

    # ── 模型状态 ───────────────────────────────────────────
    if not json_output:
        typer.echo("\n▸ 模型状态")
    try:
        from subtap.schemas.config import load_config
        from subtap.core.models import ModelRegistry

        config = load_config(config_path)
        registry = ModelRegistry(config)

        for ms in registry.status():
            icon = (
                typer.style("✓", fg=typer.colors.GREEN)
                if ms.installed
                else typer.style("✗", fg=typer.colors.RED)
            )
            report["models"].append(
                {
                    "name": ms.name,
                    "installed": ms.installed,
                    "path": str(ms.path),
                    "missing_files": ms.missing_files,
                }
            )
            if not json_output:
                typer.echo(f"  {icon} {ms.name}")
            if not ms.installed:
                all_ok = False
                if not json_output:
                    typer.echo(f"    路径：{ms.path}")
                if ms.missing_files:
                    if not json_output:
                        typer.echo(f"    缺失：{', '.join(ms.missing_files)}")
    except Exception as e:
        report["models_error"] = str(e)
        if not json_output:
            typer.echo(f"  ⚠ 无法检查模型状态：{e}")

    report["ok"] = all_ok
    if json_output:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        if not all_ok:
            raise typer.Exit(1)
        return

    if all_ok:
        typer.echo(typer.style("\n✓ 所有检查通过！", fg=typer.colors.GREEN))
    else:
        typer.echo(
            typer.style("\n✗ 部分检查未通过，请根据提示修复", fg=typer.colors.RED)
        )
        raise typer.Exit(1)


def _doctor_workspace(work_dir: Path = Path("./work")) -> None:
    """检查工作区状态：Git、环境卫生、模型、Pipeline 状态。"""
    typer.echo("═══ 工作区状态检查 ═══\n")

    # 1. Git 状态
    from subtap.engine.git_guard import GitGuard

    git_guard = GitGuard(work_dir)
    if git_guard.is_git_repo():
        git_status = git_guard.get_git_status()
        typer.echo("▸ Git 状态")
        typer.echo(f"  分支: {git_status['branch']}")
        typer.echo(f"  提交: {git_status['commit_hash']}")
        dirty_icon = (
            typer.style("✗ 脏", fg=typer.colors.RED)
            if git_status["is_dirty"]
            else typer.style("✓ 干净", fg=typer.colors.GREEN)
        )
        typer.echo(f"  状态: {dirty_icon}")
        if git_status["changed_files"]:
            for f in git_status["changed_files"][:5]:
                typer.echo(f"    - {f}")
    else:
        typer.echo("▸ Git 状态")
        typer.echo(typer.style("  ⚠ 非 Git 仓库", fg=typer.colors.YELLOW))

    # 2. 工作环境卫生
    from subtap.engine.cleanroom import Cleanroom

    cleanroom = Cleanroom(work_dir)
    cr_result = cleanroom.check_workspace()
    typer.echo("\n▸ 工作环境卫生")
    clean_icon = (
        typer.style("✓ 干净", fg=typer.colors.GREEN)
        if cr_result["is_clean"]
        else typer.style("⚠ 有问题", fg=typer.colors.YELLOW)
    )
    typer.echo(f"  状态: {clean_icon}")
    if cr_result["issues"]:
        for issue in cr_result["issues"]:
            typer.echo(f"    - {issue}")

    # 3. 模型状态
    model_status = cleanroom.check_model_status()
    typer.echo("\n▸ 模型状态")
    for m in model_status["models"]:
        icon = (
            typer.style("✓", fg=typer.colors.GREEN)
            if m["installed"]
            else typer.style("✗", fg=typer.colors.RED)
        )
        typer.echo(f"  {icon} {m['name']}")

    # 4. Pipeline 状态（检查中间文件）
    typer.echo("\n▸ Pipeline 中间文件")
    for name, label in [
        ("chunks/chunks.jsonl", "切段结果"),
        ("asr/asr.jsonl", "ASR 结果"),
        ("cleaned.jsonl", "清洗结果"),
        ("sentences.jsonl", "断句结果"),
        ("aligned.jsonl", "对齐结果"),
    ]:
        p = work_dir / name
        icon = (
            typer.style("✓", fg=typer.colors.GREEN)
            if p.exists()
            else typer.style("○", fg=typer.colors.WHITE)
        )
        typer.echo(f"  {icon} {label}")

    typer.echo("\n═══ 检查完成 ═══")


# ── Setup 命令 ─────────────────────────────────────────────


@app.command()
def setup(
    skip_models: bool = typer.Option(False, "--skip-models", help="跳过模型下载"),
    download_source: str = typer.Option(
        "ask",
        "--download-source",
        help="模型下载方式：ask / hf / hf-mirror / modelscope / manual",
    ),
    include_optional: bool = typer.Option(
        False, "--include-optional", help="同时下载可选大模型"
    ),
    model_endpoint: str | None = typer.Option(
        None, "--model-endpoint", help="自定义 Hugging Face 镜像地址"
    ),
) -> None:
    """用户初始化向导"""
    from subtap.core.setup import SetupWizard

    wizard = SetupWizard()

    typer.echo("═══ Subtap 初始化向导 ═══\n")

    # Step 1: System check
    typer.echo("▸ Step 1: 系统检查")
    deps = wizard.check_system_deps()

    for name, ok in deps.items():
        icon = (
            typer.style("✓", fg=typer.colors.GREEN)
            if ok
            else typer.style("✗", fg=typer.colors.RED)
        )
        label = {
            "ffmpeg": "ffmpeg",
            "ffprobe": "ffprobe",
            "python": "Python 3.10+",
        }.get(name, name)
        typer.echo(f"  {icon} {label}")

    if not all(deps.values()):
        typer.echo(
            typer.style("\n✗ 系统检查未通过，请安装缺失依赖", fg=typer.colors.RED)
        )
        raise typer.Exit(1)

    # Step 2: Config init
    typer.echo("\n▸ Step 2: 初始化配置")
    if not wizard.check_config_exists():
        wizard.run_init()
        typer.echo("  ✓ ~/.subtap/ 已创建")
    else:
        typer.echo("  ✓ ~/.subtap/ 已存在")

    # Step 3: Model setup
    if skip_models:
        typer.echo("\n▸ Step 3: 模型安装（已跳过）")
    else:
        typer.echo("\n▸ Step 3: 模型安装")
        ok = wizard.setup_models(
            source=download_source,
            include_optional=include_optional,
            endpoint=model_endpoint,
        )
        if ok:
            typer.echo("  ✓ 模型安装完成")
        elif (
            download_source == "manual"
            or getattr(wizard, "last_model_source", None) == "manual"
        ):
            # manual 模式下用户选择手动安装，正常结束
            typer.echo("  ⚠ 模型安装待手动完成")
        else:
            typer.echo("  ✗ 模型安装失败")
            raise typer.Exit(1)

    typer.echo(typer.style("\n═══ 初始化完成 ═══", fg=typer.colors.GREEN))
    typer.echo("下一步：subtap run <音频文件>")


# ── Run 命令 ───────────────────────────────────────────────


def _run_pipeline_safely(
    pipeline,
    input_path: Path,
    output_dir: Path,
    mode: str,
    fmt: str,
    skip_clean: bool,
    skip_align: bool,
) -> dict:
    """在线程中安全运行 pipeline，不涉及 UI 操作。"""
    from subtap.ui.tui import TUIRunner

    runner = TUIRunner(use_tui=False, mode=mode)
    return runner.run_pipeline(
        pipeline,
        input_path,
        output_dir,
        fmt=fmt,
        skip_clean=skip_clean,
        skip_align=skip_align,
    )


@app.command()
def run(
    input_path: Path = typer.Argument(
        ..., help="输入媒体文件路径（支持 mp3/mp4/wav/mkv 等）"
    ),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    output_dir: Path = typer.Option(
        Path("./output"), "-o", "--output-dir", help="输出目录"
    ),
    fmt: str = typer.Option("srt", "--format", "-f", help="导出格式：srt / ass / txt"),
    mode: str = typer.Option(
        "hybrid", "--mode", "-m", help="执行模式：fast / quality / hybrid"
    ),
    skip_clean: bool = typer.Option(False, "--skip-clean", help="跳过文本清洗阶段"),
    skip_align: bool = typer.Option(False, "--skip-align", help="跳过时间轴对齐阶段"),
    use_tui: bool = typer.Option(
        True, "--tui/--no-tui", help="启用 TUI 界面（默认开启）"
    ),
    policy: str = typer.Option(
        "local", "--policy", "-p", help="执行策略：local / hybrid / fast"
    ),
    no_git_check: bool = typer.Option(
        False, "--no-git-check", help="跳过 Git 状态检查"
    ),
    no_cleanroom: bool = typer.Option(
        False, "--no-cleanroom", help="跳过工作环境卫生检查"
    ),
    timestamp: bool = typer.Option(
        True, "--timestamp/--no-timestamp", help="输出目录是否带时间戳"
    ),
    json_output: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
) -> None:
    """运行完整字幕生成流程

    [bold]流程：[/bold] 音频标准化 → 切段 → 语音识别 → 文本清洗 → 智能断句 → 时间轴对齐 → 字幕导出

    [bold]模式：[/bold]
      fast     — 最快速度，跳过清洗和对齐
      quality  — 完整流程，使用大模型，质量最高
      hybrid   — 平衡速度和质量（默认）

    [bold]示例：[/bold]
      subtap run video.mp3
      subtap run audio.mp3 --mode fast
      subtap run input.mp3 --mode quality -o ./subtitles
      subtap run input.mp3 --no-git-check --no-cleanroom
    """
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if json_output and use_tui:
        typer.echo("✗ --json 需要同时使用 --no-tui", err=True)
        raise typer.Exit(1)

    if not input_path.exists():
        typer.echo(f"✗ 错误：文件未找到 {input_path}", err=True)
        raise typer.Exit(1)

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    config.output.timestamp = timestamp  # CLI overrides config

    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

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

    # ── Mode-based skip flags ────────────────────────────────
    if mode == "fast":
        skip_clean = True
        skip_align = True
    elif mode == "quality":
        skip_clean = False
        skip_align = False
    # hybrid mode uses defaults

    # ── Pipeline execution ──────────────────────────────────
    from subtap.metrics.events import EventBus
    from subtap.metrics.profiler import PipelineProfiler

    # 创建 Event Bus 和 Profiler
    event_bus = EventBus()
    profiler = PipelineProfiler(event_bus)
    profiler.wrap_pipeline(pipeline)

    if use_tui:
        from concurrent.futures import ThreadPoolExecutor
        from subtap.ui.dashboard import PipelineDashboard
        from subtap.ui.event_bridge import EventBridge

        dashboard = PipelineDashboard(event_bus, profiler)
        bridge = EventBridge(event_bus, dashboard)
        bridge.connect()

        # 使用 ThreadPoolExecutor 管理线程生命周期
        timings = {}
        pipeline_error = None

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _run_pipeline_safely,
                pipeline,
                input_path,
                output_dir,
                mode,
                fmt,
                skip_clean,
                skip_align,
            )

            # 运行 dashboard（它会启动 async loop 处理事件）
            dashboard.run()

            # 获取结果（future.result() 会阻塞直到完成）
            try:
                result = future.result(timeout=300)
                timings = result.get("timings", {})
            except Exception as e:
                pipeline_error = e

        if pipeline_error:
            typer.echo(f"\n✗ 处理失败：{pipeline_error}", err=True)
            raise typer.Exit(1)
    else:
        from subtap.ui.tui import PlainRunner

        runner = PlainRunner()

        timings = {}
        try:
            if json_output:
                with redirect_stdout(StringIO()):
                    result = runner.run_pipeline(
                        pipeline,
                        input_path,
                        output_dir,
                        fmt=fmt,
                        skip_clean=skip_clean,
                        skip_align=skip_align,
                    )
            else:
                result = runner.run_pipeline(
                    pipeline,
                    input_path,
                    output_dir,
                    fmt=fmt,
                    skip_clean=skip_clean,
                    skip_align=skip_align,
                )
            timings = result.get("timings", {})
        except SystemExit:
            raise
        except Exception as e:
            typer.echo(f"\n✗ 处理失败：{e}", err=True)
            raise typer.Exit(1)

    # ── Generate report and debug output ────────────────────
    try:
        from subtap.quality.scorer import Scorer
        from subtap.core.report import generate_report

        # Quality assessment
        aligned_path = work_dir / "aligned.jsonl"
        if aligned_path.exists():
            scorer = Scorer(aligned_path)
            quality_report = scorer.score()

            # Generate report
            report_content = generate_report(
                quality_score=quality_report.total_score,
                error_count=quality_report.error_count,
                fixable_count=quality_report.fixable_count,
                fixed_count=0,
                segment_count=0,
                timings=timings,
                mode=mode,
                input_file=input_path,
                output_format=fmt,
            )

            # Write report
            output_dir.mkdir(parents=True, exist_ok=True)
            report_path = output_dir / "report.md"
            report_path.write_text(report_content, encoding="utf-8")
            if not json_output:
                typer.echo(f"\n▸ 质量报告：{report_path}")

            # Write debug.json
            debug_data = {
                "mode": mode,
                "input_file": str(input_path),
                "output_format": fmt,
                "quality_score": quality_report.total_score,
                "timings": timings,
                "error_count": quality_report.error_count,
            }
            debug_path = output_dir / "debug.json"
            debug_path.write_text(
                json.dumps(debug_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
    except Exception as e:
        # Report generation is optional - don't fail the whole run
        if not json_output:
            typer.echo(f"\n⚠ 报告生成失败：{e}", err=True)

    if json_output:
        output_path = output_dir / f"output.{fmt}"
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "input_path": str(input_path),
                    "work_dir": str(work_dir),
                    "output_dir": str(output_dir),
                    "output_path": str(output_path),
                    "report_path": str(output_dir / "report.md"),
                    "debug_path": str(output_dir / "debug.json"),
                    "timings": timings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


# ── 单阶段命令 ─────────────────────────────────────────────


@app.command("batch-transcribe")
def batch_transcribe(
    files: str = typer.Option(..., "--files", "-f", help="输入文件，逗号分隔"),
    output_dir: Path = typer.Option(
        Path("./output"), "--output-dir", "-o", help="输出目录"
    ),
    mode: str = typer.Option("offline", "--mode", "-m", help="offline / hybrid / remote-asr"),
    json_output: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
) -> None:
    """批量转录多个媒体文件。"""
    paths = [Path(item.strip()) for item in files.split(",") if item.strip()]
    if not paths:
        typer.echo("✗ 未提供输入文件", err=True)
        raise typer.Exit(1)

    result = {
        "ok": all(path.exists() for path in paths),
        "output_dir": str(output_dir),
        "mode": mode,
        "items": [
            {"input_path": str(path), "ok": path.exists(), "error": "" if path.exists() else "文件不存在"}
            for path in paths
        ],
    }
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return

    for item in result["items"]:
        icon = "✓" if item["ok"] else "✗"
        typer.echo(f"  {icon} {item['input_path']}")


@app.command()
def prepare(
    input_path: Path = typer.Argument(..., help="输入媒体文件路径"),
    output: Path = typer.Option(Path("./work"), "-o", "--output", help="工作目录"),
) -> None:
    """提取音频并切段（单阶段执行）"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not input_path.exists():
        typer.echo(f"✗ 文件未找到：{input_path}", err=True)
        raise typer.Exit(1)

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


@app.command()
def transcribe(
    audio_path: Path = typer.Argument(..., help="音频文件路径"),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    backend: str | None = typer.Option(None, "-b", "--backend", help="ASR 后端覆盖"),
) -> None:
    """语音识别（单阶段执行）"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not audio_path.exists():
        typer.echo(f"✗ 文件未找到：{audio_path}", err=True)
        raise typer.Exit(1)

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    typer.echo(f"▸ 语音识别（{backend or config.asr.backend}）...")
    try:
        result = pipeline.run_stage("asr", backend_name=backend)
    except (ImportError, NotImplementedError) as e:
        typer.echo(f"✗ 错误：{e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"  ✓ {result['segment_count']} 条 → {result['asr_jsonl']}")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


@app.command()
def clean(
    asr_path: Path = typer.Argument(..., help="asr.jsonl 路径"),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    llm: str | None = typer.Option(
        None, "--llm", help="LLM 后端（如 ollama:qwen3-coder）"
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
        typer.echo(f"✗ 文件未找到：{asr_path}", err=True)
        raise typer.Exit(1)

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
        typer.echo(f"✗ 错误：{e}", err=True)
        raise typer.Exit(1)

    cleaned_path = Path(result["cleaned_jsonl"])
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        if cleaned_path.resolve() != output.resolve():
            shutil.copy2(cleaned_path, output)
        cleaned_path = output

    typer.echo(f"  ✓ {result['segment_count']} 条 → {cleaned_path}")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


@app.command()
def segment(
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
        typer.echo(f"✗ 文件未找到：{cleaned_path}", err=True)
        raise typer.Exit(1)

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    if cleaned_path.resolve() != pipeline.workspace.cleaned_jsonl.resolve():
        shutil.copy2(cleaned_path, pipeline.workspace.cleaned_jsonl)

    typer.echo("▸ 智能断句...")
    try:
        result = pipeline.run_stage("segment")
    except ValueError as e:
        typer.echo(f"✗ 错误：{e}", err=True)
        raise typer.Exit(1)

    sentences_path = Path(result["sentences_jsonl"])
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        if sentences_path.resolve() != output.resolve():
            shutil.copy2(sentences_path, output)
        sentences_path = output

    typer.echo(f"  ✓ {result['sentence_count']} 句 → {sentences_path}")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


@app.command()
def align(
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
        typer.echo(f"✗ 文件未找到：{sentences_path}", err=True)
        raise typer.Exit(1)

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    if sentences_path.resolve() != pipeline.workspace.sentences_jsonl.resolve():
        shutil.copy2(sentences_path, pipeline.workspace.sentences_jsonl)

    typer.echo(f"▸ 时间轴对齐（{backend or config.align.backend}）...")
    try:
        result = pipeline.run_stage("align", backend_name=backend)
    except (ImportError, ValueError) as e:
        typer.echo(f"✗ 错误：{e}", err=True)
        raise typer.Exit(1)

    aligned_path = Path(result["aligned_jsonl"])
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        if aligned_path.resolve() != output.resolve():
            shutil.copy2(aligned_path, output)
        aligned_path = output

    typer.echo(f"  ✓ {result['aligned_count']} 条 → {aligned_path}")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


@app.command()
def export(
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
        typer.echo(f"✗ 文件未找到：{aligned_path}", err=True)
        raise typer.Exit(1)

    typer.echo(f"▸ 字幕导出（{fmt.upper()}）...")
    try:
        result = run_export(aligned_path, output_dir, fmt=fmt, stem=stem)
    except ValueError as e:
        typer.echo(f"✗ 错误：{e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"  ✓ {result['output_path']}（{result['segment_count']} 条）")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


# ── Resume / Retry 命令 ────────────────────────────────────


@app.command()
def resume(
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
        typer.echo(f"✗ 恢复失败：{e}", err=True)
        raise typer.Exit(1)


@app.command()
def retry(
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
        typer.echo(f"✗ {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"✗ 重试失败：{e}", err=True)
        raise typer.Exit(1)


# ── Demo 命令 ──────────────────────────────────────────────


@app.command()
def demo(
    output_dir: Path = typer.Option(
        Path("./demo_output"), "-o", "--output-dir", help="输出目录"
    ),
    skip_tui: bool = typer.Option(False, "--skip-tui", help="跳过 TUI 展示"),
) -> None:
    """运行演示：使用内置测试音频展示完整流程

    自动查找项目内置测试音频，执行完整 pipeline 并输出示例 SRT。
    """
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    # 查找内置测试音频
    samples_dir = Path(__file__).resolve().parents[2] / "samples"
    test_files = list(samples_dir.glob("*.mp3")) + list(samples_dir.glob("*.wav"))

    if not test_files:
        typer.echo("✗ 未找到内置测试音频", err=True)
        typer.echo(f"  请将测试音频放入：{samples_dir}", err=True)
        raise typer.Exit(1)

    input_file = test_files[0]
    typer.echo("═══ Subtap 演示 ═══")
    typer.echo(f"  输入：{input_file.name}")
    typer.echo()

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=Path("./demo_work"))
    pipeline.workspace.ensure_dirs()

    from subtap.ui.tui import PlainRunner, TUIRunner

    runner: PlainRunner | TUIRunner
    if skip_tui:
        runner = PlainRunner()
    else:
        runner = TUIRunner(use_tui=True)

    try:
        runner.run_pipeline(
            pipeline,
            input_file,
            output_dir,
            fmt="srt",
            skip_clean=True,
            skip_align=True,
        )
    except SystemExit:
        raise
    except Exception as e:
        typer.echo(f"\n✗ 演示失败：{e}", err=True)
        raise typer.Exit(1)

    # 显示示例 SRT 内容
    srt_path = output_dir / "output.srt"
    if srt_path.exists():
        typer.echo()
        typer.echo("═══ 示例 SRT（前 20 行）═══")
        lines = srt_path.read_text(encoding="utf-8").splitlines()
        for line in lines[:20]:
            typer.echo(f"  {line}")
        if len(lines) > 20:
            typer.echo(f"  ...（共 {len(lines)} 行）")


# ── Quality 命令 ────────────────────────────────────────────


@app.command()
def quality(
    aligned_path: Path = typer.Argument(..., help="aligned.jsonl 路径"),
    report_only: bool = typer.Option(False, "--report-only", help="只显示报告，不修复"),
    fix: bool = typer.Option(False, "--fix", help="自动修复可修复的问题"),
    output: Path | None = typer.Option(None, "-o", "--output", help="修复后的输出路径"),
) -> None:
    """评估字幕质量并可选自动修复

    [bold]示例：[/bold]
      subtap quality work/aligned.jsonl
      subtap quality work/aligned.jsonl --report-only
      subtap quality work/aligned.jsonl --fix
      subtap quality work/aligned.jsonl --fix -o output/fixed.jsonl
    """
    from subtap.quality.scorer import Scorer
    from subtap.quality.error_detector import ErrorDetector
    from subtap.quality.fixer import Fixer

    if not aligned_path.exists():
        typer.echo(f"✗ 文件未找到：{aligned_path}", err=True)
        raise typer.Exit(1)

    # Score
    scorer = Scorer(aligned_path)
    report = scorer.score()

    # Display report
    typer.echo("═══ 字幕质量报告 ═══\n")
    typer.echo(f"评分：{report.total_score:.0f}/100")
    typer.echo(f"  对齐误差：      {report.alignment_error:.0f}/100")
    typer.echo(f"  断句质量：      {report.segmentation_quality:.0f}/100")
    typer.echo(f"  可读性：        {report.readability:.0f}/100")

    # Detect errors
    detector = ErrorDetector(aligned_path)
    errors = detector.detect()

    typer.echo(f"\n错误：{len(errors)} 个（{report.fixable_count} 可修复）")
    for error in errors:
        severity_icon = {
            "critical": typer.style("✗", fg=typer.colors.RED),
            "warning": typer.style("⚠", fg=typer.colors.YELLOW),
            "info": typer.style("ℹ", fg=typer.colors.BLUE),
        }.get(error.severity, "•")
        typer.echo(
            f"  {severity_icon} #{error.segment_id} {error.message} → {error.suggestion}"
        )

    # Fix if requested
    if fix and not report_only:
        fixer = Fixer(aligned_path)
        output_path = output or aligned_path.parent / "fixed_aligned.jsonl"
        actions = fixer.fix(errors, output_path)

        applied = [a for a in actions if a.applied]
        if applied:
            typer.echo(f"\n✓ 已修复 {len(applied)} 个问题 → {output_path}")
            for action in applied:
                typer.echo(f"  ✓ #{action.segment_id}: {action.description}")
        else:
            typer.echo("\n没有可自动修复的问题")

    # Write quality event to log
    log_path = aligned_path.parent / "logs" / "event.log.jsonl"
    if log_path.parent.exists():
        import json
        import time

        event = {
            "stage": "quality_check",
            "quality_score": report.total_score,
            "error_count": len(errors),
            "fixable_count": report.fixable_count,
            "timestamp": time.time(),
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ── Analyze 命令 ────────────────────────────────────────────


@app.command()
def analyze(
    srt_path: Path = typer.Argument(..., help="SRT 字幕文件路径"),
) -> None:
    """分析字幕文件质量并输出报告

    [bold]示例：[/bold]
      subtap analyze output.srt
      subtap analyze subtitles/final.srt
    """
    from subtap.quality.scorer import Scorer
    from subtap.quality.error_detector import ErrorDetector

    if not srt_path.exists():
        typer.echo(f"✗ 文件未找到：{srt_path}", err=True)
        raise typer.Exit(1)

    # Parse SRT to aligned format for analysis
    segments = _parse_srt_to_aligned(srt_path)
    if not segments:
        typer.echo("✗ 无法解析 SRT 文件", err=True)
        raise typer.Exit(1)

    # Create temporary aligned.jsonl for analysis
    import tempfile
    import json

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        for seg in segments:
            f.write(json.dumps(seg, ensure_ascii=False) + "\n")
        temp_path = Path(f.name)

    try:
        # Score
        scorer = Scorer(temp_path)
        report = scorer.score()

        # Detect errors
        detector = ErrorDetector(temp_path)
        errors = detector.detect()

        # Display analysis
        typer.echo("═══ 字幕分析报告 ═══\n")
        typer.echo(f"文件：{srt_path.name}")
        typer.echo(f"字幕数：{len(segments)} 条\n")

        typer.echo(f"质量评分：{report.total_score:.0f}/100")
        typer.echo(f"  对齐误差：      {report.alignment_error:.0f}/100")
        typer.echo(f"  断句质量：      {report.segmentation_quality:.0f}/100")
        typer.echo(f"  可读性：        {report.readability:.0f}/100")

        # Show errors
        if errors:
            typer.echo(f"\n问题：{len(errors)} 个")
            for error in errors:
                severity_icon = {
                    "critical": typer.style("✗", fg=typer.colors.RED),
                    "warning": typer.style("⚠", fg=typer.colors.YELLOW),
                    "info": typer.style("ℹ", fg=typer.colors.BLUE),
                }.get(error.severity, "•")
                typer.echo(f"  {severity_icon} #{error.segment_id} {error.message}")
        else:
            typer.echo("\n✓ 未发现问题")

        # Suggestions
        typer.echo("\n建议：")
        if report.total_score < 80:
            typer.echo("  1. 使用 --mode quality 重新生成可提升质量")
        if any(e.error_type == "too_long" for e in errors):
            typer.echo("  2. 过长字幕建议拆分以提高可读性")
        if any(e.error_type == "overlap" for e in errors):
            typer.echo("  3. 时间轴重叠需要修复")
        if report.total_score >= 90:
            typer.echo("  ✓ 质量优秀，可直接用于剪辑软件")

    finally:
        temp_path.unlink()


def _parse_srt_to_aligned(srt_path: Path) -> list[dict]:
    """Parse SRT file to aligned segment format for analysis.

    Args:
        srt_path: Path to SRT file.

    Returns:
        List of aligned segment dicts.
    """
    import re

    content = srt_path.read_text(encoding="utf-8")
    segments = []

    # Parse SRT format: sequence number, timestamp, text
    pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\n\d+\n|\Z)"
    matches = re.findall(pattern, content, re.DOTALL)

    for seq, start, end, text in matches:
        # Convert timestamp to seconds
        start_sec = _srt_time_to_seconds(start)
        end_sec = _srt_time_to_seconds(end)
        text = text.strip().replace("\n", " ")

        segments.append(
            {
                "sentence_id": int(seq) - 1,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "text": text,
            }
        )

    return segments


def _srt_time_to_seconds(time_str: str) -> float:
    """Convert SRT timestamp to seconds.

    Args:
        time_str: SRT timestamp (HH:MM:SS,mmm)

    Returns:
        Time in seconds.
    """
    hours, minutes, seconds = time_str.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


# ── Models 子命令组 ────────────────────────────────────────

models_app = typer.Typer(help="模型管理", no_args_is_help=True)
app.add_typer(models_app, name="models")


@models_app.command("status")
def models_status() -> None:
    """查看所有模型状态"""
    from subtap.schemas.config import load_config
    from subtap.core.models import ModelRegistry

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    registry = ModelRegistry(config)

    for ms in registry.status():
        if ms.installed:
            status = typer.style("✓ 已安装", fg=typer.colors.GREEN)
        else:
            missing = ", ".join(ms.missing_files)
            status = typer.style(f"✗ 缺失（{missing}）", fg=typer.colors.RED)
        typer.echo(f"  {ms.name:12s} {status}  {ms.path}")


@models_app.command("install")
def models_install(
    model_name: str = typer.Argument(
        ..., help="要安装的模型（asr_0.6b / asr_1.7b / aligner / all）"
    ),
    download_source: str = typer.Option(
        "hf", "--source", "-s", help="下载源：hf / hf-mirror / modelscope"
    ),
    model_endpoint: str | None = typer.Option(
        None, "--endpoint", "-e", help="自定义 Hugging Face 镜像地址"
    ),
) -> None:
    """安装模型文件到本地"""
    from subtap.schemas.config import load_config
    from subtap.core.models import ModelDownloader, MODEL_REGISTRY
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        DownloadColumn,
        TransferSpeedColumn,
    )

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    if model_endpoint:
        config.models.hf_mirror_endpoint = model_endpoint
    downloader = ModelDownloader(config)

    targets = list(MODEL_REGISTRY.keys()) if model_name == "all" else [model_name]

    for name in targets:
        typer.echo(f"▸ 安装 {name}（{download_source}）...")
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
            ) as progress:
                task_id = progress.add_task(name, total=None)

                def update_progress(filename: str, downloaded: int, total: int) -> None:
                    if downloaded == 0:
                        progress.reset(
                            task_id, total=total, description=f"{name}/{filename}"
                        )
                    progress.update(task_id, completed=downloaded)

                path = downloader.download(
                    name, source=download_source, progress=update_progress
                )
            typer.echo(f"  ✓ {path}")
        except ValueError as e:
            typer.echo(f"  ✗ 错误：{e}", err=True)
            raise typer.Exit(1)
        except NotImplementedError as e:
            typer.echo(f"  {e}")
            typer.echo(
                typer.style(
                    f"  → 请将模型文件放入：{downloader.root / MODEL_REGISTRY[name]['subdir']}",
                    fg=typer.colors.YELLOW,
                )
            )


@models_app.command("verify")
def models_verify() -> None:
    """验证模型完整性"""
    from subtap.schemas.config import load_config
    from subtap.core.models import ModelVerifier

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    verifier = ModelVerifier(config)

    from subtap.core.models import MODEL_REGISTRY

    all_ok = True
    for name in MODEL_REGISTRY:
        result = verifier.verify(name)
        if result["status"] == "ok":
            typer.echo(typer.style(f"  ✓ {name}: 正常", fg=typer.colors.GREEN))
        else:
            typer.echo(
                typer.style(f"  ✗ {name}: {result['status']}", fg=typer.colors.RED)
            )
            all_ok = False

    if all_ok:
        typer.echo(typer.style("\n✓ 所有模型验证通过", fg=typer.colors.GREEN))
    else:
        typer.echo(typer.style("\n✗ 部分模型异常，请检查", fg=typer.colors.YELLOW))


@models_app.command("list")
def models_list() -> None:
    """列出可用模型"""
    from subtap.schemas.config import load_config
    from subtap.core.models import ModelRegistry

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    registry = ModelRegistry(config)

    typer.echo("═══ 可用模型 ═══")
    for name in registry.list_available():
        typer.echo(f"  • {name}")


@models_app.command("remove")
def models_remove(
    model_name: str = typer.Argument(..., help="要移除的模型名称"),
) -> None:
    """移除已安装的模型"""
    from subtap.schemas.config import load_config
    from subtap.core.models import ModelRemover

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    remover = ModelRemover(config)

    try:
        result = remover.remove(model_name)
        if result:
            typer.echo(f"✓ 已移除 {model_name}")
        else:
            typer.echo(f"⚠ {model_name} 不存在")
    except ValueError as e:
        typer.echo(f"✗ 错误：{e}", err=True)
        raise typer.Exit(1)
    except OSError as e:
        typer.echo(f"✗ 删除失败：{e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
