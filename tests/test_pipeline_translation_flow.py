from __future__ import annotations

from pathlib import Path

from subtap.ui.tui import PlainRunner


class FakeWorkspace:
    def __init__(self, root: Path):
        self.root = root
        self.asr_jsonl = root / "asr.jsonl"
        self.aligned_jsonl = root / "aligned.jsonl"


class FakeOutputConfig:
    subtitle_punctuation = False
    subtitle_language = "zh"
    max_chars = 25
    min_chars = 10
    subtitle_formats = {"srt"}
    subtitle_stem = "final"


class FakeConfig:
    output = FakeOutputConfig()


class FakePipeline:
    def __init__(self, root: Path):
        self.workspace = FakeWorkspace(root)
        self.config = FakeConfig()
        self.calls: list[tuple[str, dict]] = []

    def run_stage(self, stage: str, **kwargs):
        self.calls.append((stage, kwargs))
        if stage == "prepare":
            return {"media_info": {"duration": 1.0, "sample_rate": 16000}}
        if stage == "chunk":
            return {"chunk_count": 1}
        if stage == "asr":
            return {"segment_count": 1}
        if stage == "clean":
            return {"segment_count": 1}
        if stage == "segment":
            return {"sentence_count": 1}
        if stage == "script_match":
            return {"skipped": True}
        if stage == "align":
            return {"aligned_count": 1}
        if stage == "translate":
            return {"translated_count": 1}
        raise AssertionError(stage)


def test_plain_runner_passes_translate_and_bilingual(monkeypatch, tmp_path):
    pipeline = FakePipeline(tmp_path / "work")
    pipeline.workspace.root.mkdir(parents=True)

    def fake_final_exports(*_args, **kwargs):
        pipeline.calls.append(("export", kwargs))
        return {"output_path": str(tmp_path / "output" / "final.srt")}

    monkeypatch.setattr("subtap.core.export.run_final_exports", fake_final_exports)

    PlainRunner().run_pipeline(
        pipeline,
        tmp_path / "input.mp3",
        tmp_path / "output",
        enhance="api",
        translate_to="en",
        bilingual="source-first",
        hotword_enabled=True,
    )

    assert (
        "clean",
        {"enhance_mode": "api", "hotword_enabled": True, "hotword_mode": "local"},
    ) in pipeline.calls
    assert ("translate", {"target_language": "en"}) in pipeline.calls
    assert any(
        call[0] == "export" and call[1]["bilingual"] == "source-first"
        for call in pipeline.calls
    )
    assert not any(call[0] == "hotword" for call in pipeline.calls)
