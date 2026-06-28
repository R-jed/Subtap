"""Tests for translation and bilingual subtitle text contracts."""

from __future__ import annotations

from typer.testing import CliRunner

from subtap.cli import app
from subtap.enhancement.api_llm import APIEnhancer
from subtap.enhancement.tasks import EnhancementTask
from subtap.schemas.enhancement import CleanSegment
from subtap.translation import build_bilingual_text

runner = CliRunner()


def test_api_translation_uses_target_language_and_preserves_timing():
    calls = []

    def client(text, task, glossary, target_language):
        calls.append((text, task, target_language))
        return "Hello"

    enhancer = APIEnhancer(text_client=client)
    segment = CleanSegment(
        segment_id=1,
        source_chunk_id=0,
        text="你好",
        original_text="你好",
        start_sec=1.0,
        end_sec=2.0,
    )

    result = enhancer.enhance(
        [segment],
        tasks=[EnhancementTask.TRANSLATION],
        target_language="en",
    )

    assert result.segments[0].text == "Hello"
    assert result.segments[0].start_sec == 1.0
    assert result.segments[0].end_sec == 2.0
    assert calls == [("你好", "translation", "en")]


def test_build_bilingual_text_order():
    assert build_bilingual_text("你好", "Hello", "source-first") == "你好\nHello"
    assert build_bilingual_text("你好", "Hello", "target-first") == "Hello\n你好"


def test_run_local_only_blocks_translation(tmp_path):
    media = tmp_path / "demo.wav"
    media.write_bytes(b"demo")

    result = runner.invoke(
        app,
        ["run", str(media), "--local-only", "--translate-to", "en", "--no-tui"],
    )

    assert result.exit_code == 1
    assert "--local-only 模式下不能使用 --translate-to" in result.output


def test_run_help_exposes_bilingual_option():
    result = runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0
    assert "bilingual" in result.output
