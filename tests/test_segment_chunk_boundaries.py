"""Test that run_segment reads chunk boundaries from chunks.jsonl when not provided."""

from __future__ import annotations

from pathlib import Path
import json

from subtap.core.segment import run_segment
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig, with_output_max_chars
from subtap.schemas.models import RawCleanSegment, Chunk


def test_run_segment_reads_chunk_boundaries(test_config: SubtapConfig, tmp_path: Path):
    """run_segment should read chunk boundaries from chunks.jsonl when chunk_start/chunk_end not provided."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    ws.ensure_dirs()

    # Create chunks.jsonl with a specific time range
    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=628.736, path="chunk_0000.wav")
    with open(ws.chunks_jsonl, "w") as f:
        f.write(chunk.model_dump_json() + "\n")

    # Create cleaned.jsonl with some segments
    segments = [
        RawCleanSegment(
            segment_id=0,
            original_text="orig 0",
            cleaned_text="First sentence。",
            glossary_applied=[],
        ),
        RawCleanSegment(
            segment_id=1,
            original_text="orig 1",
            cleaned_text="Second sentence。",
            glossary_applied=[],
        ),
    ]
    with open(ws.cleaned_jsonl, "w") as f:
        for seg in segments:
            f.write(seg.model_dump_json() + "\n")

    # Run segment without providing chunk_start/chunk_end
    run_segment(ws)

    # Verify sentences have correct time range (not 0-1)
    with open(ws.sentences_jsonl) as f:
        sentences = [json.loads(line) for line in f if line.strip()]

    # Check that timestamps are in the correct range
    for sent in sentences:
        assert sent["start_sec"] >= 0.0
        assert sent["end_sec"] <= 628.736
        assert sent["start_sec"] < sent["end_sec"]

    # Verify the time range is not 0-1 (the bug)
    first_start = sentences[0]["start_sec"]
    last_end = sentences[-1]["end_sec"]
    assert last_end > 1.0, f"Expected end_sec > 1.0, got {last_end}"

    print(f"✓ Sentences time range: {first_start:.3f} - {last_end:.3f}")
    print(f"✓ Sentence count: {len(sentences)}")


def test_run_segment_uses_output_character_limits(
    test_config: SubtapConfig, tmp_path: Path, monkeypatch
):
    """Segment and export must share the user's character limits."""
    test_config.output = with_output_max_chars(test_config.output, max_chars=18)
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    ws.ensure_dirs()
    ws.chunks_jsonl.write_text(
        Chunk(
            chunk_id=0, start_sec=0.0, end_sec=1.0, path="chunk.wav"
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    ws.cleaned_jsonl.write_text(
        RawCleanSegment(
            segment_id=0,
            original_text="原文",
            cleaned_text="清洗后的文本。",
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    captured = {}

    def fake_segment(
        segments,
        chunk_start,
        chunk_end,
        language="zh",
        *,
        max_chars,
    ):
        captured.update(max_chars=max_chars)
        return []

    monkeypatch.setattr("subtap.core.segment.segment_clean_segments", fake_segment)

    run_segment(ws)

    assert captured == {"max_chars": 18}
