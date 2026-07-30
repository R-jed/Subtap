"""CLI disclosure integration tests.

These tests prove the real command prints disclosure from the same policy
passed to the Pipeline. They exercise the actual _warn_external_api_use()
call inside the CLI.

Required cases:
1. enhance=local → no external disclosure
2. enhance=api with --no-llm-proofread --no-llm-hotword → no subtitle-text disclosure
3. enhance=api with proofread enabled → subtitle-text disclosure
4. http-asr with clean LLM disabled → audio disclosure only
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


def _make_config(
    tmp_path: Path, *, asr_backend: str = "mlx-qwen-asr"
) -> SimpleNamespace:
    config = SimpleNamespace(
        mode="online",
        translate_to="",
        asr=SimpleNamespace(backend=asr_backend, model="asr_0.6b", hotwords=[]),
        align=SimpleNamespace(model="aligner", quantization="q8"),
        clean=SimpleNamespace(glossary_path=None, style_rules=None, backend="local"),
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
        llm_proofread=None,
        llm_hotword=None,
    )
    return config


def _run_and_capture(
    monkeypatch, config: SimpleNamespace, args: list[str]
) -> tuple[int, list[str], list]:
    """Run CLI and capture exit code, stderr, and pipeline policy."""
    from subtap.cli import pipeline_cli as pcl_mod
    from subtap.runtime import external_policy as ep_mod

    original_build_policy = ep_mod.build_policy
    captured_policies = []

    def capturing_build_policy(*bp_args, **bp_kwargs):
        policy = original_build_policy(*bp_args, **bp_kwargs)
        captured_policies.append(policy)
        return policy

    monkeypatch.setattr(ep_mod, "build_policy", capturing_build_policy)
    monkeypatch.setattr(pcl_mod, "build_policy", capturing_build_policy)

    def capturing_execute(pipeline, *args, **kwargs):
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

    result = runner.invoke(app, args)
    return result.exit_code, captured_policies, result.output


# ── Test 1: enhance=local → no external disclosure ───────────


def test_enhance_local_no_disclosure(tmp_path, monkeypatch):
    """enhance=local: no external disclosure lines printed."""
    config = _make_config(tmp_path)
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake-wav")

    exit_code, policies, output = _run_and_capture(
        monkeypatch,
        config,
        [
            "run",
            str(audio),
            "--enhance",
            "local",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
            "--no-cleanroom",
            "--no-git-check",
            "--no-tui",
        ],
    )

    assert exit_code == 0, output
    assert len(policies) == 1
    policy = policies[0]

    assert policy.sends_external_data is False
    assert policy.sends_audio is False
    assert policy.sends_text is False

    # No disclosure lines about sending data
    assert "发送" not in output


# ── Test 2: enhance=api, no LLM features → no text disclosure ─


def test_enhance_api_no_llm_no_text_disclosure(tmp_path, monkeypatch):
    """enhance=api + --no-llm-proofread --no-llm-hotword: no subtitle-text disclosure."""
    config = _make_config(tmp_path)
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake-wav")

    exit_code, policies, output = _run_and_capture(
        monkeypatch,
        config,
        [
            "run",
            str(audio),
            "--enhance",
            "api",
            "--no-llm-proofread",
            "--no-llm-hotword",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
            "--no-cleanroom",
            "--no-git-check",
            "--no-tui",
        ],
    )

    assert exit_code == 0, output
    policy = policies[0]
    assert policy.sends_text is False
    assert "字幕文本" not in output


# ── Test 3: enhance=api, proofread enabled → text disclosure ──


def test_enhance_api_proofread_text_disclosure(tmp_path, monkeypatch):
    """enhance=api + proofread: subtitle-text disclosure printed."""
    config = _make_config(tmp_path)
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake-wav")

    exit_code, policies, output = _run_and_capture(
        monkeypatch,
        config,
        [
            "run",
            str(audio),
            "--enhance",
            "api",
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

    assert exit_code == 0, output
    policy = policies[0]
    assert policy.sends_text is True
    assert "字幕文本" in output


# ── Test 4: http-asr, no LLM → audio disclosure only ─────────


def test_http_asr_audio_disclosure_only(tmp_path, monkeypatch):
    """http-asr with clean LLM disabled: audio disclosure only."""
    config = _make_config(tmp_path, asr_backend="http-asr")
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake-wav")

    exit_code, policies, output = _run_and_capture(
        monkeypatch,
        config,
        [
            "run",
            str(audio),
            "--enhance",
            "local",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
            "--no-cleanroom",
            "--no-git-check",
            "--no-tui",
        ],
    )

    assert exit_code == 0, output
    policy = policies[0]
    assert policy.sends_audio is True
    assert policy.sends_text is False

    # Audio disclosure present
    assert "音频" in output
    # Text disclosure absent
    assert "字幕文本" not in output
