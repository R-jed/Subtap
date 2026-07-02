"""Phase 21: 验证 --local-only 禁用 API 增强。"""

from __future__ import annotations

import re

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_local_only_blocks_api_enhance(tmp_path, monkeypatch):
    """--local-only 模式下不能使用 --enhance api。"""
    input_file = tmp_path / "test.mp3"
    input_file.write_bytes(b"fake audio")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--local-only", "--enhance", "api"],
    )
    assert result.exit_code == 1
    output = _strip_ansi(result.output)
    assert "local-only" in output.lower() or "错误" in output


def test_local_only_allows_local_enhance(tmp_path, monkeypatch):
    """--local-only 模式下可以使用 --enhance local。"""
    from types import SimpleNamespace

    input_file = tmp_path / "test.mp3"
    input_file.write_bytes(b"fake audio")

    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda p: SimpleNamespace(output=SimpleNamespace(timestamp=True)),
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--local-only", "--enhance", "local"],
    )
    output = _strip_ansi(result.output)
    assert "local-only 模式下不能使用" not in output


def test_local_only_allows_local_enhance(tmp_path, monkeypatch):
    """--local-only 模式下可以使用 --enhance local。"""
    from types import SimpleNamespace

    input_file = tmp_path / "test.mp3"
    input_file.write_bytes(b"fake audio")

    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda p: SimpleNamespace(output=SimpleNamespace(timestamp=True)),
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--local-only", "--enhance", "local"],
    )
    output = _strip_ansi(result.output)
    assert "local-only 模式下不能使用" not in output
