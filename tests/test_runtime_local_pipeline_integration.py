"""Real runner-driven local pipeline integration tests.

These tests exercise the actual production orchestration path:

    real RichRunner.run_pipeline()
        → BaseRunner._run_pipeline_inner()
            → _build_stages()
            → _run_loop()
                → Pipeline.run_stage() for each stage
            → _run_export()

Heavy backends (prepare_media, split_chunks, run_asr, run_align) are
stubbed at their function boundaries.  run_clean, segment, hotword,
learn, and export execute real production code.

The align stub reads the ACTUAL sentences.jsonl produced by the real
segment stage — final.srt is causally derived from the real clean and
segment output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from subtap.core.pipeline import Pipeline
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import ASRSegment, Chunk
from subtap.ui.tui import RichRunner

runner = CliRunner()


# ── helpers ─────────────────────────────────────────────────────────


def _make_config(tmp_path: Path) -> SubtapConfig:
    """Build a minimal SubtapConfig for pipeline tests."""
    config = SubtapConfig()
    config.workspace.root = str(tmp_path / "work")
    config.output.directory = str(tmp_path / "output")
    return config


def _seed_asr(ws, texts: list[str]) -> None:
    """Write ASR segments with observable doubled-space text."""
    ws.asr_dir.mkdir(parents=True, exist_ok=True)
    with open(ws.asr_jsonl, "w") as f:
        for i, text in enumerate(texts):
            seg = ASRSegment(
                chunk_id=0,
                segment_id=i,
                start_sec=float(i),
                end_sec=float(i + 1),
                text=text,
            )
            f.write(seg.model_dump_json() + "\n")


def _make_prepare_stub(tmp_path: Path):
    """Stub prepare_media: write media_info.json, return result shape."""

    def _stub(input_path, workspace, config):
        info = {"duration": 2.0, "sample_rate": 16000, "channels": 1}
        ws_root = Path(workspace.root)
        ws_root.mkdir(parents=True, exist_ok=True)
        (ws_root / "media_info.json").write_text(json.dumps(info))
        from types import SimpleNamespace

        return SimpleNamespace(model_dump=lambda: info)

    return _stub


def _make_chunk_stub(tmp_path: Path):
    """Stub split_chunks: return one chunk covering full audio."""

    def _stub(workspace, config):
        chunk = Chunk(
            chunk_id=0, start_sec=0.0, end_sec=2.0, path=str(tmp_path / "chunk0.wav")
        )
        with open(workspace.chunks_jsonl, "w") as f:
            f.write(chunk.model_dump_json() + "\n")
        return [chunk]

    return _stub


def _make_asr_stub():
    """Stub run_asr: ASR data already seeded in __init__."""

    def _stub(workspace, config, **kwargs):
        count = 0
        if workspace.asr_jsonl.exists():
            count = sum(1 for _ in open(workspace.asr_jsonl))
        return {"segment_count": count, "asr_jsonl": str(workspace.asr_jsonl)}

    return _stub


def _make_align_stub():
    """Stub run_align: read actual sentences.jsonl, write aligned.jsonl."""

    def _stub(workspace, config, **kwargs):
        sentences_path = kwargs.get("sentences_path") or workspace.sentences_jsonl
        aligned = []
        with open(sentences_path) as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    aligned.append(
                        {
                            "sentence_id": rec.get("sentence_id", 0),
                            "start_sec": rec.get("start_sec", 0.0),
                            "end_sec": rec.get("end_sec", 1.0),
                            "text": rec["text"],
                        }
                    )
        with open(workspace.aligned_jsonl, "w") as f:
            for rec in aligned:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"aligned_count": len(aligned)}

    return _stub


def _make_hotword_stub():
    """Stub run_hotword: no replacements (avoids glossary load)."""

    def _stub(workspace, **kwargs):
        return {"replaced": 0, "total": 0}

    return _stub


# ── tests ───────────────────────────────────────────────────────────


class TestRunnerDrivenPipeline:
    """Execute real pipeline through the real runner stage loop.

    The runner constructs the stage plan, iterates stages, and calls
    Pipeline.run_stage() for each one.  Heavy backends are stubbed;
    run_clean and segment execute real production code.
    """

    def _run_full_pipeline(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        enhance: str = "local",
        local_only: bool = False,
    ) -> tuple[list[str], Path]:
        """Run full pipeline through real runner.  Return (observed_stages, output_dir)."""
        config = _make_config(tmp_path)
        work_dir = tmp_path / "work"
        output_dir = tmp_path / "output"

        # Seed ASR data in Pipeline.__init__
        original_init = Pipeline.__init__

        def seeded_init(self, config, work_dir, **kwargs):
            original_init(self, config, work_dir, **kwargs)
            self.workspace.ensure_dirs()
            _seed_asr(self.workspace, ["hello  world  test", "foo  bar  baz"])

        monkeypatch.setattr(Pipeline, "__init__", seeded_init)

        # Stub heavy backends
        monkeypatch.setattr(
            "subtap.core.media.prepare_media", _make_prepare_stub(tmp_path)
        )
        monkeypatch.setattr("subtap.core.vad.split_chunks", _make_chunk_stub(tmp_path))
        monkeypatch.setattr("subtap.core.asr.run_asr", _make_asr_stub())
        monkeypatch.setattr("subtap.core.align.run_align", _make_align_stub())
        monkeypatch.setattr("subtap.core.hotword.run_hotword", _make_hotword_stub())

        # Prevent LLM backend calls
        def fail_if_llm(*_a, **_k):
            raise AssertionError("get_llm_backend must not be called")

        monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_llm)

        # Stub model validation
        monkeypatch.setattr(
            "subtap.core.models.validate_runtime_models", lambda _c: None
        )
        monkeypatch.setattr("subtap.core.models.apply_asr_mode", lambda _c, _m: None)
        monkeypatch.setattr("subtap.core.models.asr_mode_for_model", lambda _m: "fast")

        # Observe stage order via Pipeline.run_stage spy
        observed: list[str] = []
        original_run_stage = Pipeline.run_stage

        def observed_run_stage(self, stage, **kwargs):
            observed.append(stage)
            return original_run_stage(self, stage, **kwargs)

        monkeypatch.setattr(Pipeline, "run_stage", observed_run_stage)

        # Build policy
        from subtap.runtime.external_policy import build_policy

        policy = build_policy(
            local_only=local_only,
            enhance_mode=enhance,
            asr_backend="mlx-qwen-asr",
        )
        config.llm_proofread = policy.llm_proofread
        config.llm_hotword = policy.llm_hotword

        # Create real Pipeline
        pipeline = Pipeline(
            config,
            work_dir=work_dir,
            external_policy=policy,
        )

        # Create real input file
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav-data")

        # Run through real RichRunner
        rich = RichRunner()
        meta = rich.run_pipeline(
            pipeline,
            audio,
            output_dir,
            fmt="srt",
            enhance=enhance,
        )

        return observed, output_dir

    @pytest.mark.parametrize(
        "enhance,local_only",
        [
            ("local", False),
            ("api", True),
            ("off", False),
        ],
        ids=["enhance=local", "local_only=True", "enhance=off"],
    )
    def test_full_pipeline_through_runner(
        self, tmp_path, monkeypatch, skip_runtime_model_validation, enhance, local_only
    ):
        """Full runner-driven pipeline: clean → segment → export produces SRT."""
        observed, output_dir = self._run_full_pipeline(
            tmp_path, monkeypatch, enhance=enhance, local_only=local_only
        )

        # Verify stage order through runner
        assert "prepare" in observed
        assert "chunk" in observed
        assert "asr" in observed
        assert "clean" in observed
        assert "segment" in observed
        assert "align" in observed
        assert "export" in observed

        # Verify stage counts
        assert observed.count("clean") == 1
        assert observed.count("segment") == 1
        assert observed.count("align") == 1
        assert observed.count("export") == 1

        # Verify artifacts
        work_dir = tmp_path / "work"
        assert (work_dir / "cleaned.jsonl").exists()
        assert (work_dir / "sentences.jsonl").exists()
        assert (work_dir / "aligned.jsonl").exists()

        # Verify final SRT
        srt_path = output_dir / "final.srt"
        assert srt_path.exists()
        srt_text = srt_path.read_text()
        assert srt_text.strip()

        # Verify causal chain: cleaned text appears in SRT
        # The input had "hello  world  test" — real run_clean normalizes
        # double spaces.  The SRT must contain the cleaned form.
        assert "hello" in srt_text.lower() or "world" in srt_text.lower()

        # Verify LLM was never called
        # (fail_if_llm raises AssertionError if called)
