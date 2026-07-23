"""Public CLI help stays focused on complete user workflows."""

import sys

from typer.testing import CliRunner

from subtap.cli import app


def test_root_help_prioritizes_user_tasks_and_hides_pipeline_internals():
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "字幕工作流" in result.stdout
    assert "本地资源" in result.stdout
    for command in (
        "run",
        "batch-transcribe",
        "script",
        "glossary",
        "models",
    ):
        assert command in result.stdout
    for internal_command in ("prepare", "transcribe", "clean", "segment", "align"):
        assert f"│ {internal_command} " not in result.stdout


def test_hidden_pipeline_commands_remain_available_for_advanced_use():
    align_result = CliRunner().invoke(app, ["align", "--help"])
    asr_result = CliRunner().invoke(app, ["transcribe", "--help"])

    assert align_result.exit_code == 0
    assert asr_result.exit_code == 0


def test_tui_models_action_reports_installed_model_status(monkeypatch):
    commands: list[list[str]] = []
    monkeypatch.setattr(
        "subtap.ui.command_deck.CommandDeckApp.run", lambda self: "models"
    )
    monkeypatch.setattr(
        "subtap.cli.subprocess.run",
        lambda command, **kwargs: commands.append(command)
        or type("Result", (), {"returncode": 0})(),
    )

    result = CliRunner().invoke(app, ["tui"])

    assert result.exit_code == 0
    assert commands == [[sys.executable, "-m", "subtap.cli", "models", "status"]]
