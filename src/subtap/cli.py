"""Subtap CLI — 中文优先字幕生成引擎入口."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

import typer

from subtap import __version__
from subtap.glossary.cli import app as glossary_app

app = typer.Typer(
    name="subtap",
    help="Subtap — 本地优先的 AI 字幕生成引擎",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(glossary_app, name="glossary")

# ── Glossary 热词命令 ──────────────────────────────────────────

hotword_app = typer.Typer(help="热词管理")
glossary_app.add_typer(hotword_app, name="hotword")


@hotword_app.command("add")
def hotword_add(
    word: str = typer.Argument(..., help="热词（正确写法）"),
    aliases: str = typer.Argument(..., help="错词（逗号分隔）"),
    lang: str = typer.Option("zh", "--lang", "-l", help="语言"),
) -> None:
    """添加热词"""
    from subtap.glossary.hotword import Hotword, HotwordGlossary, load_glossary, save_glossary

    glossary_dir = Path.home() / ".subtap" / "glossary"
    path = glossary_dir / f"hotwords_{lang}.txt"
    glossary = load_glossary(path, lang)
    glossary.add(Hotword(word=word, aliases=[a.strip() for a in aliases.split(",")]))
    save_glossary(glossary, path)
    typer.echo(f"✓ 已添加热词：{word} = {aliases}")


@hotword_app.command("list")
def hotword_list(
    lang: str = typer.Option("zh", "--lang", "-l", help="语言"),
) -> None:
    """查看热词"""
    from subtap.glossary.hotword import load_glossary

    glossary_dir = Path.home() / ".subtap" / "glossary"
    path = glossary_dir / f"hotwords_{lang}.txt"
    glossary = load_glossary(path, lang)

    if not glossary.hotwords:
        typer.echo(f"暂无 {lang} 热词")
        return

    typer.echo(f"▸ {lang} 热词列表：")
    for hw in glossary.hotwords:
        aliases = ", ".join(hw.aliases)
        typer.echo(f"  {hw.word} = {aliases}")


@hotword_app.command("delete")
def hotword_delete(
    word: str = typer.Argument(..., help="热词"),
    lang: str = typer.Option("zh", "--lang", "-l", help="语言"),
) -> None:
    """删除热词"""
    from subtap.glossary.hotword import load_glossary, save_glossary

    glossary_dir = Path.home() / ".subtap" / "glossary"
    path = glossary_dir / f"hotwords_{lang}.txt"
    glossary = load_glossary(path, lang)
    glossary.remove(word)
    save_glossary(glossary, path)
    typer.echo(f"✓ 已删除热词：{word}")


@hotword_app.command("edit")
def hotword_edit(
    lang: str = typer.Option("zh", "--lang", "-l", help="语言"),
) -> None:
    """编辑热词（用 Numbers 打开）"""
    import subprocess

    glossary_dir = Path.home() / ".subtap" / "glossary"
    path = glossary_dir / f"hotwords_{lang}.txt"

    if not path.exists():
        from subtap.glossary.hotword import HotwordGlossary, save_glossary
        save_glossary(HotwordGlossary(lang=lang), path)

    subprocess.run(["open", "-a", "Numbers", str(path)])
    typer.echo(f"✓ 已打开 {path}")


script_app = typer.Typer(help="文稿匹配")
app.add_typer(script_app, name="script")
learn_app = typer.Typer(help="学习人工修正")
profile_app = typer.Typer(help="本地学习档案")
app.add_typer(learn_app, name="learn")
app.add_typer(profile_app, name="profile")

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


@learn_app.command("import")
def learn_import(
    corrected_srt: Path = typer.Argument(..., help="人工修正后的 SRT 文件"),
    yes: bool = typer.Option(False, "--yes", "-y", help="确认写入本地学习档案"),
) -> None:
    """导入人工修正字幕，写入前必须确认。"""
    from subtap.learning.importer import import_corrected_srt
    from subtap.learning.profile_store import ProfileStore

    if not corrected_srt.exists():
        typer.echo(f"✗ 文件不存在：{corrected_srt}", err=True)
        raise typer.Exit(1)

    texts = import_corrected_srt(corrected_srt)
    pairs = [{"from": "", "to": text} for text in texts]
    store = ProfileStore()
    if not store.apply_corrections(pairs, confirmed=yes):
        typer.echo("未写入：请确认后使用 --yes 写入本地学习档案")
        return
    typer.echo(f"✓ 已导入 {len(pairs)} 条修正到本地学习档案")


@profile_app.command("export")
def profile_export(
    output: Path = typer.Option(
        Path("subtap-profile-export.yaml"),
        "--output",
        "-o",
        help="导出文件路径",
    ),
) -> None:
    """导出本地可编辑学习档案。"""
    from subtap.learning.profile_store import ProfileStore

    path = ProfileStore().export(output)
    typer.echo(f"✓ 已导出：{path}")


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
        report["runtime"] = {
            "asr_model": config.asr.model,
            "asr_quantization": config.asr.quantization,
            "aligner_model": config.align.model,
            "aligner_quantization": config.align.quantization,
            "keep_model_alive": bool(
                config.asr.keep_model_alive or config.align.keep_model_alive
            ),
            "warmup": bool(config.asr.warmup or config.align.warmup),
            "device_backend": "mlx-metal",
        }
        report["privacy"] = {
            "external_audio_sent": False,
            "local_only_available": True,
            "default_local": True,
        }
        report["output"] = {
            "default_dir": "./output",
            "final_outputs": ["final.srt", "final.vtt", "final.json", "final.tsv"],
            "draft_outputs": ["draft.srt", "draft.json"],
        }
        remote_api = getattr(config, "remote_api", None)
        api_key_env = getattr(remote_api, "api_key_env", "SUBTAP_API_KEY")
        report["llm"] = {
            "api_configured": bool(os.environ.get(api_key_env)),
            "api_key_env": api_key_env,
            "audio_sent": False,
        }

        if not json_output:
            typer.echo(
                f"  ASR：{config.asr.model} / {config.asr.quantization}，"
                f"对齐：{config.align.model} / {config.align.quantization}"
            )
            typer.echo("  模型策略：任务阶段加载，阶段结束释放，不默认常驻或预热")
            typer.echo("  隐私：音频不外发；--local-only 可用")
            typer.echo("  输出：默认写入 ./output，精对齐生成 final.*")

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
    remote_api: bool = typer.Option(False, "--remote-api", help="配置远程 API"),
    remote_provider: str = typer.Option(
        "openai-compatible",
        "--remote-provider",
        help="远程 API 格式：openai-compatible / anthropic",
    ),
    remote_base_url: str | None = typer.Option(
        None, "--remote-base-url", help="远程 API Base URL"
    ),
    remote_api_key_env: str = typer.Option(
        "SUBTAP_API_KEY",
        "--remote-api-key-env",
        help="保存到配置的 API Key 环境变量名",
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
            "venv": "Python 虚拟环境",
            "mlx": "MLX / Metal",
            "models": "本地 models/",
            "output": "输出目录权限",
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

    if remote_api:
        typer.echo("\n▸ Step 4: 远程 API 配置")
        if not wizard.configure_remote_api(
            provider=remote_provider,
            base_url=remote_base_url,
            api_key_env=remote_api_key_env,
        ):
            raise typer.Exit(1)

    typer.echo(typer.style("\n═══ 初始化完成 ═══", fg=typer.colors.GREEN))
    typer.echo("下一步：subtap run <音频文件>")


# ── Run 命令 ───────────────────────────────────────────────


def _build_observer_child_command(
    *,
    input_path: Path,
    work_dir: Path,
    output_dir: Path,
    fmt: str,
    mode: str,
    enhance: str,
    local_only: bool,
    translate_to: str | None,
    bilingual: str,
    align_enabled: bool,
    punctuation: bool,
    subtitle_language: str,
    no_git_check: bool,
    no_cleanroom: bool,
    timestamp: bool,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "subtap.cli",
        "run",
        str(input_path),
        "--work-dir",
        str(work_dir),
        "--output-dir",
        str(output_dir),
        "--format",
        fmt,
        "--mode",
        mode,
        "--enhance",
        enhance,
        "--bilingual",
        bilingual,
        "--subtitle-language",
        subtitle_language,
        "--no-tui",
        "--observer-child",
    ]
    if local_only:
        command.append("--local-only")
    if translate_to:
        command.extend(["--translate-to", translate_to])
    if not align_enabled:
        command.append("--no-align")
    if punctuation:
        command.append("--punctuation")
    if no_git_check:
        command.append("--no-git-check")
    if no_cleanroom:
        command.append("--no-cleanroom")
    if not timestamp:
        command.append("--no-timestamp")
    return command


def _print_observer_state(log_path: Path) -> None:
    from subtap.ui.observer import summarize_event_log

    state = summarize_event_log(log_path)
    typer.echo(
        "▸ "
        f"阶段：{state['stage']}  "
        f"进度：{state['progress']}%  "
        f"Chunk：{state['chunk_id']}  "
        f"模型：{state['model']}  "
        f"草稿：{state['asr_drafts']}  "
        f"已对齐：{state['aligned']}"
    )


def _run_observer_parent(
    command: list[str], log_path: Path, refresh_interval: float = 1.0
) -> None:
    """父进程只观察日志；推理在子进程内执行。"""
    from subtap.ui.observer import ObserverDashboard

    output_dir = log_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / "child.stdout.log"
    stderr_path = output_dir / "child.stderr.log"
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        ObserverDashboard(log_path, process).run()

    _print_observer_state(log_path)
    if process.returncode:
        typer.echo(f"✗ 子进程处理失败，错误日志：{stderr_path}", err=True)
        raise typer.Exit(process.returncode)


def _run_pipeline_safely(
    pipeline,
    input_path: Path,
    output_dir: Path,
    mode: str,
    fmt: str,
    enhance: str = "local",
    align_enabled: bool = True,
    hotword_enabled: bool = True,
) -> dict:
    """在线程中安全运行 pipeline，不涉及 UI 操作。"""
    from subtap.ui.tui import TUIRunner

    runner = TUIRunner(use_tui=False, mode=mode)
    return runner.run_pipeline(
        pipeline,
        input_path,
        output_dir,
        fmt=fmt,
        enhance=enhance,
        align_enabled=align_enabled,
        hotword_enabled=hotword_enabled,
    )


def _exit_dashboard_when_pipeline_done(future, dashboard) -> None:
    """后台 pipeline 结束时退出 Textual dashboard。"""

    def _exit(_future):
        try:
            dashboard.call_from_thread(dashboard.exit)
        except Exception:
            try:
                dashboard.exit()
            except Exception:
                pass

    future.add_done_callback(_exit)


@app.command()
def run(
    input_path: Path = typer.Argument(
        ..., help="输入媒体文件路径（支持 mp3/mp4/wav/mkv 等）"
    ),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
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
        "local", "--enhance", "-e", help="字幕增强模式：off / local / api"
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
    align_enabled: bool = typer.Option(
        True,
        "--align/--no-align",
        help="默认执行精对齐；关闭后不生成 final.srt，只生成 draft 粗剪预览",
    ),
    punctuation: bool = typer.Option(
        False, "--punctuation", help="字幕带标点符号（默认不带）"
    ),
    subtitle_language: str = typer.Option(
        "zh", "--subtitle-language", help="字幕输出语种（zh/en/ja），影响标点规范"
    ),
    max_chars: int = typer.Option(
        25, "--max-chars", help="每行字幕最大字符数（10-60）", min=10, max=60
    ),
    min_chars: int = typer.Option(
        10, "--min-chars", help="每行字幕最小字符数（4-30）", min=4, max=30
    ),
    use_tui: bool = typer.Option(
        True, "--tui/--no-tui", help="启用 TUI 界面（默认开启）"
    ),
    observer_child: bool = typer.Option(False, "--observer-child", hidden=True),
    no_git_check: bool = typer.Option(
        False, "--no-git-check", help="跳过 Git 状态检查"
    ),
    no_cleanroom: bool = typer.Option(
        False, "--no-cleanroom", help="跳过工作环境卫生检查"
    ),
    timestamp: bool = typer.Option(
        True, "--timestamp/--no-timestamp", help="输出目录是否带时间戳"
    ),
    hotword_enabled: bool = typer.Option(
        True, "--hotword/--no-hotword", help="启用热词替换"
    ),
    hotword_mode: str = typer.Option(
        "local", "--hotword-mode", help="热词模式：local / api / hybrid"
    ),
    json_output: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
) -> None:
    """运行完整字幕生成流程

    [bold]流程：[/bold] 音频标准化 → 切段 → 语音识别 → 文本清洗 → 智能断句 → 时间轴对齐 → 字幕导出

    [bold]模式：[/bold]
      fast     — 快速模式，使用 0.6B 模型（默认）
      quality  — 高质量模式，使用 1.7B 模型

    [bold]增强：[/bold]
      off      — 关闭字幕增强
      local    — 本地规则增强（默认）
      api      — LLM API 增强（需配置 API Key）

    [bold]输出：[/bold] 精对齐默认生成 final.srt/final.vtt/final.json/final.tsv；--no-align 只生成 draft.srt/draft.json

    [bold]示例：[/bold]
      subtap run video.mp3
      subtap run video.mp3 --local-only
      subtap run video.mp3 --enhance off
      subtap run video.mp3 --enhance api
      subtap run video.mp3 --translate-to en
      subtap run input.mp3 --mode quality -o ./subtitles
    """
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if json_output and use_tui:
        typer.echo("✗ --json 需要同时使用 --no-tui", err=True)
        raise typer.Exit(1)

    if not input_path.exists():
        typer.echo(f"✗ 错误：文件未找到 {input_path}", err=True)
        raise typer.Exit(1)

    # ── 参数验证 ──────────────────────────────────────────────
    if enhance not in ("off", "local", "api"):
        typer.echo(f"✗ 错误：--enhance 必须是 off/local/api，收到：{enhance}", err=True)
        raise typer.Exit(1)

    if local_only and enhance == "api":
        typer.echo("✗ 错误：--local-only 模式下不能使用 --enhance api", err=True)
        raise typer.Exit(1)

    if local_only and translate_to:
        typer.echo("✗ 错误：--local-only 模式下不能使用 --translate-to", err=True)
        raise typer.Exit(1)

    if bilingual not in ("off", "source-first", "target-first"):
        typer.echo(
            f"✗ 错误：--bilingual 必须是 off/source-first/target-first，收到：{bilingual}",
            err=True,
        )
        raise typer.Exit(1)

    if bilingual != "off" and not translate_to:
        typer.echo("✗ 错误：--bilingual 需要同时使用 --translate-to", err=True)
        raise typer.Exit(1)

    if enhance == "api":
        typer.echo("⚠ 增强模式为 api，字幕文本将发送到外部 LLM API（音频不会发送）")

    if use_tui and not observer_child:
        event_log_path = work_dir / "run.log.jsonl"
        event_log_path.unlink(missing_ok=True)
        command = _build_observer_child_command(
            input_path=input_path,
            work_dir=work_dir,
            output_dir=output_dir,
            fmt=fmt,
            mode=mode,
            enhance=enhance,
            local_only=local_only,
            translate_to=translate_to,
            bilingual=bilingual,
            align_enabled=align_enabled,
            punctuation=punctuation,
            subtitle_language=subtitle_language,
            no_git_check=no_git_check,
            no_cleanroom=no_cleanroom,
            timestamp=timestamp,
        )
        typer.echo("▸ TUI 观察者进程已启动，推理将在独立子进程执行")
        _run_observer_parent(command, event_log_path)
        return

    if observer_child:
        use_tui = False

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    config.output.timestamp = timestamp  # CLI overrides config
    config.output.subtitle_punctuation = punctuation
    config.output.subtitle_language = subtitle_language
    config.output.max_chars = max_chars
    config.output.min_chars = min_chars
    config.output.subtitle_stem = input_path.stem

    # Mode-based model override
    if mode == "quality":
        config.asr.model = "asr_1.7b"

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

    # ── Pipeline execution ──────────────────────────────────
    from subtap.metrics.events import EventBus
    from subtap.metrics.profiler import PipelineProfiler

    # 创建 Event Bus 和 Profiler
    event_log_path = work_dir / "run.log.jsonl"
    event_log_path.unlink(missing_ok=True)
    event_bus = EventBus(log_path=event_log_path)
    pipeline.event_bus = event_bus
    profiler = PipelineProfiler(event_bus)
    profiler.wrap_pipeline(pipeline)

    if use_tui and getattr(config.asr, "backend", "") == "mlx-qwen-asr":
        typer.echo("⚠ MLX/Metal 推理与 Textual 实时界面存在兼容风险，已切换为安全进度模式")
        use_tui = False

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
            future = None

            def _start_pipeline():
                nonlocal future
                future = executor.submit(
                    _run_pipeline_safely,
                    pipeline,
                    input_path,
                    output_dir,
                    mode,
                    fmt,
                    enhance,
                    align_enabled,
                    hotword_enabled,
                )
                _exit_dashboard_when_pipeline_done(future, dashboard)

            dashboard.set_startup_callback(_start_pipeline)

            # 运行 dashboard（它会启动 async loop 处理事件）
            dashboard.run()

            # 获取结果（future.result() 会阻塞直到完成）
            try:
                if future is None:
                    raise RuntimeError("TUI 未能启动处理任务")
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
                        enhance=enhance,
                        align_enabled=align_enabled,
                        hotword_enabled=hotword_enabled,
                    )
            else:
                result = runner.run_pipeline(
                    pipeline,
                    input_path,
                    output_dir,
                    fmt=fmt,
                    enhance=enhance,
                    align_enabled=align_enabled,
                    hotword_enabled=hotword_enabled,
                )
            timings = result.get("timings", {})
        except SystemExit:
            raise
        except Exception as e:
            typer.echo(f"\n✗ 处理失败：{e}", err=True)
            raise typer.Exit(1)

    # Pipeline 执行成功后清理 L1 临时文件
    pipeline.cleanup()

    def _count_jsonl(path: Path) -> int:
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line)

    def _audio_duration_sec(path: Path) -> float:
        if not path.exists():
            return 0.0
        try:
            return float(
                json.loads(path.read_text(encoding="utf-8")).get("duration", 0)
            )
        except Exception:
            return 0.0

    from subtap.metrics.performance import build_subtitle_performance_metrics

    asr_config = getattr(config, "asr", None)
    align_config = getattr(config, "align", None)
    performance_metrics = build_subtitle_performance_metrics(
        timings=timings,
        audio_duration_sec=_audio_duration_sec(work_dir / "media_info.json"),
        chunks_total=_count_jsonl(work_dir / "chunks" / "chunks.jsonl"),
        subtitles_total=_count_jsonl(
            work_dir / "aligned.jsonl"
            if align_enabled
            else work_dir / "asr" / "asr.jsonl"
        ),
        alignment_enabled=align_enabled,
        asr_model=getattr(asr_config, "model", "asr_0.6b"),
        aligner_model=getattr(align_config, "model", "aligner"),
        quantization=getattr(asr_config, "quantization", "q8"),
        enhance_mode=enhance,
    )
    quality_payload: dict[str, Any] = {}

    # ── Generate report and debug output ────────────────────
    try:
        from subtap.quality.scorer import Scorer
        from subtap.core.report import generate_report

        # Quality assessment
        aligned_path = work_dir / "aligned.jsonl"
        if aligned_path.exists():
            scorer = Scorer(aligned_path)
            quality_report = scorer.score()
            quality_payload = {
                "quality_score": quality_report.total_score,
                "error_count": quality_report.error_count,
                "fixable_count": quality_report.fixable_count,
            }

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
                performance_metrics=performance_metrics,
            )

            # Write report
            output_dir.mkdir(parents=True, exist_ok=True)
            report_path = work_dir / "report.md"
            report_path.write_text(report_content, encoding="utf-8")
            if not json_output:
                typer.echo(f"\n▸ 质量报告：{report_path}")

            # Write debug.json
            debug_data = {
                "mode": mode,
                "input_file": str(input_path),
                "output_format": fmt,
                "alignment_enabled": align_enabled,
                "quality_score": quality_report.total_score,
                "timings": timings,
                "error_count": quality_report.error_count,
            }
            debug_path = work_dir / "debug.json"
            debug_path.write_text(
                json.dumps(debug_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
    except Exception as e:
        # Report generation is optional - don't fail the whole run
        if not json_output:
            typer.echo(f"\n⚠ 报告生成失败：{e}", err=True)

    if not align_enabled:
        from subtap.core.report import format_performance_summary

        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = work_dir / "report.md"
        report_path.write_text(
            "# Subtap 运行报告\n\n"
            "## 对齐状态\n\n"
            "未精对齐，仅适合粗剪预览；本次未生成 final.srt。\n\n"
            f"{format_performance_summary(performance_metrics)}\n"
            "## 输出\n\n"
            "- draft.srt\n"
            "- draft.json\n",
            encoding="utf-8",
        )
        debug_path = output_dir / "debug.json"
        debug_path.write_text(
            json.dumps(
                {
                    "mode": mode,
                    "input_file": str(input_path),
                    "output_format": "draft",
                    "alignment_enabled": False,
                    "timings": timings | {"align": 0},
                    "draft_output": str(output_dir / "draft.srt"),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if not json_output:
            typer.echo(f"\n▸ 草稿报告：{report_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_payload = performance_metrics | {
        "output_contract": "final" if align_enabled else "draft"
    }
    (work_dir / "metrics.json").write_text(
        json.dumps(metrics_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    try:
        from subtap.core.report import format_output_contract_summary
        from subtap.output.contract import write_contract_artifacts
        from subtap.quality.sample_picker import pick_manual_review_segments

        write_contract_artifacts(work_dir, output_dir, quality=quality_payload)
        output_files = [
            path.name
            for path in [
                output_dir / "final.srt",
                output_dir / "final.vtt",
                output_dir / "final.json",
                output_dir / "final.tsv",
                output_dir / "draft.srt",
                output_dir / "draft.json",
                work_dir / "report.md",
                work_dir / "metrics.json",
                work_dir / "run.log.jsonl",
            ]
            if path.exists()
        ]
        final_json = output_dir / "final.json"
        subtitles = (
            json.loads(final_json.read_text(encoding="utf-8"))
            if final_json.exists()
            else []
        )
        manual_samples = pick_manual_review_segments(
            subtitles, slow_chunks=performance_metrics["slow_chunks"]
        )
        report_path = work_dir / "report.md"
        if report_path.exists():
            report_path.write_text(
                report_path.read_text(encoding="utf-8")
                + "\n"
                + format_output_contract_summary(output_files, manual_samples),
                encoding="utf-8",
            )
    except Exception as e:
        if not json_output:
            typer.echo(f"\n⚠ 输出契约补充失败：{e}", err=True)

    if json_output:
        output_path = output_dir / ("final.srt" if align_enabled else "draft.srt")
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "input_path": str(input_path),
                    "work_dir": str(work_dir),
                    "output_dir": str(output_dir),
                    "output_path": str(output_path),
                    "alignment_enabled": align_enabled,
                    "report_path": str(work_dir / "report.md"),
                    "debug_path": str(work_dir / "debug.json"),
                    "timings": timings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


@app.command("observe")
def observe(
    log_path: Path = typer.Argument(..., help="pipeline 事件日志 run.log.jsonl"),
) -> None:
    """观察已运行或正在运行的任务事件日志。"""
    if not log_path.exists():
        typer.echo(f"✗ 日志文件不存在：{log_path}", err=True)
        raise typer.Exit(1)

    from subtap.ui.observer import summarize_event_log

    state = summarize_event_log(log_path)
    typer.echo("Subtap 观察者")
    typer.echo(f"当前阶段：{state['stage']}")
    typer.echo(f"进度：{state['progress']}%")
    typer.echo(f"当前 Chunk：{state['chunk_id']}")
    typer.echo(f"当前模型：{state['model']}")
    typer.echo(f"ASR 草稿：{state['asr_drafts']}  已对齐：{state['aligned']}")


# ── 单阶段命令 ─────────────────────────────────────────────


@app.command("batch-transcribe")
def batch_transcribe(
    args: list[str] = typer.Argument(None, help="输入文件路径（支持拖入）"),
    directory: str = typer.Option(None, "--dir", "-d", help="扫描目录中的媒体文件"),
    configure: bool = typer.Option(False, "--configure", help="运行配置向导"),
    no_confirm: bool = typer.Option(
        False, "--no-confirm", "-y", help="跳过确认"
    ),
    files: str = typer.Option(None, "--files", "-f", help="输入文件，逗号分隔"),
    output_dir: Path = typer.Option(
        Path("./output"), "--output-dir", "-o", help="输出目录"
    ),
    mode: str | None = typer.Option(None, "--mode", "-m", help="fast / quality"),
    enhance: str | None = typer.Option(
        None, "--enhance", "-e", help="字幕增强模式：off / local / api"
    ),
    translate_to: str | None = typer.Option(
        None, "--translate-to", help="翻译目标语言：en / ja / zh"
    ),
    bilingual: str | None = typer.Option(
        None,
        "--bilingual",
        help="双语字幕顺序：off / source-first / target-first",
    ),
    max_chars: int | None = typer.Option(
        None, "--max-chars", help="每行字幕最大字符数（10-60）", min=10, max=60
    ),
    min_chars: int | None = typer.Option(
        None, "--min-chars", help="每行字幕最小字符数（4-30）", min=4, max=30
    ),
    punctuation: bool | None = typer.Option(
        None, "--punctuation", help="字幕带标点符号（默认不带）"
    ),
    subtitle_language: str | None = typer.Option(
        None, "--subtitle-language", help="字幕输出语种（zh/en/ja）"
    ),
    no_align: bool | None = typer.Option(None, "--no-align", help="跳过对齐阶段"),
    concurrency: int = typer.Option(
        1, "--concurrency", "-c", help="并发处理数（最大 4）（尚未实现）", min=1, max=4, hidden=True
    ),
    resume: Path | None = typer.Option(
        None, "--resume", help="恢复中断的任务（传入 manifest.json 路径）"
    ),
    retry_failed: Path | None = typer.Option(
        None, "--retry-failed", help="重试失败的文件（传入 manifest.json 路径）"
    ),
    json_output: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
) -> None:
    """批量转录多个媒体文件。

    支持将文件拖入终端或手动输入路径。首次运行会显示配置向导。

    [bold]示例：[/bold]
      subtap batch-transcribe a.mp4 b.mp4 c.mp4
      subtap batch-transcribe --files a.mp4,b.mp4,c.mp4
      subtap batch-transcribe --dir /path/to/media
      subtap batch-transcribe --configure
      subtap batch-transcribe --files a.mp4,b.mp4 --mode quality --translate-to en
      subtap batch-transcribe --resume output/manifest.json
      subtap batch-transcribe --retry-failed output/manifest.json
      subtap batch-transcribe --files a.mp4,b.mp4 --json
    """
    import time
    from datetime import datetime, timezone

    from subtap.batch import (
        PIPELINE_STAGES,
        build_manifest,
        get_failed_items,
        get_pending_items,
        load_manifest,
        make_item,
        parse_files,
        write_manifest,
    )
    from subtap.batch_abort import AbortController
    from subtap.batch_progress import (
        JsonProgressWriter,
        print_progress_footer,
        print_progress_header,
        print_progress_item,
    )
    from subtap.core.pipeline import Pipeline
    from subtap.schemas.config import load_config
    from subtap.ui.tui import PlainRunner

    # ── 参数冲突检查 ──────────────────────────────────────────
    if resume and retry_failed:
        typer.echo("✗ 错误：--resume 和 --retry-failed 不能同时使用", err=True)
        raise typer.Exit(1)

    if (resume or retry_failed) and (files or args or directory):
        typer.echo(
            "✗ 错误：--resume/--retry-failed 不能与输入文件同时使用", err=True
        )
        raise typer.Exit(1)

    # ── 配置向导 ──────────────────────────────────────────────
    from subtap.batch_config import load_batch_config
    from subtap.batch_interactive import (
        collect_files,
        confirm_files,
        run_config_wizard,
        validate_files,
    )

    config_path = Path.home() / ".subtap" / "batch-config.yaml"

    if configure or (not config_path.exists() and not json_output):
        batch_config = run_config_wizard(config_path)
    else:
        batch_config = load_batch_config(config_path)

    # 使用配置文件的值作为默认值（CLI 参数优先）
    if mode is None:
        mode = batch_config.mode
    if enhance is None:
        enhance = batch_config.enhance
    if translate_to is None:
        translate_to = batch_config.translate_to
    if bilingual is None:
        bilingual = batch_config.bilingual
    if max_chars is None:
        max_chars = batch_config.max_chars
    if min_chars is None:
        min_chars = batch_config.min_chars
    if punctuation is None:
        punctuation = batch_config.punctuation
    if subtitle_language is None:
        subtitle_language = batch_config.subtitle_language
    if no_align is None:
        no_align = False

    if bilingual != "off" and not translate_to:
        typer.echo("✗ 错误：--bilingual 需要同时使用 --translate-to", err=True)
        raise typer.Exit(1)

    # ── 收集文件（支持多种方式）─────────────────────────────────
    if not resume and not retry_failed:
        collected = collect_files(args, directory)

        # 兼容旧的 --files 参数
        if files:
            collected.extend(parse_files(files))

        if not collected:
            typer.echo("✗ 未找到媒体文件", err=True)
            raise typer.Exit(1)

        # 验证文件（仅用于确认提示，不预过滤——让处理循环记录失败）
        valid, invalid = validate_files(collected)
        if invalid and not json_output:
            for f in invalid:
                typer.echo(f"⚠ 文件不存在：{f}", err=True)

        # 确认（--json 或 --no-confirm 时跳过）
        if not no_confirm and not json_output:
            if not confirm_files(collected):
                typer.echo("已取消")
                return

    # ── 加载配置 ──────────────────────────────────────────────
    config = load_config(Path.home() / ".subtap" / "config.yaml")
    config.output.timestamp = True
    config.output.subtitle_punctuation = punctuation
    config.output.subtitle_language = subtitle_language
    config.output.max_chars = max_chars
    config.output.min_chars = min_chars
    config.output.subtitle_stem = "batch"

    if mode == "quality":
        config.asr.model = "asr_1.7b"

    # ── 恢复或重试模式 ──────────────────────────────────────
    if resume or retry_failed:
        manifest_path = resume or retry_failed
        if not manifest_path.exists():
            typer.echo(f"✗ manifest 文件不存在：{manifest_path}", err=True)
            raise typer.Exit(1)

        manifest = load_manifest(manifest_path)
        output_dir = Path(manifest["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        if resume:
            items_to_process = get_pending_items(manifest["items"])
            typer.echo(f"▸ 恢复模式：跳过 {manifest['succeeded']} 个成功文件")
        else:
            items_to_process = get_failed_items(manifest["items"])
            typer.echo(f"▸ 重试模式：重试 {len(items_to_process)} 个失败文件")

        if not items_to_process:
            typer.echo("✓ 没有需要处理的文件")
            return

        # 重置待处理项状态并清理 work/ 目录
        import shutil

        for item in items_to_process:
            item["status"] = "pending"
            item["error"] = ""
            for stage in item.get("stages", {}).values():
                if isinstance(stage, dict):
                    stage["status"] = "pending"
            # I4 fix: 清理失败/中断文件的 work/ 目录，防止读到脏数据
            work_dir = Path(item["output_dir"]) / "work"
            if work_dir.exists():
                shutil.rmtree(work_dir)

        items = manifest["items"]
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        items = [make_item(p, output_dir) for p in collected]

    # ── 构建参数快照 ──────────────────────────────────────────
    params = {
        "mode": mode,
        "enhance": enhance,
        "translate_to": translate_to,
        "bilingual": bilingual,
        "max_chars": max_chars,
        "min_chars": min_chars,
        "punctuation": punctuation,
        "subtitle_language": subtitle_language,
        "concurrency": concurrency,
        "align_enabled": not no_align,
    }

    # ── 初始化中止控制器 ──────────────────────────────────────
    abort_controller = AbortController(output_dir)
    # 清理旧的 abort 标记
    abort_controller.cleanup()
    abort_controller.install_signal_handler()

    # ── 初始化进度显示 ──────────────────────────────────────
    # I2 fix: 记录任务真正开始时间，后续调用复用
    task_created_at = datetime.now(timezone.utc).isoformat()

    json_writer = JsonProgressWriter() if json_output else None
    total = len(items)
    manifest_path = output_dir / "manifest.json"

    if json_writer:
        json_writer.write_start(total, mode, created_at=task_created_at)
    else:
        print_progress_header(total, mode)

    # ── 写入初始 manifest ──────────────────────────────────────
    write_manifest(
        manifest_path,
        build_manifest(output_dir, mode, items, params, created_at=task_created_at),
    )

    # ── 处理文件 ──────────────────────────────────────────────
    start_time = time.time()

    for index, item in enumerate(items, start=1):
        # 检查中止
        if abort_controller.is_aborted():
            if item["status"] in ("pending", "running"):
                item["status"] = "interrupted"
                item["error"] = "用户中止"
            continue

        # 跳过已成功的文件
        if item["status"] == "succeeded":
            continue

        path = Path(item["input_path"])
        item_output_dir = Path(item["output_dir"])
        filename = path.name

        # 文件不存在
        if not path.exists():
            item["status"] = "failed"
            item["error"] = "文件不存在"
            if json_writer:
                json_writer.write_item_complete(
                    index, filename, "failed", error="文件不存在"
                )
            else:
                print_progress_item(index, total, filename, "failed")
            write_manifest(
                manifest_path, build_manifest(output_dir, mode, items, params, created_at=task_created_at)
            )
            continue

        # 开始处理
        item["status"] = "running"
        item["stages"] = {s: {"status": "pending"} for s in PIPELINE_STAGES}

        if json_writer:
            json_writer.write_item_start(index, filename)
        else:
            print_progress_item(index, total, filename, "running")

        write_manifest(manifest_path, build_manifest(output_dir, mode, items, params, created_at=task_created_at))

        # C1 fix: stage_start 移到 try 之前，防止 UnboundLocalError
        stage_start = time.time()

        try:
            # 配置 Pipeline
            item_config = load_config(Path.home() / ".subtap" / "config.yaml")
            item_config.output.timestamp = True
            item_config.output.subtitle_punctuation = punctuation
            item_config.output.subtitle_language = subtitle_language
            item_config.output.max_chars = max_chars
            item_config.output.min_chars = min_chars
            item_config.output.subtitle_stem = path.stem

            if mode == "quality":
                item_config.asr.model = "asr_1.7b"

            pipeline = Pipeline(item_config, work_dir=item_output_dir / "work")
            pipeline.workspace.ensure_dirs()

            # 运行 Pipeline
            runner = PlainRunner()

            if json_output:
                with redirect_stdout(StringIO()):
                    meta = runner.run_pipeline(
                        pipeline,
                        path,
                        item_output_dir,
                        enhance=enhance,
                        align_enabled=not no_align,
                        hotword_enabled=True,
                    )
            else:
                meta = runner.run_pipeline(
                    pipeline,
                    path,
                    item_output_dir,
                    enhance=enhance,
                    align_enabled=not no_align,
                    hotword_enabled=True,
                )

            # 记录成功
            item["status"] = "succeeded"
            item["duration"] = time.time() - stage_start
            item["meta"] = meta

            # 更新阶段状态
            timings = meta.get("timings", {})
            for stage_name in item.get("stages", {}):
                if stage_name in timings:
                    item["stages"][stage_name] = {
                        "status": "done",
                        "duration": round(timings[stage_name], 2),
                    }
                elif no_align and stage_name == "align":
                    item["stages"][stage_name] = {
                        "status": "skipped",
                        "reason": "--no-align",
                    }

            if json_writer:
                json_writer.write_item_complete(
                    index, filename, "succeeded", item["duration"]
                )
            else:
                print_progress_item(
                    index, total, filename, "succeeded", duration=item["duration"]
                )

            # 成功处理后清理 L2 中间文件
            from subtap.engine.cleanroom import Cleanroom
            cleanroom = Cleanroom(item_output_dir / "work")
            cleanroom.clean_intermediate_files()

        except Exception as e:
            item["status"] = "failed"
            item["error"] = str(e)
            item["duration"] = time.time() - stage_start

            # 标记失败的阶段
            for stage_name, stage_info in item.get("stages", {}).items():
                if isinstance(stage_info, dict) and stage_info.get("status") == "running":
                    stage_info["status"] = "failed"
                    stage_info["error"] = str(e)

            if json_writer:
                json_writer.write_item_complete(
                    index, filename, "failed", error=str(e)
                )
            else:
                print_progress_item(index, total, filename, "failed")

        write_manifest(manifest_path, build_manifest(output_dir, mode, items, params, created_at=task_created_at))

    # ── 完成 ──────────────────────────────────────────────────
    total_duration = time.time() - start_time
    abort_controller.restore_signal_handler()
    abort_controller.cleanup()

    # 更新完成时间
    manifest = build_manifest(output_dir, mode, items, params, created_at=task_created_at)
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest["duration"] = total_duration
    write_manifest(manifest_path, manifest)

    if json_writer:
        json_writer.write_complete(
            manifest["ok"],
            manifest["total"],
            manifest["succeeded"],
            manifest["failed"],
            manifest["interrupted"],
            total_duration,
        )
    else:
        print_progress_footer(
            manifest["total"],
            manifest["succeeded"],
            manifest["failed"],
            manifest["interrupted"],
            total_duration,
        )
        typer.echo(f"\n▸ 批量任务清单：{manifest_path}")


@app.command("compose")
def compose_subtitle(
    video: Path = typer.Argument(..., help="输入视频文件"),
    subtitle: Path = typer.Option(..., "--subtitle", "-s", help="字幕文件 SRT/ASS"),
    output: Path = typer.Option(..., "--output", "-o", help="输出视频路径"),
    overwrite: bool = typer.Option(False, "--overwrite", help="覆盖已存在输出文件"),
) -> None:
    """把字幕烧录进单个视频。"""
    from subtap.compose import compose_one

    result = compose_one(video, subtitle, output, overwrite=overwrite)
    if result["status"] != "succeeded":
        typer.echo(f"✗ 合成失败：{result['error']}", err=True)
        raise typer.Exit(1)
    typer.echo(f"✓ 合成完成：{output}")


@app.command("batch-compose")
def batch_compose_subtitle(
    items: Path = typer.Option(..., "--items", help="JSON 文件：[{video, subtitle}]"),
    output_dir: Path = typer.Option(
        Path("./output/composed"), "--output-dir", "-o", help="输出目录"
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="覆盖已存在输出文件"),
    json_output: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
) -> None:
    """批量把字幕烧录进视频。"""
    from subtap.compose import compose_batch

    if not items.exists():
        typer.echo(f"✗ 批量合成清单不存在：{items}", err=True)
        raise typer.Exit(1)
    payload = json.loads(items.read_text(encoding="utf-8"))
    manifest = compose_batch(payload, output_dir, overwrite=overwrite)
    if json_output:
        typer.echo(json.dumps(manifest, ensure_ascii=False, indent=2))
        return
    typer.echo(f"▸ 批量合成清单：{output_dir / 'compose-manifest.json'}")
    for item in manifest["items"]:
        icon = "✓" if item["status"] == "succeeded" else "✗"
        typer.echo(f"  {icon} {item['video']} — {item['status']}")


@script_app.command("match")
def script_match(
    timeline: Path = typer.Option(..., "--timeline", help="已有时间轴 JSONL"),
    script: Path = typer.Option(..., "--script", help="文稿文本文件"),
    output: Path = typer.Option(..., "--output", "-o", help="输出 JSONL"),
    follow_script_lines: bool = typer.Option(
        False,
        "--follow-script-lines/--keep-subtitle-lines",
        help="按文稿行数重排；默认保持原字幕段数和时间轴",
    ),
) -> None:
    """按顺序用文稿替换已有时间轴文本。"""
    from subtap.script.match import (
        build_match_report,
        format_script,
        match_script_lines,
    )

    if not timeline.exists():
        typer.echo(f"✗ 时间轴文件不存在：{timeline}", err=True)
        raise typer.Exit(1)
    if not script.exists():
        typer.echo(f"✗ 文稿文件不存在：{script}", err=True)
        raise typer.Exit(1)

    segments = [
        json.loads(line)
        for line in timeline.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lines = format_script(script.read_text(encoding="utf-8"))
    mode = "follow_script" if follow_script_lines else "keep_subtitle"
    matched = match_script_lines(segments, lines, mode=mode)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in matched) + "\n",
        encoding="utf-8",
    )
    report_path = output.with_name("matched_report.md")
    report_path.write_text(
        build_match_report(
            segments_total=len(segments),
            script_lines_total=len(lines),
            output_total=len(matched),
            mode=mode,
        ),
        encoding="utf-8",
    )
    typer.echo(f"✓ 已输出：{output}")
    typer.echo(f"▸ 文稿匹配报告：{report_path}")


@script_app.command("format")
def script_format(
    script: Path = typer.Option(..., "--script", help="文稿文本文件"),
) -> None:
    """清理文稿空行、标题和备注后输出到终端。"""
    from subtap.script.match import format_script

    if not script.exists():
        typer.echo(f"✗ 文稿文件不存在：{script}", err=True)
        raise typer.Exit(1)
    for line in format_script(script.read_text(encoding="utf-8")):
        typer.echo(line)


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


@app.command(help="运行演示：默认本地不联网，输出 demo final.srt")
def demo(
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
        )
    except SystemExit:
        raise
    except Exception as e:
        typer.echo(f"\n✗ 演示失败：{e}", err=True)
        raise typer.Exit(1)

    # 显示示例 SRT 内容
    srt_path = output_dir / "final.srt"
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


@app.command("clean")
def clean_workspace(
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
    - report.md, metrics.json（用户输出）
    - output/ 目录（用户输出）
    """
    from subtap.engine.cleanroom import Cleanroom

    if not work_dir.exists():
        typer.echo(f"✗ 工作目录不存在：{work_dir}", err=True)
        raise typer.Exit(1)

    cleanroom = Cleanroom(work_dir)

    if all:
        result = cleanroom.clean_all()
    else:
        result = cleanroom.clean_temp_files()

    # 使用 format_summary() 显示清理结果
    summary = cleanroom.format_summary(result)
    typer.echo(summary)


if __name__ == "__main__":
    app()
