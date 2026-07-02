from __future__ import annotations

import json
from pathlib import Path

from subtap.core.clean import run_clean
from subtap.core.translate import run_translate
from subtap.core.export import run_final_exports
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import ASRSegment, AlignedSegment


class FakeLLM:
    def __init__(self):
        self.translation_input = ""

    def select_suspicious_segments(self, segments):
        return [0]

    def repair_segments(self, segments):
        return {0: "理光 GR4 发布了"}

    def replace_hotwords(self, segments, glossary):
        return {}

    def translate_srt(self, srt_text, target_language):
        self.translation_input = srt_text
        return "1\n00:00:01,000 --> 00:00:02,000\nRicoh GR4 was released\n"


def test_translation_uses_repaired_hotword_text_not_raw_asr(tmp_path, monkeypatch):
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    workspace.asr_jsonl.write_text(
        ASRSegment(
            chunk_id=0,
            segment_id=0,
            start_sec=1.0,
            end_sec=2.0,
            text="李光机亚四发布了",
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    llm = FakeLLM()
    monkeypatch.setattr("subtap.core.clean.get_llm_backend", lambda *_a, **_k: llm)
    monkeypatch.setattr("subtap.core.translate.get_llm_backend", lambda *_a, **_k: llm)

    run_clean(workspace, config, enhance_mode="api")
    cleaned = json.loads(workspace.cleaned_jsonl.read_text(encoding="utf-8").splitlines()[0])
    workspace.aligned_jsonl.write_text(
        AlignedSegment(
            sentence_id=0,
            start_sec=1.0,
            end_sec=2.0,
            text=cleaned["cleaned_text"],
            words=[],
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    run_translate(workspace, config, target_language="en")

    assert "理光 GR4 发布了" in llm.translation_input
    assert "李光机亚四发布了" not in llm.translation_input


def test_final_export_matrix_for_translation(tmp_path):
    aligned = tmp_path / "aligned.jsonl"
    aligned.write_text(
        AlignedSegment(
            sentence_id=0,
            start_sec=1.0,
            end_sec=2.0,
            text="理光 GR4 发布了",
            translated_text="Ricoh GR4 was released",
            words=[],
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )

    run_final_exports(
        aligned,
        tmp_path,
        formats={"srt"},
        stem="final",
        translate_to="en",
        bilingual="target-first",
    )

    assert (tmp_path / "final.source.srt").exists()
    final_text = (tmp_path / "final.srt").read_text(encoding="utf-8")
    assert "Ricoh GR4 was released\n理光 GR4 发布了" in final_text
