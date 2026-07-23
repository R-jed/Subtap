"""Glossary CLI commands."""

from __future__ import annotations

from pathlib import Path
import re

import typer

from subtap.schemas.glossary import (
    GlossaryTerm,
    load_glossary,
    remove_plain_glossary_entry,
    save_glossary,
    upsert_plain_glossary_terms,
)

app = typer.Typer(help="热词/术语管理")


def _default_path() -> Path:
    from subtap.core.user_resources import default_glossary_path

    return default_glossary_path()


def _resolve_path(path: Path | None) -> Path:
    if path is not None:
        return path
    from subtap.core.user_resources import ensure_default_glossary

    return ensure_default_glossary()


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
    path: Path | None = typer.Option(None, "--file", "-f", help="术语文件路径"),
) -> None:
    """列出当前术语。"""
    path = _resolve_path(path)
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
    input_text: str = typer.Option(
        ..., "--input", help="格式：术语 或 术语=别名1,别名2"
    ),
    path: Path | None = typer.Option(None, "--file", "-f", help="术语文件路径"),
) -> None:
    """添加一条术语。"""
    separators = list(re.finditer(r"[=＝]", input_text))
    if len(separators) > 1:
        typer.echo("✗ 格式错误：只能使用一个等号", err=True)
        raise typer.Exit(1)
    if separators:
        separator = separators[0]
        canonical = input_text[: separator.start()].strip()
        aliases = [
            item.strip() for item in re.split(r"[,，]", input_text[separator.end() :])
        ]
    else:
        if re.search(r"[,，]", input_text):
            typer.echo("✗ 格式错误：逗号只能用于等号右侧的错写列表", err=True)
            raise typer.Exit(1)
        canonical = input_text.strip()
        aliases = []
    if not canonical or any(not alias for alias in aliases):
        typer.echo("✗ 格式错误：术语和别名不能为空", err=True)
        raise typer.Exit(1)
    path = _resolve_path(path)
    term = GlossaryTerm(canonical=canonical, aliases=aliases)
    if path.suffix.lower() == ".txt":
        upsert_plain_glossary_terms(path, [term])
    else:
        glossary = load_glossary(path)
        glossary.upsert_term(term)
        save_glossary(path, glossary)
    typer.echo(f"✓ 已添加：{input_text}")


@app.command("batch-add")
def batch_add_glossary(
    language: str = typer.Option(..., "--language", "-l", help="热词语言"),
    input_text: str | None = typer.Option(None, "--input", help="直接传入热词文本"),
    source: Path | None = typer.Option(None, "--source", "-s", help="从文件读取热词"),
    path: Path | None = typer.Option(None, "--file", "-f", help="术语文件路径"),
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

    path = _resolve_path(path)
    if path.suffix.lower() == ".txt":
        upsert_plain_glossary_terms(path, terms)
    else:
        glossary = load_glossary(path)
        for term in terms:
            glossary.upsert_term(term)
        save_glossary(path, glossary)
    alias_count = sum(len(term.aliases) for term in terms)
    typer.echo(f"✓ 已添加 {alias_count} 条 {language} 热词")


@app.command("remove")
def remove_glossary(
    find: str = typer.Argument(..., help="要删除的错词或术语"),
    path: Path | None = typer.Option(None, "--file", "-f", help="术语文件路径"),
) -> None:
    """删除一条术语。"""
    path = _resolve_path(path)
    if path.suffix.lower() == ".txt":
        changed = remove_plain_glossary_entry(path, find)
    else:
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
