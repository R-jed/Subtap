from __future__ import annotations

from pathlib import Path

from subtap.ui.tui import RichRunner


class FakeWorkspace:
    def __init__(self, root: Path):
        self.root = root
        self.asr_jsonl = root / "asr.jsonl"
        self.aligned_jsonl = root / "aligned.jsonl"


class FakeOutputConfig:
    subtitle_punctuation = False
    subtitle_language = "zh"
    max_chars = 25
    subtitle_formats = {"srt"}
    subtitle_stem = "final"


class FakeConfig:
    output = FakeOutputConfig()


class FakePipeline:
    def __init__(self, root: Path):
        self.workspace = FakeWorkspace(root)
        self.config = FakeConfig()
        self.calls: list[tuple[str, dict]] = []
        self.plans: list[list[str]] = []

    def publish_plan(self, stages):
        self.plans.append(stages)

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
        if stage == "hotword":
            return {"replaced": 0, "total": 1}
        if stage == "learn":
            return {"learned": 0}
        if stage == "translate":
            return {"translated_count": 1}
        if stage == "export":
            return {"output_path": str(Path(kwargs["output_dir"]) / "final.srt")}
        raise AssertionError(stage)


def test_plain_runner_passes_translate_and_bilingual(tmp_path):
    pipeline = FakePipeline(tmp_path / "work")
    pipeline.workspace.root.mkdir(parents=True)

    RichRunner().run_pipeline(
        pipeline,
        tmp_path / "input.mp3",
        tmp_path / "output",
        enhance="api",
        translate_to="en",
        bilingual="source-first",
    )

    clean_call = [c for c in pipeline.calls if c[0] == "clean"][0]
    assert clean_call[1]["enhance_mode"] == "api"
    assert ("translate", {"target_language": "en"}) in pipeline.calls
    assert any(
        call[0] == "export" and call[1]["bilingual"] == "source-first"
        for call in pipeline.calls
    )
    assert any(call[0] == "hotword" for call in pipeline.calls)
    assert pipeline.plans == [
        [
            "prepare",
            "chunk",
            "asr",
            "clean",
            "segment",
            "align",
            "hotword",
            "learn",
            "translate",
            "export",
        ]
    ]
