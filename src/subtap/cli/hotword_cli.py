"""热词管理子命令组."""

from __future__ import annotations

import subprocess
import platform
from pathlib import Path

import typer

hotword_app = typer.Typer(help="热词管理")


def _default_path() -> Path:
    return Path.home() / ".subtap" / "glossaries" / "default.yaml"


@hotword_app.command("add")
def hotword_add(
    word: str = typer.Argument(..., help="热词（正确写法）"),
    aliases: str = typer.Argument(..., help="错词（逗号分隔）"),
    lang: str = typer.Option("zh", "--lang", "-l", help="语言"),
) -> None:
    """添加热词"""
    from subtap.glossary.hotword import (
        Hotword,
        load_glossary,
        save_glossary,
    )

    path = _default_path()
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

    path = _default_path()
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

    path = _default_path()
    glossary = load_glossary(path, lang)
    glossary.remove(word)
    save_glossary(glossary, path)
    typer.echo(f"✓ 已删除热词：{word}")


@hotword_app.command("edit")
def hotword_edit(
    lang: str = typer.Option("zh", "--lang", "-l", help="语言"),
) -> None:
    """编辑热词（用默认应用打开）"""
    path = _default_path()

    if not path.exists():
        from subtap.glossary.hotword import HotwordGlossary, save_glossary

        save_glossary(HotwordGlossary(lang=lang), path)

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
