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


# ── 子命令组 ──────────────────────────────────────────────────
from subtap.cli.hotword_cli import hotword_app
from subtap.cli.script_cli import script_app

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
from subtap.cli.doctor_cli import doctor

app.command("doctor")(doctor)


# ── Setup 命令 ─────────────────────────────────────────────
from subtap.cli.setup_cli import setup

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
    from subtap.ui.tui_app import TuiApp

    app = TuiApp()
    app.run()


# ── Batch 批量处理命令 ──────────────────────────────────────
# 函数实现位于 subtap.cli.batch_cli，此处注册到主 app
from subtap.cli.batch_cli import (
    batch_transcribe,
    compose_subtitle,
    batch_compose_subtitle,
)

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
