"""CLI contract for previewing the independent Textual TUI v2."""

import subprocess
import sys
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

from typer.testing import CliRunner

from subtap.cli import _build_observer_child_command, app


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


def test_tui_v2_runs_the_command_returned_by_the_preview(monkeypatch):
    command = [
        sys.executable,
        "-m",
        "subtap.cli",
        "run",
        "voice.wav",
        "--tui-v2",
    ]

    class FakeV2App:
        def run(self):
            return command

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
    assert launched == [
        [
            sys.executable,
            "-m",
            "subtap.cli",
            "run",
            "voice.wav",
            "--tui-v2",
        ]
    ]


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
    process = SimpleNamespace(poll=lambda: None)
    dashboard = SimpleNamespace(run=lambda: "quit")
    selected: list[Path] = []

    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _path: config)
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli.subprocess.Popen", lambda *_args, **_kwargs: process
    )
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
    assert selected == [tmp_path / "work" / "run.log.jsonl"]
