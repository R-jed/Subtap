"""Subtap CLI — 中文优先字幕生成引擎入口."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

import typer

from subtap import __version__
from subtap.cli._utils import _handle_error
from subtap.cli.batch_cli import (
    batch_compose_subtitle,
    batch_transcribe,
    compose_subtitle,
)
from subtap.cli.doctor_cli import doctor
from subtap.cli.hotword_cli import hotword_app
from subtap.cli.models_cli import models_app
from subtap.cli.pipeline_cli import (
    _align as align_cmd,
    _clean as clean_cmd,
    _clean_workspace as clean_workspace_cmd,
    _demo as demo_cmd,
    _export as export_cmd,
    _prepare as prepare_cmd,
    _resume as resume_cmd,
    _retry as retry_cmd,
    _run as run_cmd,
    _segment as segment_cmd,
    _transcribe as transcribe_cmd,
    check_first_run_wizard as check_first_run_wizard,
)
from subtap.cli.script_cli import script_app
from subtap.cli.setup_cli import setup
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


def _choose_command_deck_path(action: str) -> Path | None:
    """Choose a run input using the native macOS picker."""
    scripts = {
        "run": 'POSIX path of (choose file with prompt "选择音频或视频文件")',
        "observe": 'POSIX path of (choose file with prompt "选择 run.log.jsonl")',
        "batch": 'POSIX path of (choose folder with prompt "选择媒体文件夹")',
    }
    result = subprocess.run(
        ["osascript", "-e", scripts[action]],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        if "(-128)" in result.stderr:
            return None
        _handle_error(f"无法打开文件选择器：{result.stderr.strip()}")
    selected = result.stdout.strip()
    return Path(selected) if selected else None


def _run_command(command: list[str]) -> None:
    result = subprocess.run(command)
    if result.returncode:
        raise typer.Exit(result.returncode)


def _run_subtap_command(*args: str) -> None:
    _run_command([sys.executable, "-m", "subtap.cli", *args])


def _handle_command_deck_action(action: str | None) -> None:
    """Handle a Command Deck result."""
    if action == "version":
        version()
        return
    if action == "output":
        output_dir = Path.cwd() / "output"
        output_dir.mkdir(exist_ok=True)
        result = subprocess.run(["open", str(output_dir)])
        if result.returncode:
            raise typer.Exit(result.returncode)
        return
    if action in {"run", "observe", "batch"}:
        selected = _choose_command_deck_path(action)
        if selected is None:
            return
        if action == "run":
            from subtap.ui.textual_run_setup import RunSetupApp

            command = RunSetupApp(selected).run()
            if command is None:
                return
            _run_command(command)
        elif action == "observe":
            _run_subtap_command("observe", str(selected))
        else:
            _run_subtap_command("batch-transcribe", "--dir", str(selected))
        return
    if action == "doctor":
        _run_subtap_command("doctor")
    elif action == "setup":
        _run_subtap_command("setup")
    elif action is not None:
        _handle_error(f"未知操作：{action}")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Subtap command entry."""
    if ctx.invoked_subcommand is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            from subtap.ui.command_deck import CommandDeckApp

            _handle_command_deck_action(CommandDeckApp().run())
            return
        typer.echo(_build_root_command_deck())


learn_app = typer.Typer(help="学习人工修正")
profile_app = typer.Typer(help="本地学习档案")

glossary_app.add_typer(hotword_app, name="hotword")
app.add_typer(script_app, name="script")
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
    from subtap.core.migration import execute_migration, plan_migration
    from subtap.core.safe_delete import ensure_directory_structure
    from subtap.core.state_store import StateStore

    home = Path.home()
    subtap_dir = home / ".subtap"
    config_path = subtap_dir / "config.yaml"
    db_path = subtap_dir / "subtap.db"

    # 1. 创建新目录结构
    dirs = ensure_directory_structure(subtap_dir)

    # 2. 迁移旧布局（仅在旧结构存在时执行）
    plan = plan_migration(subtap_dir)
    if plan.moves:
        execute_migration(plan, subtap_dir)
        typer.echo(f"✓ 已迁移旧目录布局：{len(plan.moves)} 个文件迁移")

    # 3. 初始化 state.json
    StateStore(subtap_dir / "state.json").load()

    # 4. 复制默认配置（保留向后兼容）
    if not config_path.exists():
        default_config = (
            Path(__file__).resolve().parents[2] / "configs" / "default.yaml"
        )
        if default_config.exists():
            shutil.copy2(default_config, config_path)
        else:
            config_path.write_text("# Subtap 配置\n")

    # 5. 初始化兼容数据库与默认热词库
    if not db_path.exists():
        db_path.touch()

    from subtap.core.user_resources import ensure_default_glossary

    ensure_default_glossary(subtap_dir)

    typer.echo(f"✓ 工作空间已初始化：{subtap_dir}")
    typer.echo(f"  配置文件：{config_path}")
    typer.echo(f"  术语表：  {dirs['glossaries']}")
    typer.echo(f"  数据库：  {db_path}")
    typer.echo(f"  状态文件：{subtap_dir / 'state.json'}")


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


app.command("doctor")(doctor)


app.command("setup")(setup)


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
    from subtap.ui.command_deck import CommandDeckApp

    _handle_command_deck_action(CommandDeckApp().run())


app.command("batch-transcribe")(batch_transcribe)
app.command("compose")(compose_subtitle)
app.command("batch-compose")(batch_compose_subtitle)


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


app.add_typer(models_app, name="models")


if __name__ == "__main__":
    app()
