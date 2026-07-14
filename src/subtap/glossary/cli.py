"""Glossary CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from subtap.schemas.glossary import (
    Glossary,
    GlossaryTerm,
    load_glossary,
    save_glossary,
)

app = typer.Typer(help="热词/术语管理")


def _default_path() -> Path:
    return Path.home() / ".subtap" / "glossaries" / "default.yaml"


def _parse_hotword_terms(text: str) -> list[GlossaryTerm]:
    """Parse haoone-style hotword text into canonical terms."""
    lines = [line.strip() for line in text.splitlines()]
    terms: list[GlossaryTerm] = []
    block: list[str] = []

    def flush_block() -> None:
        if not block:
            return
        if len(block) < 2:
            raise ValueError(f"术语缺少别名：{block[0]}")
        terms.append(GlossaryTerm(canonical=block[0], aliases=block[1:]))
        block.clear()

    for line in lines + [""]:
        if not line:
            flush_block()
            continue
        if "=" in line:
            flush_block()
            canonical, aliases_text = [part.strip() for part in line.split("=", 1)]
            aliases = [item.strip() for item in aliases_text.split(",") if item.strip()]
            if not canonical or not aliases:
                raise ValueError("术语和别名不能为空")
            terms.append(GlossaryTerm(canonical=canonical, aliases=aliases))
        else:
            block.append(line)
    return terms


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
        typer.echo("✗ 格式错误：请使用 术语=别名1,别名2", err=True)
        raise typer.Exit(1)
    canonical, aliases_text = [part.strip() for part in input_text.split("=", 1)]
    aliases = [item.strip() for item in aliases_text.split(",") if item.strip()]
    if not canonical or not aliases:
        typer.echo("✗ 格式错误：术语和别名不能为空", err=True)
        raise typer.Exit(1)
    glossary = load_glossary(path)
    glossary.upsert_term(GlossaryTerm(canonical=canonical, aliases=aliases))
    save_glossary(path, glossary)
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

    try:
        terms = _parse_hotword_terms(raw_text)
    except ValueError as exc:
        typer.echo(f"✗ {exc}", err=True)
        raise typer.Exit(1) from exc
    if not terms:
        typer.echo("✗ 没有解析到有效热词", err=True)
        raise typer.Exit(1)

    glossary = load_glossary(path)
    for term in terms:
        glossary.upsert_term(term)
    save_glossary(path, glossary)
    alias_count = sum(len(term.aliases) for term in terms)
    typer.echo(f"✓ 已添加 {alias_count} 条 {language} 热词")


@app.command("remove")
def remove_glossary(
    find: str = typer.Argument(..., help="要删除的错词或术语"),
    path: Path = typer.Option(_default_path(), "--file", "-f", help="术语文件路径"),
) -> None:
    """删除一条术语。"""
    glossary = load_glossary(path)
    changed = glossary.remove_entry(find)
    save_glossary(path, glossary)
    if not changed:
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
