"""Phase 25: output contract files."""

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

    result = run_final_exports(aligned_jsonl, tmp_path / "latest")

    assert (tmp_path / "latest" / "final.srt").exists()
    assert (tmp_path / "latest" / "final.vtt").exists()
    assert (tmp_path / "latest" / "final.json").exists()
    assert (tmp_path / "latest" / "final.tsv").exists()
    assert result["output_contract"] == "final"
