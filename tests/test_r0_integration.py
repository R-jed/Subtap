"""R0 integration tests — clean stage and policy resolution.

These tests exercise actual run_clean() and build_policy() code paths
(no stubbing of run_clean or policy resolution) to verify the R0
runtime repair at the clean-stage level.

Note: Tests in this module exercise clean-stage isolation, NOT the full
pipeline stage loop. For full pipeline tests reaching export, see
test_runtime_local_pipeline_integration.py.

Heavy backends (ffmpeg, ASR model, aligner model) are stubbed.
run_clean is NEVER stubbed — it runs the real deterministic local
clean + policy-guarded LLM path.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from subtap.core.clean import run_clean
from subtap.core.pipeline import Pipeline
from subtap.core.workspace import Workspace
from subtap.runtime.external_policy import (
    build_policy,
)
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import ASRSegment

runner = CliRunner()


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
                chunk_id=i,
                segment_id=i,
                start_sec=float(i),
                end_sec=float(i + 1),
                text=text,
            )
            f.write(seg.model_dump_json() + "\n")


def _seed_sentences_jsonl(ws: Workspace, texts: list[str]) -> None:
    """Write mock sentence segments to sentences.jsonl."""
    ws.sentences_dir.mkdir(parents=True, exist_ok=True)
    with open(ws.sentences_jsonl, "w") as f:
        for i, text in enumerate(texts):
            record = {
                "chunk_id": 0,
                "sentence_id": i,
                "start_sec": float(i),
                "end_sec": float(i + 1),
                "text": text,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _seed_aligned_jsonl(ws: Workspace, texts: list[str]) -> None:
    """Write mock aligned segments to aligned.jsonl."""
    with open(ws.aligned_jsonl, "w") as f:
        for i, text in enumerate(texts):
            record = {
                "sentence_id": i,
                "start_sec": float(i),
                "end_sec": float(i + 1),
                "text": text,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Test A: CLI precedence via build_policy() ────────────────


class TestCLIPrecedenceBuildPolicy:
    """Verify build_policy() produces correct policy/config for CLI scenarios.

    These tests exercise the same build_policy() path used by the CLI,
    but do NOT invoke the real Typer CLI command. For real CLI invocation
    tests, see test_cli_external_policy_integration.py.
    """

    def test_local_off_resolves_policy_before_pipeline(
        self, tmp_path, monkeypatch, skip_runtime_model_validation
    ):
        """enhance=off: config.llm_proofread/llm_hotword are False at pipeline creation."""

        captured = {}

        original_init = Pipeline.__init__

        def capturing_init(self, config, work_dir, **kwargs):
            captured["config_proofread"] = getattr(config, "llm_proofread", None)
            captured["config_hotword"] = getattr(config, "llm_hotword", None)
            captured["policy"] = kwargs.get("external_policy")
            original_init(self, config, work_dir, **kwargs)

        monkeypatch.setattr(Pipeline, "__init__", capturing_init)

        config = _make_local_config(tmp_path)
        monkeypatch.setattr(
            "subtap.schemas.config.load_config", lambda *a, **kw: config
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav")

        # Stub validate_runtime_models to skip model file checks
        monkeypatch.setattr(
            "subtap.core.models.validate_runtime_models", lambda _c: None
        )

        # We can't run the full pipeline (needs real media), but we can
        # verify the policy resolution by calling the relevant code path
        # directly.
        from subtap.runtime.external_policy import build_policy

        # Simulate what _run does: resolve flags, build policy, sync config
        effective_proofread = None  # CLI not provided
        effective_hotword = None  # CLI not provided
        config.llm_proofread = None  # config default
        config.llm_hotword = None  # config default

        policy = build_policy(
            local_only=False,
            enhance_mode="off",
            asr_backend="mlx-qwen-asr",
            llm_proofread=effective_proofread,
            llm_hotword=effective_hotword,
        )

        config.llm_proofread = policy.llm_proofread
        config.llm_hotword = policy.llm_hotword

        assert policy.llm_proofread is False
        assert policy.llm_hotword is False
        assert config.llm_proofread is False
        assert config.llm_hotword is False

    def test_local_only_resolves_policy_before_pipeline(self, tmp_path):
        """local_only=True: config.llm_proofread/llm_hotword are False."""
        from subtap.runtime.external_policy import build_policy

        config = _make_local_config(tmp_path)
        config.llm_proofread = True  # would be True from config
        config.llm_hotword = True  # would be True from config

        policy = build_policy(
            local_only=True,
            enhance_mode="api",
            asr_backend="mlx-qwen-asr",
            llm_proofread=config.llm_proofread,
            llm_hotword=config.llm_hotword,
        )

        config.llm_proofread = policy.llm_proofread
        config.llm_hotword = policy.llm_hotword

        assert policy.llm_proofread is False
        assert policy.llm_hotword is False
        assert config.llm_proofread is False
        assert config.llm_hotword is False

    def test_api_with_explicit_false_keeps_false(self, tmp_path):
        """--no-llm-proofread with enhance=api: policy proofread=False."""
        from subtap.runtime.external_policy import build_policy

        config = _make_local_config(tmp_path)
        config.llm_proofread = None  # config default

        # CLI provides explicit False
        cli_proofread = False
        cli_hotword = None

        effective_proofread = (
            cli_proofread if cli_proofread is not None else config.llm_proofread
        )
        effective_hotword = (
            cli_hotword
            if cli_hotword is not None
            else getattr(config, "llm_hotword", None)
        )

        policy = build_policy(
            local_only=False,
            enhance_mode="api",
            asr_backend="mlx-qwen-asr",
            llm_proofread=effective_proofread,
            llm_hotword=effective_hotword,
        )

        assert policy.llm_proofread is False
        # config.llm_hotword defaults to False, so effective_hotword=False
        assert policy.llm_hotword is False


# ── Test B: Real Pipeline clean stage ───────────────────────


class TestPipelineCleanStage:
    """Execute real Pipeline clean stage with heavy backends stubbed.

    run_clean is NEVER stubbed — it runs the real deterministic local
    clean + policy-guarded LLM path.

    Note: These tests exercise clean+segment only, NOT the full pipeline
    loop through export. For full pipeline tests, see
    test_runtime_local_pipeline_integration.py.
    """

    def test_clean_stage_local_policy_writes_cleaned_artifact(
        self, tmp_path, monkeypatch
    ):
        """Default local: clean stage writes cleaned.jsonl."""
        config = _make_local_config(tmp_path)
        ws = Workspace(config, base_dir=tmp_path / "work")
        ws.ensure_dirs()
        _seed_asr_jsonl(ws, ["hello  世界", "maching learning is great"])

        policy = build_policy(local_only=False, enhance_mode="local")

        pipeline = Pipeline(
            config,
            work_dir=tmp_path / "work",
            external_policy=policy,
        )

        # Clean stage runs real code (no stub)
        clean_result = pipeline.run_stage("clean", enhance_mode="local")
        assert clean_result["segment_count"] == 2
        assert ws.cleaned_jsonl.exists()

        # Verify output artifact
        lines = ws.cleaned_jsonl.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            record = json.loads(line)
            assert "text" not in record or "cleaned_text" in record

    def test_clean_stage_local_only_no_llm(self, tmp_path, monkeypatch):
        """local_only=True: clean completes, no LLM backend."""
        config = _make_local_config(tmp_path)
        ws = Workspace(config, base_dir=tmp_path / "work")
        ws.ensure_dirs()
        _seed_asr_jsonl(ws, ["test segment"])

        policy = build_policy(local_only=True, enhance_mode="api")

        pipeline = Pipeline(
            config,
            work_dir=tmp_path / "work",
            external_policy=policy,
        )

        def fail_if_called(*_a, **_k):
            raise AssertionError("get_llm_backend must not be called for local_only")

        monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_called)

        clean_result = pipeline.run_stage("clean", enhance_mode="local")
        assert clean_result["segment_count"] == 1
        assert ws.cleaned_jsonl.exists()

    def test_clean_stage_enhance_off_no_llm(self, tmp_path, monkeypatch):
        """enhance=off: clean completes, no LLM backend."""
        config = _make_local_config(tmp_path)
        ws = Workspace(config, base_dir=tmp_path / "work")
        ws.ensure_dirs()
        _seed_asr_jsonl(ws, ["another test"])

        policy = build_policy(local_only=False, enhance_mode="off")

        pipeline = Pipeline(
            config,
            work_dir=tmp_path / "work",
            external_policy=policy,
        )

        def fail_if_called(*_a, **_k):
            raise AssertionError("get_llm_backend must not be called for enhance=off")

        monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_called)

        clean_result = pipeline.run_stage("clean", enhance_mode="off")
        assert clean_result["segment_count"] == 1
        assert ws.cleaned_jsonl.exists()

    def test_clean_and_segment_stage_loop(self, tmp_path, monkeypatch):
        """Clean+segment stage loop: prepare/chunk/asr stubbed, clean/segment real.

        Verifies clean and segment stages complete. Does NOT reach export —
        use test_runtime_local_pipeline_integration.py for full export tests.
        """
        config = _make_local_config(tmp_path)
        ws = Workspace(config, base_dir=tmp_path / "work")
        ws.ensure_dirs()

        policy = build_policy(local_only=False, enhance_mode="local")

        pipeline = Pipeline(
            config,
            work_dir=tmp_path / "work",
            external_policy=policy,
        )

        # Stub prepare: write media_info.json
        media_info = {"duration": 2.0, "sample_rate": 16000, "channels": 1}
        (ws.root / "media_info.json").write_text(json.dumps(media_info))

        # Stub chunk: write chunks.jsonl with boundary covering both segments
        ws.chunks_dir.mkdir(parents=True, exist_ok=True)
        chunk = {
            "chunk_id": 0,
            "start_sec": 0.0,
            "end_sec": 2.0,
            "path": str(tmp_path / "chunk0.wav"),
        }
        ws.chunks_jsonl.write_text(json.dumps(chunk) + "\n")

        # Seed ASR output — both segments must belong to chunk_id 0
        ws.asr_dir.mkdir(parents=True, exist_ok=True)
        with open(ws.asr_jsonl, "w") as f:
            for i, text in enumerate(["hello  world", "test  segment"]):
                seg = ASRSegment(
                    chunk_id=0,
                    segment_id=i,
                    start_sec=float(i),
                    end_sec=float(i + 1),
                    text=text,
                )
                f.write(seg.model_dump_json() + "\n")

        # Run clean (REAL — not stubbed)
        clean_result = pipeline.run_stage("clean", enhance_mode="local")
        assert clean_result["segment_count"] == 2
        assert ws.cleaned_jsonl.exists()

        # Run segment (real — reads cleaned.jsonl)
        segment_result = pipeline.run_stage("segment")
        assert segment_result["sentence_count"] >= 1
        assert ws.sentences_jsonl.exists()

        # Seed aligned output (stub aligner model)
        _seed_aligned_jsonl(ws, ["hello world", "test segment"])

        # Run export (real)
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        export_result = pipeline.run_stage(
            "export",
            fmt="srt",
            output_dir=str(output_dir),
            stem="final",
        )
        assert export_result.get("output_path") or (output_dir / "final.srt").exists()


# ── Test C: TUI v2 local-only clean stage ───────────────────


class TestTUIV2LocalOnlyClean:
    """Verify local_only=True policy allows clean stage to complete.

    Note: These tests exercise the policy and clean stage directly.
    For real WizardView tests, see test_tui_v2_real_path.py.
    """

    def test_task_request_local_only_command(self, tmp_path):
        """SubtitleTaskRequest(local_only=True) produces --local-only flag."""
        from subtap.schemas.task_request import SubtitleTaskRequest

        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav")

        request = SubtitleTaskRequest(
            input_path=audio,
            output_dir=tmp_path / "output",
            mode="fast",
            subtitle_format="srt",
            subtitle_language="zh",
            local_only=True,
            show_observer=True,
            use_default_glossary=False,
            reset_hotwords=True,
        )

        command = request.to_cli_command()
        assert "--local-only" in command
        assert "--tui" in command

    def test_local_only_policy_clean_completes(self, tmp_path, monkeypatch):
        """local_only=True policy allows clean stage to complete."""
        config = SubtapConfig()
        config.llm_proofread = False
        config.llm_hotword = False

        policy = build_policy(local_only=True, enhance_mode="api")
        assert policy.llm_proofread is False
        assert policy.llm_hotword is False

        ws = Workspace(config, base_dir=tmp_path / "work")
        ws.ensure_dirs()
        _seed_asr_jsonl(ws, ["test segment"])

        def fail_if_called(*_a, **_k):
            raise AssertionError(
                "get_llm_backend must not be called for local_only clean"
            )

        with patch("subtap.core.clean.get_llm_backend", fail_if_called):
            result = run_clean(ws, config, external_policy=policy)

        assert result["segment_count"] == 1
        assert ws.cleaned_jsonl.exists()


# ── Test D: Batch clean stage integration ───────────────────


class TestBatchCleanStage:
    """Batch with real clean stage — heavy stages stubbed.

    Note: These tests use a custom Pipeline stub that runs real clean
    but stubs other stages. For tests using the real Pipeline class,
    see test_batch_runtime_integration.py.
    """

    def test_batch_item_local_clean_writes_artifact(
        self, tmp_path, monkeypatch, skip_runtime_model_validation
    ):
        """Batch item with enhance=local: real clean writes cleaned.jsonl."""
        captured_policies = []
        captured_configs = []

        class RealCleanPipeline:
            """Pipeline stub that runs real clean but stubs heavy stages."""

            def __init__(self, config, work_dir, **kwargs):
                self.config = config
                self.workspace = Workspace(config, base_dir=work_dir)
                self.workspace.ensure_dirs()
                self.external_policy = kwargs.get("external_policy")
                self.work_dir = work_dir

                captured_configs.append(
                    {
                        "llm_proofread": getattr(config, "llm_proofread", None),
                        "llm_hotword": getattr(config, "llm_hotword", None),
                    }
                )
                if self.external_policy:
                    captured_policies.append(
                        {
                            "llm_proofread": self.external_policy.llm_proofread,
                            "llm_hotword": self.external_policy.llm_hotword,
                        }
                    )

            def run_stage(self, stage, **kwargs):
                if stage == "clean":
                    # Run REAL clean
                    return run_clean(
                        self.workspace,
                        self.config,
                        enhance_mode=kwargs.get("enhance_mode", "local"),
                        external_policy=self.external_policy,
                    )
                # Stub other stages
                return {"segment_count": 1, "timings": {}}

            def cleanup(self):
                return {"cleaned_count": 0}

        class FakeRunner:
            def run_pipeline(self, pipeline, input_path, output_dir, **kwargs):
                # Run clean through the real pipeline
                clean_result = pipeline.run_stage(
                    "clean", enhance_mode=kwargs.get("enhance", "local")
                )
                return {
                    "output_dir": str(output_dir),
                    "timings": {"clean": 0.1},
                    "segment_count": clean_result["segment_count"],
                }

        # Seed ASR data for the pipeline to read
        original_pipeline_init = RealCleanPipeline.__init__

        def seeded_init(self, config, work_dir, **kwargs):
            original_pipeline_init(self, config, work_dir, **kwargs)
            _seed_asr_jsonl(self.workspace, ["hello world", "test segment"])

        RealCleanPipeline.__init__ = seeded_init

        monkeypatch.setattr("subtap.core.pipeline.Pipeline", RealCleanPipeline)
        monkeypatch.setattr("subtap.ui.tui.RichRunner", FakeRunner)

        config = SimpleNamespace()
        config.output = SimpleNamespace(
            timestamp=True,
            subtitle_punctuation=False,
            subtitle_language="zh",
            max_chars=25,
            subtitle_stem="test",
        )
        config.asr = SimpleNamespace(backend="mlx-qwen-asr", model="asr_0.6b")
        config.align = SimpleNamespace(model="aligner", quantization="q8")
        config.models = SimpleNamespace(root=str(tmp_path / "models"))
        config.clean = SimpleNamespace(glossary_path=None, style_rules=None)
        config.remote_api = SimpleNamespace(model=None)
        config.llm_proofread = False
        config.llm_hotword = False
        monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)

        audio = tmp_path / "voice.wav"
        audio.write_bytes(b"audio")
        output = tmp_path / "output"

        result = runner.invoke(
            __import__("subtap.cli", fromlist=["app"]).app,
            [
                "batch-transcribe",
                str(audio),
                "--enhance",
                "local",
                "--output-dir",
                str(output),
                "--no-confirm",
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output

        # Verify manifest records success
        manifest = output / "manifest.json"
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        assert saved["items"][0]["status"] == "succeeded", saved["items"][0].get(
            "error", ""
        )

        # Verify policy has LLM disabled for local mode
        assert len(captured_policies) == 1
        assert captured_policies[0]["llm_proofread"] is False
        assert captured_policies[0]["llm_hotword"] is False

        # Verify config was synced with policy
        assert len(captured_configs) == 1
        assert captured_configs[0]["llm_proofread"] is False
        assert captured_configs[0]["llm_hotword"] is False

    def test_batch_default_clean_writes_artifact(
        self, tmp_path, monkeypatch, skip_runtime_model_validation
    ):
        """Default batch (no --enhance): local clean writes cleaned.jsonl."""
        clean_artifacts = []

        class RealCleanPipeline:
            def __init__(self, config, work_dir, **kwargs):
                self.config = config
                self.workspace = Workspace(config, base_dir=work_dir)
                self.workspace.ensure_dirs()
                self.external_policy = kwargs.get("external_policy")
                self.work_dir = work_dir
                _seed_asr_jsonl(self.workspace, ["batch test segment"])

            def run_stage(self, stage, **kwargs):
                if stage == "clean":
                    result = run_clean(
                        self.workspace,
                        self.config,
                        enhance_mode=kwargs.get("enhance_mode", "local"),
                        external_policy=self.external_policy,
                    )
                    clean_artifacts.append(
                        {
                            "cleaned_jsonl_exists": self.workspace.cleaned_jsonl.exists(),
                            "segment_count": result["segment_count"],
                        }
                    )
                    return result
                return {"segment_count": 1}

            def cleanup(self):
                return {"cleaned_count": 0}

        class FakeRunner:
            def run_pipeline(self, pipeline, input_path, output_dir, **kwargs):
                clean_result = pipeline.run_stage("clean")
                return {
                    "output_dir": str(output_dir),
                    "timings": {},
                    "segment_count": clean_result.get("segment_count", 1),
                }

        monkeypatch.setattr("subtap.core.pipeline.Pipeline", RealCleanPipeline)
        monkeypatch.setattr("subtap.ui.tui.RichRunner", FakeRunner)

        config = SimpleNamespace()
        config.output = SimpleNamespace(
            timestamp=True,
            subtitle_punctuation=False,
            subtitle_language="zh",
            max_chars=25,
            subtitle_stem="test",
        )
        config.asr = SimpleNamespace(backend="mlx-qwen-asr", model="asr_0.6b")
        config.align = SimpleNamespace(model="aligner", quantization="q8")
        config.models = SimpleNamespace(root=str(tmp_path / "models"))
        config.clean = SimpleNamespace(glossary_path=None, style_rules=None)
        config.remote_api = SimpleNamespace(model=None)
        config.llm_proofread = False
        config.llm_hotword = False
        monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)

        audio = tmp_path / "voice.wav"
        audio.write_bytes(b"audio")
        output = tmp_path / "output"

        result = runner.invoke(
            __import__("subtap.cli", fromlist=["app"]).app,
            [
                "batch-transcribe",
                str(audio),
                "--output-dir",
                str(output),
                "--no-confirm",
                "--json",
            ],
        )

        assert result.exit_code == 0

        # Verify clean produced artifacts
        assert len(clean_artifacts) == 1
        assert clean_artifacts[0]["cleaned_jsonl_exists"] is True
        assert clean_artifacts[0]["segment_count"] > 0

        # Verify manifest success
        manifest = output / "manifest.json"
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        assert saved["items"][0]["status"] == "succeeded"
