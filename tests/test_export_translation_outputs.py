from __future__ import annotations

import json
from pathlib import Path

import pytest

from subtap.core.export import run_final_exports
from subtap.schemas.models import AlignedSegment


def _aligned(path: Path) -> None:
    rows = [
        AlignedSegment(
            sentence_id=0,
            start_sec=1.0,
            end_sec=2.0,
            text="理光 GR4 发布了",
            aligned_text="李光 GR4 发布了",
            translated_text="Ricoh GR4 was released",
            words=[
                {"word": "李光", "start_sec": 1.0, "end_sec": 1.2},
                {"word": "GR4", "start_sec": 1.2, "end_sec": 1.4},
                {"word": "发布了", "start_sec": 1.4, "end_sec": 2.0},
            ],
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
    source_text = (tmp_path / "final.source.srt").read_text(encoding="utf-8")
    assert "理光 GR4 发布了" in source_text
    assert "Ricoh GR4" not in source_text
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


def test_translate_export_ignores_source_aligned_text_for_srt_and_vtt(tmp_path):
    aligned = tmp_path / "aligned.jsonl"
    _aligned(aligned)

    run_final_exports(
        aligned,
        tmp_path,
        formats={"srt", "vtt"},
        stem="final",
        translate_to="en",
        bilingual="off",
    )

    assert "Ricoh GR4 was released" in (tmp_path / "final.srt").read_text(
        encoding="utf-8"
    )
    assert "Ricoh GR4 was released" in (tmp_path / "final.vtt").read_text(
        encoding="utf-8"
    )
    assert "李光" not in (tmp_path / "final.srt").read_text(encoding="utf-8")
    assert "李光" not in (tmp_path / "final.vtt").read_text(encoding="utf-8")


def test_translate_export_json_and_tsv_use_translated_text(tmp_path):
    aligned = tmp_path / "aligned.jsonl"
    _aligned(aligned)

    run_final_exports(
        aligned,
        tmp_path,
        formats={"json", "tsv"},
        stem="final",
        translate_to="en",
        bilingual="off",
    )

    payload = json.loads((tmp_path / "final.json").read_text(encoding="utf-8"))
    assert payload[0]["text"] == "Ricoh GR4 was released"
    tsv = (tmp_path / "final.tsv").read_text(encoding="utf-8")
    assert "Ricoh GR4 was released" in tsv
    assert "理光 GR4 发布了" not in tsv


def test_translate_export_requires_translated_text(tmp_path):
    aligned = tmp_path / "aligned.jsonl"
    segment = AlignedSegment(
        sentence_id=0,
        start_sec=1.0,
        end_sec=2.0,
        text="理光 GR4 发布了",
        words=[],
    )
    aligned.write_text(segment.model_dump_json() + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="缺少翻译文本"):
        run_final_exports(
            aligned,
            tmp_path,
            formats={"srt"},
            stem="final",
            translate_to="en",
            bilingual="off",
        )
