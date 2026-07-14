"""Phase 25: output contract files."""

import pytest

from subtap.core.export import run_final_exports
from subtap.schemas.models import AlignedSegment


def test_output_contract_files(tmp_path):
    """Aligned output should create all final deliverables."""
    aligned = AlignedSegment(
        sentence_id=0,
        start_sec=0.0,
        end_sec=1.0,
        text="测试字幕",
    )
    aligned_jsonl = tmp_path / "aligned.jsonl"
    aligned_jsonl.write_text(aligned.model_dump_json() + "\n", encoding="utf-8")

    result = run_final_exports(
        aligned_jsonl, tmp_path / "latest", formats={"srt", "vtt", "json", "tsv"}
    )

    assert (tmp_path / "latest" / "final.srt").exists()
    assert (tmp_path / "latest" / "final.vtt").exists()
    assert (tmp_path / "latest" / "final.json").exists()
    assert (tmp_path / "latest" / "final.tsv").exists()
    assert result["output_contract"] == "final"


def test_output_contract_rejects_overlapping_timeline_before_delivery(tmp_path):
    """The main final-export path must enforce the SRT delivery gate."""
    segments = [
        AlignedSegment(
            sentence_id=0,
            start_sec=0.0,
            end_sec=2.0,
            text="这是第一句完整字幕。",
        ),
        AlignedSegment(
            sentence_id=1,
            start_sec=1.5,
            end_sec=3.0,
            text="这是第二句完整字幕。",
        ),
    ]
    aligned_jsonl = tmp_path / "aligned.jsonl"
    aligned_jsonl.write_text(
        "".join(segment.model_dump_json() + "\n" for segment in segments),
        encoding="utf-8",
    )
    output_dir = tmp_path / "latest"

    with pytest.raises(ValueError, match="SRT 交付检查失败"):
        run_final_exports(
            aligned_jsonl,
            output_dir,
            formats={"srt", "vtt", "json", "tsv"},
        )

    assert not (output_dir / "final.srt").exists()
    assert not (output_dir / "final.vtt").exists()
    assert not (output_dir / "final.json").exists()
    assert not (output_dir / "final.tsv").exists()
