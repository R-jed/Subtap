from __future__ import annotations

from pathlib import Path

import pytest

from subtap.core.translate import (
    parse_srt,
    render_srt_from_aligned,
    run_translate,
    validate_translated_srt,
)
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import AlignedSegment


class FakeTranslator:
    def __init__(self, translated_srt: str):
        self.translated_srt = translated_srt
        self.input_srt = ""
        self.target_language = ""

    def translate_srt(self, srt_text: str, target_language: str) -> str:
        self.input_srt = srt_text
        self.target_language = target_language
        return self.translated_srt


def _workspace(tmp_path: Path) -> Workspace:
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    rows = [
        AlignedSegment(
            sentence_id=0,
            start_sec=1.0,
            end_sec=2.0,
            text="理光 GR4 发布了",
            words=[],
        ),
        AlignedSegment(
            sentence_id=1,
            start_sec=2.0,
            end_sec=3.5,
            text="这是一台相机",
            words=[],
        ),
    ]
    workspace.aligned_jsonl.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows),
        encoding="utf-8",
    )
    return workspace


def test_render_srt_from_aligned_uses_enhanced_aligned_text(tmp_path):
    workspace = _workspace(tmp_path)
    srt_text = render_srt_from_aligned(workspace.aligned_jsonl)

    assert "理光 GR4 发布了" in srt_text
    assert "00:00:01,000 --> 00:00:02,000" in srt_text


def test_parse_srt_reads_index_time_and_text():
    blocks = parse_srt("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

    assert blocks == [
        {
            "index": 1,
            "start": "00:00:01,000",
            "end": "00:00:02,000",
            "text": "Hello",
        }
    ]


def test_validate_translated_srt_rejects_time_changes():
    source = parse_srt("1\n00:00:01,000 --> 00:00:02,000\n源文\n")
    translated = parse_srt("1\n00:00:01,100 --> 00:00:02,000\nHello\n")

    with pytest.raises(ValueError, match="时间轴不一致"):
        validate_translated_srt(source, translated)


def test_run_translate_writes_translated_text(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    translated = (
        "1\n00:00:01,000 --> 00:00:02,000\nRicoh GR4 was released\n\n"
        "2\n00:00:02,000 --> 00:00:03,500\nThis is a camera\n"
    )
    llm = FakeTranslator(translated)
    monkeypatch.setattr("subtap.core.translate.get_llm_backend", lambda *_a, **_k: llm)

    result = run_translate(workspace, SubtapConfig(), target_language="en")

    assert result["translated_count"] == 2
    assert llm.target_language == "en"
    assert "理光 GR4 发布了" in llm.input_srt
    payload = workspace.aligned_jsonl.read_text(encoding="utf-8")
    assert "Ricoh GR4 was released" in payload
    assert "This is a camera" in payload


def test_run_translate_rejects_non_openai_backend(tmp_path):
    workspace = _workspace(tmp_path)

    with pytest.raises(ValueError, match="翻译只支持 OpenAI-compatible"):
        run_translate(
            workspace,
            SubtapConfig(),
            target_language="en",
            llm_backend_name="ollama:qwen3-coder",
        )
