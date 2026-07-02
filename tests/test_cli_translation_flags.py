from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_bilingual_without_translate_to_fails(tmp_path):
    """验证使用 --bilingual 但不指定 --translate-to 时 CLI 报错"""
    input_file = tmp_path / "input.mp3"
    input_file.write_bytes(b"fake")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--bilingual", "source-first"],
    )

    assert result.exit_code == 1
    assert "bilingual" in _strip_ansi(result.output).lower() or "双语" in _strip_ansi(
        result.output
    )


def test_translate_to_shows_external_api_warning(tmp_path, monkeypatch):
    """验证使用 --translate-to + --enhance api 时提示外部 API 使用"""
    from types import SimpleNamespace
    import subtap.schemas.config as cfg_mod

    config = SimpleNamespace(
        mode="online",
        output=SimpleNamespace(
            timestamp=True,
            generate_metrics=True,
            subtitle_punctuation=False,
            subtitle_language="zh",
            max_chars=25,
            min_chars=10,
            subtitle_stem="output",
        ),
        metrics=SimpleNamespace(output_path="metrics.json"),
        translate_to="",
    )
    monkeypatch.setattr(cfg_mod, "load_config", lambda p: config)

    input_file = tmp_path / "input.mp3"
    input_file.write_bytes(b"fake")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--translate-to", "en", "--enhance", "api"],
    )

    assert "翻译" in _strip_ansi(result.output) or "外部 LLM API" in _strip_ansi(
        result.output
    )
