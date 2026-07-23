"""热词管理子命令组."""

from __future__ import annotations

import subprocess
import platform
from pathlib import Path

import typer

hotword_app = typer.Typer(help="热词管理")


def _default_path() -> Path:
    from subtap.core.user_resources import default_glossary_path

    return default_glossary_path()


@hotword_app.command("add")
def hotword_add(
    word: str = typer.Argument(..., help="热词（正确写法）"),
    aliases: str = typer.Argument(..., help="错词（逗号分隔）"),
    lang: str = typer.Option("zh", "--lang", "-l", help="语言"),
) -> None:
    """添加热词"""
    from subtap.core.user_resources import ensure_default_glossary
    from subtap.schemas.glossary import (
        GlossaryTerm,
        upsert_plain_glossary_terms,
    )

    path = ensure_default_glossary()
    upsert_plain_glossary_terms(
        path,
        [
            GlossaryTerm(
                canonical=word,
                aliases=[a.strip() for a in aliases.split(",")],
            )
        ],
    )
    typer.echo(f"✓ 已添加热词：{word} = {aliases}")


@hotword_app.command("list")
def hotword_list(
    lang: str = typer.Option("zh", "--lang", "-l", help="语言"),
) -> None:
    """查看热词"""
    from subtap.core.user_resources import ensure_default_glossary
    from subtap.glossary.hotword import load_glossary

    path = ensure_default_glossary()
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
    from subtap.core.user_resources import ensure_default_glossary
    from subtap.schemas.glossary import remove_plain_glossary_entry

    path = ensure_default_glossary()
    remove_plain_glossary_entry(path, word)
    typer.echo(f"✓ 已删除热词：{word}")


@hotword_app.command("edit")
def hotword_edit(
    lang: str = typer.Option("zh", "--lang", "-l", help="语言"),
) -> None:
    """编辑热词（用默认应用打开）"""
    from subtap.core.user_resources import ensure_default_glossary

    path = ensure_default_glossary()

    _open_file_cross_platform(path)
    typer.echo(f"✓ 已打开 {path}")


def _open_file_cross_platform(path: Path) -> None:
    """跨平台打开文件，使用系统默认应用。"""
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(path)], check=True)
    elif system == "Linux":
        subprocess.run(["xdg-open", str(path)], check=True)
    elif system == "Windows":
        subprocess.run(["start", str(path)], shell=True, check=True)
    else:
        raise RuntimeError(f"不支持的操作系统：{system}，请手动打开：{path}")
