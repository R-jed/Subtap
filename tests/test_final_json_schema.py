"""Phase 25: final.json schema."""

import json

from subtap.core.export import run_final_exports
from subtap.schemas.models import AlignedSegment


def test_final_json_schema(tmp_path):
    """final.json should expose stable subtitle fields and traceability."""
    aligned = AlignedSegment(
        sentence_id=2,
        start_sec=1.0,
        end_sec=2.5,
        text="测试字幕",
    )
    aligned_jsonl = tmp_path / "aligned.jsonl"
    aligned_jsonl.write_text(aligned.model_dump_json() + "\n", encoding="utf-8")

    run_final_exports(aligned_jsonl, tmp_path / "latest", formats={"srt", "vtt", "json", "tsv"})

    payload = json.loads((tmp_path / "latest" / "final.json").read_text())
    item = payload[0]
    assert item["subtitle_id"] == 2
    assert item["start_sec"] == 1.0
    assert item["end_sec"] == 2.5
    assert item["text"] == "测试字幕"
    assert item["words"] == []
    assert item["source_trace"]["source"] == "forced_aligner"
    assert "alignment_confidence" in item
