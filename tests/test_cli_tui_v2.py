"""CLI contract for previewing the independent Textual TUI v2."""

import subprocess
import sys
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from subtap.cli import _build_observer_child_command, app
from subtap.core.state_store import StateStore


@pytest.fixture(autouse=True)
def _isolate_user_state(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


def test_tui_v2_flag_launches_preview_app(monkeypatch):
    launched: list[bool] = []

    class FakeV2App:
        def run(self):
            launched.append(True)
            return None

    fake_module = ModuleType("subtap.ui.v2")
    fake_module.SubtapV2App = FakeV2App
    monkeypatch.setitem(sys.modules, "subtap.ui.v2", fake_module)

    result = CliRunner().invoke(app, ["tui", "--v2"])

    assert result.exit_code == 0
    assert launched == [True]


def test_observer_child_command_removes_every_parent_ui_flag():
    command = _build_observer_child_command(
        [
            "subtap",
            "run",
            "voice.wav",
            "--tui",
            "--tui-v2",
            "--observer-child",
            "--no-tui",
        ]
    )

    assert command == [
        sys.executable,
        "-m",
        "subtap.cli",
        "run",
        "voice.wav",
        "--observer-child",
        "--no-tui",
    ]


def test_tui_v2_does_not_launch_a_second_cli_after_the_app_closes(monkeypatch):
    class FakeV2App:
        def run(self):
            return None

    fake_module = ModuleType("subtap.ui.v2")
    fake_module.SubtapV2App = FakeV2App
    monkeypatch.setitem(sys.modules, "subtap.ui.v2", fake_module)
    launched = []
    monkeypatch.setattr(
        "subtap.cli.subprocess.run",
        lambda selected, **_kwargs: launched.append(selected)
        or subprocess.CompletedProcess(selected, 0),
    )

    result = CliRunner().invoke(app, ["tui", "--v2"])

    assert result.exit_code == 0
    assert launched == []


def test_run_tui_v2_uses_signal_desk_observer(
    tmp_path, monkeypatch, skip_runtime_model_validation
):
    config = SimpleNamespace(
        mode="online",
        translate_to="",
        asr=SimpleNamespace(backend="mlx-qwen-asr", model="asr_0.6b"),
        clean=SimpleNamespace(glossary_path=None),
        output=SimpleNamespace(
            timestamp=True,
            subtitle_punctuation=False,
            subtitle_language="zh",
            subtitle_stem="output",
        ),
        workspace=SimpleNamespace(root=str(tmp_path / "work")),
    )
    process = SimpleNamespace(poll=lambda: None, pid=4321)
    dashboard = SimpleNamespace(run=lambda: "quit")
    selected: list[Path] = []

    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda _path, **_kwargs: config,
    )
    registration_statuses: list[str] = []

    def fake_popen(*_args, **_kwargs):
        store = StateStore(tmp_path / ".subtap" / "state.json")
        task = store.load().recent_tasks[0]
        registration_statuses.append(str(task["status"]))
        store.update_recent_task_status(str(task["task_id"]), "success")
        return process

    monkeypatch.setattr("subtap.cli.pipeline_cli.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "subtap.ui.v2.observer._make_v2_observer_dashboard",
        lambda log_path, *_args, **_kwargs: selected.append(log_path) or dashboard,
    )
    input_path = tmp_path / "voice.wav"
    input_path.write_bytes(b"audio")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(input_path),
            "--tui-v2",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
        ],
    )

    assert result.exit_code == 0
    assert len(selected) == 1
    assert selected[0].parent.parent == tmp_path / "work" / "jobs"
    assert selected[0].name == "run.log.jsonl"
    task = StateStore(tmp_path / ".subtap" / "state.json").load().recent_tasks[0]
    assert registration_statuses == ["starting"]
    assert task["pid"] == 4321
    assert task["status"] == "success"


def test_tui_parent_start_failure_does_not_register_running_task(
    tmp_path, monkeypatch, skip_runtime_model_validation
):
    config = SimpleNamespace(
        mode="online",
        translate_to="",
        asr=SimpleNamespace(backend="mlx-qwen-asr", model="asr_0.6b"),
        clean=SimpleNamespace(glossary_path=None),
        output=SimpleNamespace(
            timestamp=True,
            subtitle_punctuation=False,
            subtitle_language="zh",
            subtitle_stem="output",
        ),
        workspace=SimpleNamespace(root=str(tmp_path / "work")),
    )
    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda _path, **_kwargs: config,
    )
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli.subprocess.Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("spawn failed")),
    )
    input_path = tmp_path / "voice.wav"
    input_path.write_bytes(b"audio")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(input_path),
            "--tui-v2",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
        ],
    )

    assert result.exit_code != 0
    state_path = tmp_path / ".subtap" / "state.json"
    assert StateStore(state_path).load().recent_tasks == []


