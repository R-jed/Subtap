"""Tests for Pipeline fail-fast enforcement on missing external_policy.

AC-6: Pipeline fails fast when an external-capable stage lacks policy.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from subtap.core.pipeline import Pipeline
from subtap.core.tracked_pipeline import TrackedPipeline
from subtap.runtime.external_policy import (
    ExternalProcessingError,
    MissingExternalProcessingPolicyError,
    build_policy,
)
from subtap.schemas.config import load_config


@pytest.fixture()
def config(tmp_path: Path):
    """Minimal config for Pipeline construction."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}")
    return load_config(config_path)


@pytest.fixture()
def work_dir(tmp_path: Path):
    return tmp_path / "work"


def _run_stage_kwargs(stage: str) -> dict:
    """Return the extra kwargs needed to dispatch a given stage."""
    if stage == "translate":
        return {"target_language": "en"}
    return {}


# ── MissingExternalProcessingPolicyError ─────────────────────────


class TestMissingExternalProcessingPolicyError:
    """MissingExternalProcessingPolicyError is a RuntimeError subclass."""

    def test_is_runtime_error(self):
        assert issubclass(MissingExternalProcessingPolicyError, RuntimeError)

    def test_can_be_raised_with_message(self):
        with pytest.raises(MissingExternalProcessingPolicyError, match="test message"):
            raise MissingExternalProcessingPolicyError("test message")


# ── Pipeline dispatch without policy ─────────────────────────────


class TestPipelineMissingPolicyDispatch:
    """Pipeline raises MissingExternalProcessingPolicyError when
    external-capable stages are dispatched without policy."""

    def test_asr_without_policy_raises(self, config, work_dir):
        pipeline = Pipeline(config, work_dir=work_dir)
        assert pipeline.external_policy is None
        with pytest.raises(MissingExternalProcessingPolicyError, match="asr"):
            pipeline.run_stage("asr")

    def test_clean_without_policy_raises(self, config, work_dir):
        pipeline = Pipeline(config, work_dir=work_dir)
        assert pipeline.external_policy is None
        with pytest.raises(MissingExternalProcessingPolicyError, match="clean"):
            pipeline.run_stage("clean")

    def test_translate_without_policy_raises(self, config, work_dir):
        pipeline = Pipeline(config, work_dir=work_dir)
        assert pipeline.external_policy is None
        with pytest.raises(MissingExternalProcessingPolicyError, match="translate"):
            pipeline.run_stage("translate", target_language="en")


# ── No backend factory called on missing policy (AC-6) ───────────


class TestNoBackendFactoryOnMissingPolicy:
    """When policy is missing, backend factory constructors are never called."""

    STAGES_AND_PATCHES = [
        ("asr", "subtap.core.asr.get_backend"),
        ("clean", "subtap.core.clean.get_llm_backend"),
        ("translate", "subtap.core.translate.get_translator"),
    ]

    @pytest.mark.parametrize("stage, patch_target", STAGES_AND_PATCHES)
    def test_backend_factory_not_called(self, config, work_dir, stage, patch_target):
        pipeline = Pipeline(config, work_dir=work_dir)
        mock_factory = MagicMock()
        with patch(patch_target, mock_factory):
            with pytest.raises(MissingExternalProcessingPolicyError):
                pipeline.run_stage(stage, **_run_stage_kwargs(stage))
        mock_factory.assert_not_called()


# ── Pipeline dispatch with policy (no false positives) ───────────


class TestPipelineWithPolicyDispatch:
    """Pipeline does NOT raise MissingExternalProcessingPolicyError
    when policy is provided. Pure local stages never require policy."""

    def test_prepare_without_policy_ok(self, config, work_dir):
        """prepare is a pure local stage — no policy required."""
        pipeline = Pipeline(config, work_dir=work_dir)
        # prepare requires input_path, but the point is it doesn't
        # raise MissingExternalProcessingPolicyError
        with pytest.raises(ValueError, match="input_path"):
            pipeline.run_stage("prepare")

    def test_asr_with_deny_policy_raises_external_error(self, config, work_dir):
        """With a deny policy, ASR raises ExternalProcessingError
        (not MissingExternalProcessingPolicyError)."""
        policy = build_policy(
            local_only=True,
            enhance_mode="local",
            asr_backend="http-asr",
        )
        pipeline = Pipeline(config, work_dir=work_dir, external_policy=policy)
        # The assertion happens inside run_asr, not in run_stage dispatch
        with pytest.raises(ExternalProcessingError) as exc_info:
            pipeline.run_stage("asr", backend_name="http-asr")
        # Must NOT be a missing-policy error
        assert not isinstance(exc_info.value, MissingExternalProcessingPolicyError)


