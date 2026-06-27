"""Glossary CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="热词/术语管理")


@app.command("list")
def list_glossary() -> None:
    """列出当前术语。"""
    typer.echo("暂无术语")


@app.command("add")
def add_glossary(
    input_text: str = typer.Option(..., "--input", help="格式：术语=别名1,别名2"),
) -> None:
    """添加一条术语。"""
    typer.echo(f"✓ 已添加：{input_text}")


@app.command("import")
def import_glossary(
    path: Path = typer.Option(..., "--file", "-f", help="术语文件路径"),
) -> None:
    """从文件导入术语。"""
    typer.echo(f"✓ 已导入：{path}")
