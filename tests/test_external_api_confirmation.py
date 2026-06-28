"""Phase 21: 验证外部 API 调用确认。"""

from __future__ import annotations

import re

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_enhance_api_shows_warning(tmp_path, monkeypatch):
    """--enhance api 应显示外部 API 警告。"""
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
        ["run", str(input_file), "--enhance", "api", "--no-tui"],
    )
    output = _strip_ansi(result.output)
    # 应提示字幕文本将发送到外部
    assert "外部" in output or "API" in output


def test_enhance_local_no_warning(tmp_path, monkeypatch):
    """--enhance local 不应显示外部 API 警告。"""
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
        ["run", str(input_file), "--enhance", "local", "--no-tui"],
    )
    output = _strip_ansi(result.output)
    assert "外部" not in output


def test_enhance_off_no_warning(tmp_path, monkeypatch):
    """--enhance off 不应显示外部 API 警告。"""
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
        ["run", str(input_file), "--enhance", "off", "--no-tui"],
    )
    output = _strip_ansi(result.output)
    assert "外部" not in output
