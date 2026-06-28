"""Glossary CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml

from subtap.schemas.glossary import Glossary, GlossaryReplacement, load_glossary

app = typer.Typer(help="热词/术语管理")


def _default_path() -> Path:
    return Path.home() / ".subtap" / "profile" / "glossary.yaml"


def _save_glossary(path: Path, glossary: Glossary) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = glossary.model_dump(mode="json")
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


@app.command("list")
def list_glossary(
    path: Path = typer.Option(_default_path(), "--file", "-f", help="术语文件路径"),
) -> None:
    """列出当前术语。"""
    glossary = load_glossary(path)
    if not glossary.terms and not glossary.replacements:
        typer.echo("暂无术语")
        return
    for term in glossary.terms:
        aliases = ",".join(term.aliases)
        typer.echo(f"{term.canonical}: {aliases}" if aliases else term.canonical)
    for replacement in glossary.replacements:
        typer.echo(f"{replacement.find} -> {replacement.replace}")


@app.command("add")
def add_glossary(
    input_text: str = typer.Option(..., "--input", help="格式：术语=别名1,别名2"),
    path: Path = typer.Option(_default_path(), "--file", "-f", help="术语文件路径"),
) -> None:
    """添加一条术语。"""
    if "=" not in input_text:
        typer.echo("✗ 格式错误：请使用 错词=正确词", err=True)
        raise typer.Exit(1)
    find, replace = [part.strip() for part in input_text.split("=", 1)]
    glossary = load_glossary(path)
    glossary.replacements.append(GlossaryReplacement(find=find, replace=replace))
    _save_glossary(path, glossary)
    typer.echo(f"✓ 已添加：{input_text}")


@app.command("remove")
def remove_glossary(
    find: str = typer.Argument(..., help="要删除的错词或术语"),
    path: Path = typer.Option(_default_path(), "--file", "-f", help="术语文件路径"),
) -> None:
    """删除一条术语。"""
    glossary = load_glossary(path)
    before = len(glossary.replacements)
    glossary.replacements = [
        item for item in glossary.replacements if item.find != find
    ]
    _save_glossary(path, glossary)
    if len(glossary.replacements) == before:
        typer.echo("未找到匹配术语")
    else:
        typer.echo(f"✓ 已删除：{find}")


@app.command("import")
def import_glossary(
    path: Path = typer.Option(..., "--file", "-f", help="术语文件路径"),
) -> None:
    """从文件导入术语。"""
    glossary = load_glossary(path)
    count = len(glossary.terms) + len(glossary.replacements)
    typer.echo(f"✓ 已导入：{count} 条")
