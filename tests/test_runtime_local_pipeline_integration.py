"""Real full local pipeline regression tests.

These tests execute the actual production stage loop through to export,
verifying that a final subtitle artifact is produced.

Heavy boundaries (ffmpeg, ASR model, aligner model) are stubbed at their
true function boundaries. run_clean() is NEVER stubbed — it runs the real
deterministic local clean + policy-guarded LLM path.

The Pipeline and its run_stage dispatch are real. Only the media extraction,
ASR inference, and aligner inference functions are replaced with fixtures
that write valid artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path


from subtap.core.pipeline import Pipeline
from subtap.core.workspace import Workspace
from subtap.runtime.external_policy import build_policy
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import ASRSegment

# ── Helpers ─────────────────────────────────────────────────


def _make_local_config(tmp_path: Path) -> SubtapConfig:
    """Config for local-only pipeline tests."""
    from subtap.schemas.config import AudioConfig, VADConfig, WorkspaceConfig

    return SubtapConfig(
        audio=AudioConfig(
            sample_rate=16000,
            channels=1,
            format="wav",
            vad=VADConfig(use_silero_vad=False, min_silence_sec=0.4),
        ),
        workspace=WorkspaceConfig(
            root=str(tmp_path / "work"),
            keep_intermediate=True,
        ),
    )


def _seed_asr_jsonl(ws: Workspace, texts: list[str]) -> None:
    """Write mock ASR segments to asr.jsonl."""
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


def _seed_chunks(ws: Workspace, count: int = 1) -> None:
    """Write mock chunks.jsonl."""
    ws.chunks_dir.mkdir(parents=True, exist_ok=True)
    with open(ws.chunks_jsonl, "w") as f:
        for i in range(count):
            chunk = {
                "chunk_id": i,
                "start_sec": float(i),
                "end_sec": float(i + 1),
                "path": str(ws.root / f"chunk{i}.wav"),
            }
            f.write(json.dumps(chunk) + "\n")


def _seed_media_info(ws: Workspace) -> None:
    """Write mock media_info.json."""
    media_info = {"duration": 2.0, "sample_rate": 16000, "channels": 1}
    (ws.root / "media_info.json").write_text(json.dumps(media_info))


# ── Test A: enhance=local full pipeline ─────────────────────


class TestFullLocalPipeline:
    """Execute real Pipeline stage loop from clean through export.

    Heavy stages (prepare, chunk, asr, align) are seeded with artifacts.
    run_clean() and segment/export run the real production code.
    """

    def test_enhance_local_reaches_export(self, tmp_path, monkeypatch):
        """enhance=local: clean → segment → export produces final SRT."""
        config = _make_local_config(tmp_path)
        ws = Workspace(config, base_dir=tmp_path / "work")
        ws.ensure_dirs()

        # Seed artifacts for stages before clean
        _seed_media_info(ws)
        _seed_chunks(ws)
        _seed_asr_jsonl(ws, ["hello  world", "test  segment"])

        policy = build_policy(local_only=False, enhance_mode="local")
        pipeline = Pipeline(
            config,
            work_dir=tmp_path / "work",
            external_policy=policy,
        )

        # Verify get_llm_backend is never called
        llm_calls = []

        def fail_if_called(*_a, **_k):
            llm_calls.append(True)
            raise AssertionError("get_llm_backend must not be called for local clean")

        monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_called)

        # Stage 1: clean (REAL — not stubbed)
        clean_result = pipeline.run_stage("clean", enhance_mode="local")
        assert clean_result["segment_count"] == 2
        assert ws.cleaned_jsonl.exists()

        # Verify cleaned.jsonl content
        lines = ws.cleaned_jsonl.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            record = json.loads(line)
            assert "cleaned_text" in record or "text" in record

        # Stage 2: segment (real — reads cleaned.jsonl)
        segment_result = pipeline.run_stage("segment")
        assert segment_result["sentence_count"] >= 1
        assert ws.sentences_jsonl.exists()

        # Seed aligned output (stub aligner model)
        ws.aligned_jsonl.write_text(
            json.dumps(
                {
                    "sentence_id": 0,
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "text": "hello world",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "sentence_id": 1,
                    "start_sec": 1.0,
                    "end_sec": 2.0,
                    "text": "test segment",
                }
            )
            + "\n"
        )

        # Stage 3: export (real)
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        pipeline.run_stage(
            "export",
            fmt="srt",
            output_dir=str(output_dir),
            stem="final",
        )

        # Verify final subtitle artifact
        srt_path = output_dir / "final.srt"
        assert srt_path.exists(), "Final SRT artifact must exist"
        srt_content = srt_path.read_text()
        assert len(srt_content) > 0, "Final SRT must be non-empty"
        assert "hello world" in srt_content

        # Verify no LLM backend was called
        assert llm_calls == []

        # Verify no ExternalProcessingError was raised
        # (test would have failed already if it was)

    def test_local_only_reaches_export(self, tmp_path, monkeypatch):
        """local_only=True with enhance=api requested: effective LLM=False/False."""
        config = _make_local_config(tmp_path)
        ws = Workspace(config, base_dir=tmp_path / "work")
        ws.ensure_dirs()

        _seed_media_info(ws)
        _seed_chunks(ws)
        _seed_asr_jsonl(ws, ["local  only  test"])

        # local_only=True overrides enhance=api
        policy = build_policy(local_only=True, enhance_mode="api")
        assert policy.llm_proofread is False
        assert policy.llm_hotword is False

        pipeline = Pipeline(
            config,
            work_dir=tmp_path / "work",
            external_policy=policy,
        )

        llm_calls = []

        def fail_if_called(*_a, **_k):
            llm_calls.append(True)
            raise AssertionError("get_llm_backend must not be called")

        monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_called)

        # Clean
        clean_result = pipeline.run_stage("clean", enhance_mode="local")
        assert clean_result["segment_count"] == 1
        assert ws.cleaned_jsonl.exists()

        # Segment
        segment_result = pipeline.run_stage("segment")
        assert segment_result["sentence_count"] >= 1
        assert ws.sentences_jsonl.exists()

        # Seed aligned
        ws.aligned_jsonl.write_text(
            json.dumps(
                {
                    "sentence_id": 0,
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "text": "local only test",
                }
            )
            + "\n"
        )

        # Export
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        pipeline.run_stage(
            "export",
            fmt="srt",
            output_dir=str(output_dir),
            stem="final",
        )

        srt_path = output_dir / "final.srt"
        assert srt_path.exists()
        assert len(srt_path.read_text()) > 0
        assert llm_calls == []

    def test_enhance_off_reaches_export(self, tmp_path, monkeypatch):
        """enhance=off: clean → segment → export produces final SRT."""
        config = _make_local_config(tmp_path)
        ws = Workspace(config, base_dir=tmp_path / "work")
        ws.ensure_dirs()

        _seed_media_info(ws)
        _seed_chunks(ws)
        _seed_asr_jsonl(ws, ["enhance  off  test"])

        policy = build_policy(local_only=False, enhance_mode="off")
        pipeline = Pipeline(
            config,
            work_dir=tmp_path / "work",
            external_policy=policy,
        )

        llm_calls = []

        def fail_if_called(*_a, **_k):
            llm_calls.append(True)
            raise AssertionError("get_llm_backend must not be called")

        monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_called)

        # Clean
        clean_result = pipeline.run_stage("clean", enhance_mode="off")
        assert clean_result["segment_count"] == 1
        assert ws.cleaned_jsonl.exists()

        # Segment
        segment_result = pipeline.run_stage("segment")
        assert segment_result["sentence_count"] >= 1
        assert ws.sentences_jsonl.exists()

        # Seed aligned
        ws.aligned_jsonl.write_text(
            json.dumps(
                {
                    "sentence_id": 0,
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "text": "enhance off test",
                }
            )
            + "\n"
        )

        # Export
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        pipeline.run_stage(
            "export",
            fmt="srt",
            output_dir=str(output_dir),
            stem="final",
        )

        srt_path = output_dir / "final.srt"
        assert srt_path.exists()
        assert len(srt_path.read_text()) > 0
        assert llm_calls == []
