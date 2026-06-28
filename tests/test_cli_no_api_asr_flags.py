"""Phase 19: 验证 CLI 不包含 API ASR 相关标志。"""

from __future__ import annotations

import re

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text for reliable string matching."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_run_help_no_asr_api_flag():
    """subtap run --help 不应包含 --asr api 选项。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output).lower()
    # 不应有 --asr 选项
    assert "--asr" not in help_text


def test_run_help_no_hybrid_flag():
    """subtap run --help 不应包含 --hybrid 选项。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output).lower()
    assert "--hybrid" not in help_text


def test_run_help_no_deepgram_flag():
    """subtap run --help 不应包含 --deepgram 选项。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output).lower()
    assert "--deepgram" not in help_text
    assert "deepgram" not in help_text


def test_run_help_no_openai_asr_flag():
    """subtap run --help 不应包含 --openai-asr 选项。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output).lower()
    assert "--openai-asr" not in help_text


def test_run_help_no_custom_asr_url_flag():
    """subtap run --help 不应包含 --custom-asr-url 选项。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output).lower()
    assert "--custom-asr-url" not in help_text
    assert "--asr-url" not in help_text


def test_run_help_has_enhance_flag():
    """subtap run --help 应包含 --enhance 选项。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output)
    assert "--enhance" in help_text


def test_run_help_has_local_only_flag():
    """subtap run --help 应包含 --local-only 选项。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output)
    assert "--local-only" in help_text


def test_run_help_has_translate_to_flag():
    """subtap run --help 应包含 --translate-to 选项。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output)
    assert "--translate-to" in help_text


def test_run_help_no_policy_flag():
    """subtap run --help 不应包含 --policy 选项（已移除）。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output).lower()
    # --policy 已被 --local-only 替代
    assert "--policy" not in help_text
