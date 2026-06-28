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


def _parse_hotword_pairs(text: str) -> list[GlossaryReplacement]:
    """Parse haoone-style hotword text into replacement rules."""
    lines = [line.strip() for line in text.splitlines()]
    pairs: list[GlossaryReplacement] = []
    block: list[str] = []

    def flush_block() -> None:
        if len(block) < 2:
            block.clear()
            return
        canonical = block[0]
        for alias in block[1:]:
            pairs.append(GlossaryReplacement(find=alias, replace=canonical))
        block.clear()

    for line in lines + [""]:
        if not line:
            flush_block()
            continue
        if "=" in line:
            flush_block()
            canonical, aliases_text = [part.strip() for part in line.split("=", 1)]
            aliases = [item.strip() for item in aliases_text.split(",") if item.strip()]
            for alias in aliases:
                pairs.append(GlossaryReplacement(find=alias, replace=canonical))
        else:
            block.append(line)
    return pairs


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


@app.command("batch-add")
def batch_add_glossary(
    language: str = typer.Option(..., "--language", "-l", help="热词语言"),
    input_text: str | None = typer.Option(None, "--input", help="直接传入热词文本"),
    source: Path | None = typer.Option(None, "--source", "-s", help="从文件读取热词"),
    path: Path = typer.Option(_default_path(), "--file", "-f", help="术语文件路径"),
) -> None:
    """批量添加热词；支持 A=B,C 和块格式。"""
    if source is None and not input_text:
        typer.echo("✗ 请使用 --input 或 --source 提供热词", err=True)
        raise typer.Exit(1)
    if source is not None:
        if not source.exists():
            typer.echo(f"✗ 热词文件不存在：{source}", err=True)
            raise typer.Exit(1)
        raw_text = source.read_text(encoding="utf-8")
    else:
        raw_text = input_text or ""

    replacements = _parse_hotword_pairs(raw_text)
    if not replacements:
        typer.echo("✗ 没有解析到有效热词", err=True)
        raise typer.Exit(1)

    glossary = load_glossary(path)
    glossary.replacements.extend(replacements)
    _save_glossary(path, glossary)
    typer.echo(f"✓ 已添加 {len(replacements)} 条 {language} 热词")


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
