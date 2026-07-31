"""Real CLI precedence integration tests.

These tests invoke the real Typer CLI command and capture the actual
policy objects returned by build_policy() to verify CLI-over-config
precedence.

The real _run() code path executes:
  load_config → merge config mode → resolve CLI precedence →
  build_policy → sync config → construct TrackedPipeline → _execute_pipeline

build_policy() is intercepted at the module boundary to capture the
resolved policy. _execute_pipeline is stubbed to verify config sync.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


def _make_config(tmp_path: Path, **overrides) -> SimpleNamespace:
    """Build a minimal config that satisfies the CLI run path."""
    config = SimpleNamespace(
        mode=overrides.get("mode", "online"),
        translate_to="",
        asr=SimpleNamespace(
            backend=overrides.get("asr_backend", "mlx-qwen-asr"),
            model="asr_0.6b",
            hotwords=[],
        ),
        align=SimpleNamespace(model="aligner", quantization="q8"),
        clean=SimpleNamespace(
            glossary_path=None,
            style_rules=None,
            backend="local",
        ),
        output=SimpleNamespace(
            timestamp=True,
            subtitle_punctuation=False,
            subtitle_language="zh",
            subtitle_stem="test",
            max_chars=25,
            directory=str(tmp_path / "output"),
            generate_metrics=False,
            script_path=None,
            script_mode="follow_script",
        ),
        workspace=SimpleNamespace(root=str(tmp_path / "work")),
        models=SimpleNamespace(root=str(tmp_path / "models")),
        remote_api=SimpleNamespace(model=None, base_url="", api_key_env=""),
        metrics=SimpleNamespace(output_path="metrics.json"),
        cleanup=SimpleNamespace(auto_cleanup=False, keep_chunks=False),
    )
    config.llm_proofread = overrides.get("llm_proofread", None)
    config.llm_hotword = overrides.get("llm_hotword", None)
    return config


def _setup_cli_patches(monkeypatch, config: SimpleNamespace, captured: list):
    """Apply all necessary monkeypatches for the CLI run path.

    Captures policy at the build_policy boundary and config at the
    _execute_pipeline boundary. This avoids depending on TrackedPipeline
    internals.
    """
    from subtap.cli import pipeline_cli as pcl_mod
    from subtap.runtime import external_policy as ep_mod

    original_build_policy = ep_mod.build_policy

    def capturing_build_policy(*args, **kwargs):
        policy = original_build_policy(*args, **kwargs)
        captured.append(
            {
                "policy_object": policy,
                "policy_proofread": policy.llm_proofread,
                "policy_hotword": policy.llm_hotword,
                "policy_local_only": policy.local_only,
                "policy_enhance_mode": policy.enhance_mode.value,
                "policy_remote_asr": policy.remote_asr,
                "policy_translation": policy.translation,
            }
        )
        return policy

    # Patch both the module attribute and the local import in pipeline_cli
    monkeypatch.setattr(ep_mod, "build_policy", capturing_build_policy)
    monkeypatch.setattr(pcl_mod, "build_policy", capturing_build_policy)

    def capturing_execute(pipeline, *args, **kwargs):
        cfg = pipeline.config
        if captured:
            captured[0].update(
                {
                    "pipeline_policy": getattr(pipeline, "external_policy", None),
                    "config_proofread": getattr(cfg, "llm_proofread", None),
                    "config_hotword": getattr(cfg, "llm_hotword", None),
                }
            )
        return {}

    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda _p, **_kw: config,
    )
    monkeypatch.setattr("subtap.core.models.validate_runtime_models", lambda _c: None)
    monkeypatch.setattr("subtap.cli.pipeline_cli._execute_pipeline", capturing_execute)
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli.PipelineProfiler",
        type(
            "FakeProfiler",
            (),
            {
                "__init__": lambda self, *a, **kw: None,
                "wrap_pipeline": lambda self, p: None,
            },
        ),
    )
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._generate_metrics",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._safe_add_recent_task",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._safe_attach_recent_task_process",
        lambda *a, **kw: None,
    )
    from subtap.metrics import events as events_mod

    monkeypatch.setattr(
        events_mod,
        "EventBus",
        type(
            "FakeEventBus",
            (),
            {
                "__init__": lambda self, **kw: None,
                "publish_nowait": lambda self, *a, **kw: None,
            },
        ),
    )
    from subtap.metrics import run_log as run_log_mod

    monkeypatch.setattr(
        run_log_mod,
        "RunLog",
        type(
            "FakeRunLog",
            (),
            {
                "__init__": lambda self, **kw: None,
                "_start_time": None,
                "system": lambda self: None,
                "input": lambda self, **kw: None,
                "config_snapshot": lambda self, *a: None,
                "hotwords": lambda self, **kw: None,
                "stage": lambda self, *a, **kw: None,
                "finalize": lambda self, *a, **kw: None,
            },
        ),
    )


# ── Test 1: config=None, enhance=api → defaults True ────────


def test_config_none_enhance_api_defaults_true(tmp_path, monkeypatch):
    """config proofread=None, hotword=None, enhance=api → both True."""
    config = _make_config(tmp_path)
    captured = []
    _setup_cli_patches(monkeypatch, config, captured)

    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake-wav")

    result = runner.invoke(
        app,
        [
            "run",
            str(audio),
            "--enhance",
            "api",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
            "--no-cleanroom",
            "--no-git-check",
            "--no-tui",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(captured) == 1, f"Expected 1 capture, got {len(captured)}"
    c = captured[0]
    assert c["policy_proofread"] is True, f"captured={c}"
    assert c["policy_hotword"] is True, f"captured={c}"
    assert c["config_proofread"] is True, f"captured={c}"
    assert c["config_hotword"] is True, f"captured={c}"
    # Policy object identity: Pipeline receives the exact same policy
    assert (
        c["pipeline_policy"] is c["policy_object"]
    ), "pipeline.external_policy is not the build_policy() result"
    assert c["config_proofread"] == c["policy_proofread"]
    assert c["config_hotword"] == c["policy_hotword"]


# ── Test 2: config hotword=False, enhance=api → keeps False ──


def test_config_hotword_false_enhance_api_keeps_false(tmp_path, monkeypatch):
    """config hotword=False, enhance=api → policy hotword=False."""
    config = _make_config(tmp_path, llm_hotword=False)
    captured = []
    _setup_cli_patches(monkeypatch, config, captured)

    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake-wav")

    result = runner.invoke(
        app,
        [
            "run",
            str(audio),
            "--enhance",
            "api",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
            "--no-cleanroom",
            "--no-git-check",
            "--no-tui",
        ],
    )

    assert result.exit_code == 0, result.output
    c = captured[0]
    assert c["policy_hotword"] is False, f"captured={c}"
    assert c["config_hotword"] is False, f"captured={c}"
    assert c["pipeline_policy"] is c["policy_object"]
    assert c["config_hotword"] == c["policy_hotword"]


# ── Test 3: --no-llm-proofread, enhance=api → proofread=False ─


def test_cli_no_proofread_enhance_api(tmp_path, monkeypatch):
    """--no-llm-proofread overrides config=None → policy proofread=False."""
    config = _make_config(tmp_path)
    captured = []
    _setup_cli_patches(monkeypatch, config, captured)

    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake-wav")

    result = runner.invoke(
        app,
        [
            "run",
            str(audio),
            "--enhance",
            "api",
            "--no-llm-proofread",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
            "--no-cleanroom",
            "--no-git-check",
            "--no-tui",
        ],
    )

    assert result.exit_code == 0, result.output
    c = captured[0]
    assert c["policy_proofread"] is False, f"captured={c}"
    assert c["config_proofread"] is False, f"captured={c}"
    assert c["pipeline_policy"] is c["policy_object"]
    assert c["config_proofread"] == c["policy_proofread"]


# ── Test 4: --llm-hotword, enhance=api → hotword=True ────────


def test_cli_hotword_enhance_api(tmp_path, monkeypatch):
    """--llm-hotword with enhance=api → policy hotword=True."""
    config = _make_config(tmp_path)
    captured = []
    _setup_cli_patches(monkeypatch, config, captured)

    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake-wav")

    result = runner.invoke(
        app,
        [
            "run",
            str(audio),
            "--enhance",
            "api",
            "--llm-hotword",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
            "--no-cleanroom",
            "--no-git-check",
            "--no-tui",
        ],
    )

    assert result.exit_code == 0, result.output
    c = captured[0]
    assert c["policy_hotword"] is True, f"captured={c}"
    assert c["config_hotword"] is True, f"captured={c}"
    assert c["pipeline_policy"] is c["policy_object"]
    assert c["config_hotword"] == c["policy_hotword"]


# ── Test 5: --llm-proofread, enhance=local → forced off ──────


def test_cli_proofread_enhance_local_forced_off(tmp_path, monkeypatch):
    """--llm-proofread with enhance=local → policy proofread=False."""
    config = _make_config(tmp_path)
    captured = []
    _setup_cli_patches(monkeypatch, config, captured)

    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake-wav")

    result = runner.invoke(
        app,
        [
            "run",
            str(audio),
            "--enhance",
            "local",
            "--llm-proofread",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
            "--no-cleanroom",
            "--no-git-check",
            "--no-tui",
        ],
    )

    assert result.exit_code == 0, result.output
    c = captured[0]
    assert c["policy_proofread"] is False, f"captured={c}"
    assert c["config_proofread"] is False, f"captured={c}"
    assert c["pipeline_policy"] is c["policy_object"]
    assert c["config_proofread"] == c["policy_proofread"]


# ── Test 6: --llm-hotword, enhance=off → forced off ──────────


def test_cli_hotword_enhance_off_forced_off(tmp_path, monkeypatch):
    """--llm-hotword with enhance=off → policy hotword=False."""
    config = _make_config(tmp_path)
    captured = []
    _setup_cli_patches(monkeypatch, config, captured)

    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake-wav")

    result = runner.invoke(
        app,
        [
            "run",
            str(audio),
            "--enhance",
            "off",
            "--llm-hotword",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
            "--no-cleanroom",
            "--no-git-check",
            "--no-tui",
        ],
    )

    assert result.exit_code == 0, result.output
    c = captured[0]
    assert c["policy_hotword"] is False, f"captured={c}"
    assert c["config_hotword"] is False, f"captured={c}"
    assert c["pipeline_policy"] is c["policy_object"]
    assert c["config_hotword"] == c["policy_hotword"]


# ── Test 7: config.mode=offline → local_only=True ────────────


def test_config_mode_offline_forces_local_only(tmp_path, monkeypatch):
    """config.mode=offline forces local_only=True, disabling all remote features."""
    config = _make_config(tmp_path, mode="offline")
    captured = []
    _setup_cli_patches(monkeypatch, config, captured)

    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake-wav")

    result = runner.invoke(
        app,
        [
            "run",
            str(audio),
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
            "--no-cleanroom",
            "--no-git-check",
            "--no-tui",
        ],
    )

    assert result.exit_code == 0, result.output
    c = captured[0]
    assert c["policy_local_only"] is True, f"captured={c}"
    assert c["policy_proofread"] is False, f"captured={c}"
    assert c["policy_hotword"] is False, f"captured={c}"
    assert c["config_proofread"] is False, f"captured={c}"
    assert c["config_hotword"] is False, f"captured={c}"
    assert c["pipeline_policy"] is c["policy_object"]
    assert c["config_proofread"] == c["policy_proofread"]
    assert c["config_hotword"] == c["policy_hotword"]
