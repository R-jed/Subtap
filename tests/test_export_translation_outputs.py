from __future__ import annotations

from pathlib import Path

from subtap.core.export import run_final_exports
from subtap.schemas.models import AlignedSegment


def _aligned(path: Path) -> None:
    rows = [
        AlignedSegment(
            sentence_id=0,
            start_sec=1.0,
            end_sec=2.0,
            text="理光 GR4 发布了",
            translated_text="Ricoh GR4 was released",
            words=[],
        )
    ]
    path.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows),
        encoding="utf-8",
    )


def test_translate_export_writes_source_and_target_srt(tmp_path):
    aligned = tmp_path / "aligned.jsonl"
    _aligned(aligned)

    result = run_final_exports(
        aligned,
        tmp_path,
        formats={"srt"},
        stem="final",
        translate_to="en",
        bilingual="off",
    )

    assert (tmp_path / "final.source.srt").exists()
    assert (tmp_path / "final.srt").read_text(encoding="utf-8").count("Ricoh GR4") == 1
    assert result["output_path"] == str(tmp_path / "final.srt")


def test_bilingual_source_first_export(tmp_path):
    aligned = tmp_path / "aligned.jsonl"
    _aligned(aligned)

    run_final_exports(
        aligned,
        tmp_path,
        formats={"srt"},
        stem="final",
        translate_to="en",
        bilingual="source-first",
    )

    text = (tmp_path / "final.srt").read_text(encoding="utf-8")
    assert "理光 GR4 发布了\nRicoh GR4 was released" in text


def test_bilingual_target_first_export(tmp_path):
    aligned = tmp_path / "aligned.jsonl"
    _aligned(aligned)

    run_final_exports(
        aligned,
        tmp_path,
        formats={"srt"},
        stem="final",
        translate_to="en",
        bilingual="target-first",
    )

    text = (tmp_path / "final.srt").read_text(encoding="utf-8")
    assert "Ricoh GR4 was released\n理光 GR4 发布了" in text
