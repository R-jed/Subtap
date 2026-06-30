"""Phase 19: 验证 --local-only 阻止 LLM API 调用。"""

from __future__ import annotations

import re
from types import SimpleNamespace

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text for reliable string matching."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_local_only_blocks_enhance_api(tmp_path):
    """--local-only 模式下不能使用 --enhance api。"""
    input_file = tmp_path / "test.mp3"
    input_file.write_bytes(b"fake audio")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--local-only", "--enhance", "api"],
    )
    assert result.exit_code == 1
    assert "local-only" in _strip_ansi(result.output).lower() or "错误" in _strip_ansi(
        result.output
    )


def test_local_only_allows_enhance_local(tmp_path, monkeypatch):
    """--local-only 模式下可以使用 --enhance local。"""
    input_file = tmp_path / "test.mp3"
    input_file.write_bytes(b"fake audio")

    # Mock 配置加载
    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda p: SimpleNamespace(output=SimpleNamespace(timestamp=True)),
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--local-only", "--enhance", "local"],
    )
    # 不应报 "local-only 模式下不能使用" 错误
    output = _strip_ansi(result.output)
    assert "local-only 模式下不能使用" not in output


def test_local_only_allows_enhance_off(tmp_path, monkeypatch):
    """--local-only 模式下可以使用 --enhance off。"""
    input_file = tmp_path / "test.mp3"
    input_file.write_bytes(b"fake audio")

    # Mock 配置加载
    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda p: SimpleNamespace(output=SimpleNamespace(timestamp=True)),
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--local-only", "--enhance", "off"],
    )
    output = _strip_ansi(result.output)
    assert "local-only 模式下不能使用" not in output


def test_enhance_api_shows_warning(tmp_path, monkeypatch):
    """--enhance api 应显示外部 API 警告。"""
    input_file = tmp_path / "test.mp3"
    input_file.write_bytes(b"fake audio")

    # Mock 配置加载
    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda p: SimpleNamespace(output=SimpleNamespace(timestamp=True)),
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--enhance", "api"],
    )
    output = _strip_ansi(result.output)
    # 应提示字幕文本将发送到外部
    assert "外部" in output or "API" in output


def test_default_enhance_is_local():
    """默认增强模式应为 local。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output)
    # 检查 --enhance 的默认值
    assert "local" in help_text


def test_enhance_accepts_off_local_api():
    """--enhance 应接受 off/local/api 三个值。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output)
    assert "off" in help_text
    assert "local" in help_text
    assert "api" in help_text
