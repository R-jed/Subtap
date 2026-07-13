"""CLI shared utilities."""

from __future__ import annotations

import sys

import typer


def auto_json(explicit: bool) -> bool:
    """自动检测 JSON 输出：显式 --json 或 stdout 被管道时启用。

    管道场景（如 `subtap doctor --json | jq`）不需要显式传 --json。
    """
    return explicit or not sys.stdout.isatty()


def _handle_error(message: str, exit_code: int = 1) -> None:
    """统一错误处理：输出错误信息并退出。

    Args:
        message: 错误消息
        exit_code: 退出码，默认为 1
    """
    typer.echo(f"✗ {message}", err=True)
    raise typer.Exit(exit_code)
