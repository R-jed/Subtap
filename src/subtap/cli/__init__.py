"""Subtap CLI — 中文优先字幕生成引擎入口."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer

from subtap import __version__
from subtap.cli._utils import _handle_error
from subtap.glossary.cli import app as glossary_app

app = typer.Typer(
    name="subtap",
    help="Subtap — 本地优先的 AI 字幕生成引擎",
    no_args_is_help=False,
    rich_markup_mode="rich",
)
app.add_typer(glossary_app, name="glossary")


def _build_observer_child_command(argv: list[str]) -> list[str]:
    """Build child run command for observer-parent mode."""
    args = [arg for arg in argv[1:] if arg != "--tui"]
    return [sys.executable, "-m", "subtap.cli", *args, "--observer-child", "--no-tui"]


def _build_root_command_deck() -> str:
    """Render the root Command Deck menu."""
    from subtap.ui.command_deck import build_root_command_deck

    return build_root_command_deck()


def _command_deck_hint(action: str | None) -> str:
    """Return a short follow-up command hint after interactive selection."""
    hints = {
        "run": "运行：subtap run <音频文件> --tui",
        "observe": "观察：subtap observe <work/run.log.jsonl>",
        "batch": "批量：subtap batch-transcribe --dir <媒体文件夹>",
        "doctor": "诊断：subtap doctor",
        "config": "配置：subtap setup",
        "output": "输出目录：./output",
        "version": "版本：subtap version",
    }
    return hints.get(action or "", "")


def _handle_command_deck_action(action: str | None) -> None:
    """Handle a Command Deck result."""
    if action == "version":
        version()
        return
    hint = _command_deck_hint(action)
    if hint:
        typer.echo(hint)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Subtap command entry."""
    if ctx.invoked_subcommand is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            from subtap.ui.command_deck import CommandDeckApp

            try:
                _handle_command_deck_action(CommandDeckApp().run())
                return
            except RuntimeError:
                pass
        typer.echo(_build_root_command_deck())


# ── Glossary 热词命令 ──────────────────────────────────────────
from subtap.cli.hotword_cli import hotword_app

glossary_app.add_typer(hotword_app, name="hotword")


# ── Script 文稿匹配命令 ────────────────────────────────────────
from subtap.cli.script_cli import script_app

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
        _handle_error(f"文件不存在：{corrected_srt}")

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
            "warmup": False,  # 预热功能未启用
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


@app.command("observe")
def observe(
    log_path: Path = typer.Argument(..., help="pipeline 事件日志 run.log.jsonl"),
) -> None:
    """观察已运行或正在运行的任务事件日志。"""
    if not log_path.exists():
        _handle_error(f"日志文件不存在：{log_path}")

    from subtap.ui.observer import build_command_deck_text, summarize_event_log

    state = summarize_event_log(log_path)
    typer.echo(build_command_deck_text(state))


@app.command()
def tui() -> None:
    """启动交互式终端界面"""
    from subtap.ui.tui_app import TuiApp

    app = TuiApp()
    app.run()


# ── Batch 批量处理命令 ──────────────────────────────────────
# 函数实现位于 subtap.cli.batch_cli，此处注册到主 app
from subtap.cli.batch_cli import batch_transcribe, compose_subtitle, batch_compose_subtitle

app.command("batch-transcribe")(batch_transcribe)
app.command("compose")(compose_subtitle)
app.command("batch-compose")(batch_compose_subtitle)


# ── Pipeline 核心命令 ──────────────────────────────────────
# 函数实现位于 subtap.cli.pipeline_cli，此处注册到主 app
from subtap.cli.pipeline_cli import (
    check_first_run_wizard,
    _run as run_cmd,
    _prepare as prepare_cmd,
    _transcribe as transcribe_cmd,
    _clean as clean_cmd,
    _segment as segment_cmd,
    _align as align_cmd,
    _export as export_cmd,
    _resume as resume_cmd,
    _retry as retry_cmd,
    _demo as demo_cmd,
    _clean_workspace as clean_workspace_cmd,
)

app.command("run")(run_cmd)
app.command("prepare")(prepare_cmd)
app.command("transcribe")(transcribe_cmd)
app.command("clean")(clean_cmd)
app.command("segment")(segment_cmd)
app.command("align")(align_cmd)
app.command("export")(export_cmd)
app.command("resume")(resume_cmd)
app.command("retry")(retry_cmd)
app.command("demo", help="运行演示：默认本地不联网，输出 demo final.srt")(demo_cmd)
app.command("cleanup")(clean_workspace_cmd)


# ── Models 子命令组 ────────────────────────────────────────
from subtap.cli.models_cli import models_app

app.add_typer(models_app, name="models")


if __name__ == "__main__":
    app()
