"""Tests for AI hotword replacement task contract."""

from __future__ import annotations

from subtap.enhancement.api_llm import APIEnhancer
from subtap.enhancement.tasks import EnhancementTask, get_tasks_for_mode
from subtap.schemas.enhancement import CleanSegment


def test_api_mode_includes_ai_hotword_replacement():
    """API enhancement should include contextual hotword replacement."""
    assert EnhancementTask.AI_HOTWORD_REPLACEMENT in get_tasks_for_mode("api")


def test_ai_hotword_replacement_preserves_timing_with_mock_client():
    """AI hotword replacement may change text but never timing."""
    calls = []

    def client(text, task, glossary, target_language):
        calls.append(
            {
                "text": text,
                "task": task,
                "glossary": glossary,
                "target_language": target_language,
            }
        )
        if task == "ai_hotword_replacement":
            return text.replace("欧喷AI", "OpenAI")
        return text

    enhancer = APIEnhancer(text_client=client)
    segment = CleanSegment(
        segment_id=1,
        source_chunk_id=0,
        text="这里提到欧喷AI",
        original_text="这里提到欧喷AI",
        start_sec=1.0,
        end_sec=2.0,
    )

    result = enhancer.enhance(
        [segment],
        glossary={"欧喷AI": "OpenAI"},
        tasks=[EnhancementTask.AI_HOTWORD_REPLACEMENT],
    )

    assert result.segments[0].text == "这里提到OpenAI"
    assert result.segments[0].start_sec == 1.0
    assert result.segments[0].end_sec == 2.0
    assert result.api_calls == 1
    assert calls[0]["task"] == "ai_hotword_replacement"