# ── Error message contract ───────────────────────────────────────


class TestMissingPolicyErrorMessage:
    """Error messages identify stage, missing policy, migration hint."""

    STAGES = ["asr", "clean", "translate"]

    @pytest.mark.parametrize("stage", STAGES)
    def test_message_contains_stage_name(self, config, work_dir, stage):
        pipeline = Pipeline(config, work_dir=work_dir)
        with pytest.raises(MissingExternalProcessingPolicyError, match=stage):
            pipeline.run_stage(stage, **_run_stage_kwargs(stage))

    @pytest.mark.parametrize("stage", STAGES)
    def test_message_mentions_policy(self, config, work_dir, stage):
        pipeline = Pipeline(config, work_dir=work_dir)
        with pytest.raises(
            MissingExternalProcessingPolicyError,
            match="ExternalProcessingPolicy",
        ):
            pipeline.run_stage(stage, **_run_stage_kwargs(stage))


# ── Pure-local stages succeed without policy (Contract B) ────────


class TestPureLocalStagesWithoutPolicy:
    """Pure-local stages dispatch successfully without external_policy.

    Each stage handler is monkeypatched to return a deterministic result,
    proving that MissingExternalProcessingPolicyError is never raised
    for non-external-capable stages.
    """

    STAGE_HANDLER_KWARGS = [
        ("prepare", "_stage_prepare", {"input_path": Path("/dev/null")}),
        ("chunk", "_stage_chunk", {}),
        ("segment", "_stage_segment", {}),
        ("align", "_stage_align", {}),
        ("export", "_stage_export", {}),
    ]

    @pytest.mark.parametrize("stage, handler, kwargs", STAGE_HANDLER_KWARGS)
    def test_stage_dispatches_without_policy(
        self, config, work_dir, monkeypatch, stage, handler, kwargs
    ):
        """Stage dispatches without raising MissingExternalProcessingPolicyError."""
        sentinel = {"called": False, "result": {"ok": True}}

        def fake_handler(**_kw):
            sentinel["called"] = True
            return sentinel["result"]

        pipeline = Pipeline(config, work_dir=work_dir)
        assert pipeline.external_policy is None
        monkeypatch.setattr(pipeline, handler, fake_handler)

        result = pipeline.run_stage(stage, **kwargs)

        assert sentinel["called"], f"{handler} was not called"
        assert result == sentinel["result"]


# ── TrackedPipeline checkpoint mutation (Contract C) ─────────────


class TestTrackedPipelineMissingPolicyNoCheckpoint:
    """TrackedPipeline must not mutate state before rejecting a missing policy."""

    def test_clean_missing_policy_no_checkpoint_mutation(self, config, work_dir):
        """MissingExternalProcessingPolicyError on clean without policy,
        with zero save_state or mark_running calls."""
        pipeline = TrackedPipeline(config, work_dir=work_dir, stage_order=["clean"])
        assert pipeline.external_policy is None

        # Spy on state mutation methods — record calls without executing
        save_calls = []
        running_calls = []
        failed_calls = []

        pipeline.save_state = lambda: save_calls.append(1)
        pipeline.state.mark_running = lambda s: running_calls.append(s)
        pipeline.state.mark_failed = lambda s, m="": failed_calls.append(s)

        with pytest.raises(MissingExternalProcessingPolicyError, match="clean"):
            pipeline.run_stage("clean")

        assert save_calls == [], "save_state must not be called before policy rejection"
        assert (
            running_calls == []
        ), "mark_running must not be called before policy rejection"
        assert (
            failed_calls == []
        ), "mark_failed must not be called before policy rejection"