def test_observer_child_does_not_register_the_task_again(
    tmp_path, monkeypatch, skip_runtime_model_validation
):
    registrations: list[str] = []

    class Workspace:
        root = tmp_path / "work"

        def ensure_dirs(self):
            self.root.mkdir(parents=True, exist_ok=True)

    class FakePipeline:
        def __init__(self, config, work_dir, **kwargs):
            self.config = config
            self.workspace = Workspace()
            self.event_bus = None

        def cleanup(self):
            return {"cleaned_count": 0, "cleaned_files": []}

    config = SimpleNamespace(
        mode="online",
        translate_to="",
        asr=SimpleNamespace(backend="mlx-qwen-asr", model="asr_0.6b"),
        align=SimpleNamespace(model="aligner"),
        clean=SimpleNamespace(glossary_path=None),
        output=SimpleNamespace(
            timestamp=True,
            generate_metrics=False,
            subtitle_punctuation=False,
            subtitle_language="zh",
            subtitle_stem="output",
        ),
        workspace=SimpleNamespace(root=str(tmp_path / "work")),
    )
    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda _path, **_kwargs: config,
    )
    monkeypatch.setattr("subtap.core.tracked_pipeline.TrackedPipeline", FakePipeline)
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli.PipelineProfiler.wrap_pipeline",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._execute_pipeline",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._safe_add_recent_task",
        lambda task_id, *_args, **_kwargs: registrations.append(task_id),
    )
    input_path = tmp_path / "voice.wav"
    input_path.write_bytes(b"audio")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(input_path),
            "--observer-child",
            "--no-tui",
            "--no-cleanroom",
            "--no-git-check",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
        ],
        env={
            "SUBTAP_RUN_ID": "run-001",
            "SUBTAP_EVENT_LOG": str(tmp_path / "work" / "jobs" / "run.log.jsonl"),
        },
    )

    assert result.exit_code == 0, result.output
    assert registrations == []


# ── R0 regression: TUI v2 local-only path ──


def test_task_request_local_only_command_has_tui(tmp_path):
    """SubtitleTaskRequest(local_only=True) produces --local-only and --tui flags.

    Note: This tests SubtitleTaskRequest directly, NOT the real WizardView.
    For real WizardView tests, see test_tui_v2_real_path.py.
    """
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


def test_local_only_clean_stage_completes(tmp_path):
    """local_only=True policy allows clean stage to complete without ExternalProcessingError.

    Verifies the core regression: with local_only=True and both LLM features
    disabled, run_clean() completes successfully without calling
    assert_clean_llm_allowed().

    Note: This tests run_clean() directly, NOT the full pipeline or CLI path.
    """
    from unittest.mock import patch

    from subtap.core.clean import run_clean
    from subtap.core.workspace import Workspace
    from subtap.runtime.external_policy import build_policy
    from subtap.schemas.config import SubtapConfig
    from subtap.schemas.models import ASRSegment

    config = SubtapConfig()
    config.llm_proofread = False
    config.llm_hotword = False

    # Build a local_only policy (as TUI v2 wizard does)
    policy = build_policy(local_only=True, enhance_mode="api")
    assert policy.llm_proofread is False
    assert policy.llm_hotword is False

    # Create workspace with mock ASR data
    ws = Workspace(config, base_dir=tmp_path / "work")
    ws.ensure_dirs()
    ws.asr_dir.mkdir(parents=True, exist_ok=True)
    seg = ASRSegment(
        chunk_id=0, segment_id=0, start_sec=0.0, end_sec=1.0, text="test segment"
    )
    ws.asr_jsonl.write_text(seg.model_dump_json() + "\n")

    def fail_if_called(*_a, **_k):
        raise AssertionError("get_llm_backend must not be called for local_only clean")

    with patch("subtap.core.clean.get_llm_backend", fail_if_called):
        result = run_clean(ws, config, external_policy=policy)

    assert result["segment_count"] == 1
    assert ws.cleaned_jsonl.exists()
