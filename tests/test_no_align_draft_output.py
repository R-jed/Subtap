"""Tests for no-align draft output mode."""

from __future__ import annotations

import json
from types import SimpleNamespace

from subtap.schemas.models import ASRSegment
from subtap.ui.tui import PlainRunner


def test_plain_runner_no_align_skips_align_and_writes_draft(tmp_path):
    """--no-align should skip align and only create draft output."""
    calls: list[str] = []
    work_dir = tmp_path / "work"
    output_dir = tmp_path / "out"
    asr_jsonl = work_dir / "asr" / "asr.jsonl"

    class FakePipeline:
        workspace = SimpleNamespace(
            root=work_dir,
            asr_jsonl=asr_jsonl,
            aligned_jsonl=work_dir / "aligned.jsonl",
        )

        def run_stage(self, stage, **kwargs):
            calls.append(stage)
            if stage == "prepare":
                return {"media_info": {"duration": 1.0, "sample_rate": 16000}}
            if stage == "chunk":
                return {"chunk_count": 1}
            if stage == "asr":
                asr_jsonl.parent.mkdir(parents=True, exist_ok=True)
                segment = ASRSegment(
                    chunk_id=0,
                    segment_id=0,
                    start_sec=0.0,
                    end_sec=1.0,
                    text="你好",
                )
                asr_jsonl.write_text(
                    segment.model_dump_json() + "\n",
                    encoding="utf-8",
                )
                return {"segment_count": 1}
            if stage == "clean":
                return {"segment_count": 1}
            if stage == "hotword":
                return {"replaced": 0, "total": 1}
            if stage == "segment":
                return {"sentence_count": 1}
            if stage == "align":
                raise AssertionError("no-align must not run align")
            raise AssertionError(stage)

    result = PlainRunner().run_pipeline(
        FakePipeline(),
        tmp_path / "input.wav",
        output_dir,
        fmt="srt",
        align_enabled=False,
    )

    assert "align" not in calls
    assert (output_dir / "draft.srt").exists()
    assert (output_dir / "draft.json").exists()
    assert not (output_dir / "final.srt").exists()
    assert result["alignment_enabled"] is False
    assert result["timings"]["align"] == 0

    payload = json.loads((output_dir / "draft.json").read_text(encoding="utf-8"))
    assert payload[0]["text"] == "你好"
    assert payload[0]["start_sec"] == 0.0
    assert payload[0]["end_sec"] == 1.0


def test_plain_runner_default_runs_align(tmp_path, monkeypatch):
    """Default run should still execute align."""
    calls: list[str] = []
    work_dir = tmp_path / "work"
    output_dir = tmp_path / "out"
    work_dir.mkdir()

    class FakePipeline:
        workspace = SimpleNamespace(
            root=work_dir,
            aligned_jsonl=work_dir / "aligned.jsonl",
        )
        config = SimpleNamespace(
            output=SimpleNamespace(subtitle_punctuation=False, subtitle_language="zh", max_chars=25, min_chars=10, subtitle_formats={"srt"}, subtitle_stem="final")
        )

        def run_stage(self, stage, **kwargs):
            calls.append(stage)
            if stage == "prepare":
                return {"media_info": {"duration": 1.0, "sample_rate": 16000}}
            if stage == "chunk":
                return {"chunk_count": 1}
            if stage == "asr":
                return {"segment_count": 1}
            if stage == "clean":
                return {"segment_count": 1}
            if stage == "hotword":
                return {"replaced": 0, "total": 1}
            if stage == "segment":
                return {"sentence_count": 1}
            if stage == "align":
                return {"aligned_count": 1}
            raise AssertionError(stage)

    monkeypatch.setattr(
        "subtap.core.export.run_export",
        lambda *_args, **_kwargs: {"output_path": str(output_dir / "output.srt")},
    )

    result = PlainRunner().run_pipeline(
        FakePipeline(),
        tmp_path / "input.wav",
        output_dir,
        fmt="srt",
    )

    assert "align" in calls
    assert result["alignment_enabled"] is True
