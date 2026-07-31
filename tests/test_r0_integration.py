"""R0 integration tests — focused clean-stage and policy resolution.

These tests exercise actual run_clean() and build_policy() code paths
to verify the R0 runtime repair at the clean-stage level.

For full runner-driven pipeline tests reaching export, see
test_runtime_local_pipeline_integration.py.
For real CLI invocation tests, see test_cli_external_policy_integration.py.
For real batch runner tests, see test_batch_runtime_integration.py.
"""

from __future__ import annotations

from unittest.mock import patch

from subtap.core.clean import run_clean
from subtap.core.workspace import Workspace
from subtap.runtime.external_policy import build_policy
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import ASRSegment

# ── Helpers ─────────────────────────────────────────────────


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


# ── Test: local_only policy allows clean stage ──────────────


class TestTUIV2LocalOnlyClean:
    """Verify local_only=True policy allows clean stage to complete.

    Tests the core regression: with local_only=True and both LLM features
    disabled, run_clean() completes without calling assert_clean_llm_allowed().
    """

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
