from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from subtap.cli import _build_observer_child_command, app


runner = CliRunner()


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_observer_child_command_passes_translate_and_bilingual(tmp_path):
    """验证 _build_observer_child_command 正确传递 --translate-to 和 --bilingual 参数"""
    command = _build_observer_child_command(
        input_path=tmp_path / "input.mp3",
        work_dir=tmp_path / "work",
        output_dir=tmp_path / "output",
        fmt="srt",
        mode="fast",
        enhance="api",
        local_only=False,
        translate_to="en",
        bilingual="target-first",
        align_enabled=True,
        punctuation=False,
        subtitle_language="zh",
        no_git_check=True,
        no_cleanroom=True,
        timestamp=True,
    )

    assert "--translate-to" in command
    assert "en" in command
    assert "--bilingual" in command
    assert "target-first" in command


def test_bilingual_without_translate_to_fails(tmp_path):
    """验证使用 --bilingual 但不指定 --translate-to 时 CLI 报错"""
    input_file = tmp_path / "input.mp3"
    input_file.write_bytes(b"fake")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--bilingual", "source-first", "--no-tui"],
    )

    assert result.exit_code == 1
    assert "bilingual" in _strip_ansi(result.output).lower() or "双语" in _strip_ansi(result.output)


def test_translate_to_shows_external_api_warning(tmp_path):
    """验证使用 --translate-to + --enhance api 时提示外部 API 使用"""
    input_file = tmp_path / "input.mp3"
    input_file.write_bytes(b"fake")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--translate-to", "en", "--enhance", "api", "--no-tui"],
    )

    assert "翻译" in _strip_ansi(result.output) or "外部 LLM API" in _strip_ansi(result.output)
