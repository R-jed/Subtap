"""CLI shared utilities."""

from __future__ import annotations

import typer


def _handle_error(message: str, exit_code: int = 1) -> None:
    """统一错误处理：输出错误信息并退出。

    Args:
        message: 错误消息
        exit_code: 退出码，默认为 1
    """
    typer.echo(f"✗ {message}", err=True)
    raise typer.Exit(exit_code)
