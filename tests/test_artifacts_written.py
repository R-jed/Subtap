"""Phase 25: artifacts contract."""

import json

from subtap.output.contract import write_contract_artifacts


def test_artifacts_written(tmp_path):
    """Artifacts directory should contain stable debug JSON files."""
    work_dir = tmp_path / "work"
    output_dir = tmp_path / "latest"
    work_dir.mkdir()
    (work_dir / "asr").mkdir()
    (work_dir / "asr" / "asr_draft.jsonl").write_text('{"text":"asr"}\n')
    (work_dir / "cleaned.jsonl").write_text('{"text":"clean"}\n')
    (work_dir / "sentences.jsonl").write_text('{"text":"candidate"}\n')
    (work_dir / "aligned_subtitles.jsonl").write_text('{"text":"aligned"}\n')

    write_contract_artifacts(work_dir, output_dir, quality={"score": 90})

    artifacts_dir = output_dir / "artifacts"
    expected = [
        "asr_draft.json",
        "clean_segments.json",
        "sentence_candidates.json",
        "aligned_subtitles.json",
        "quality.json",
    ]
    for name in expected:
        assert (artifacts_dir / name).exists()
    assert json.loads((artifacts_dir / "quality.json").read_text())["score"] == 90
