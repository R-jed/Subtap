"""Textual new-subtitle setup flow tests."""

from __future__ import annotations

import sys

import pytest
from typer.main import get_command

pytest.importorskip("textual")


def _create_default_glossary(home):
    default = home / ".subtap" / "glossaries" / "default.yaml"
    default.parent.mkdir(parents=True, exist_ok=True)
    default.write_text("", encoding="utf-8")
    return default


@pytest.mark.asyncio
async def test_run_setup_returns_selected_pipeline_command(tmp_path, monkeypatch):
    from textual.widgets import Button, Input, Select, Static

    from subtap.ui.textual_run_setup import RunSetupApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")
    glossary = tmp_path / ".subtap" / "glossaries" / "camera.yaml"
    glossary.parent.mkdir(parents=True)
    glossary.write_text("理光GR4=李光机亚四\n", encoding="utf-8")
    manuscript = tmp_path / ".subtap" / "manuscripts" / "draft.txt"
    manuscript.parent.mkdir(parents=True)
    manuscript.write_text("参考文稿", encoding="utf-8")
    output = tmp_path / "subtitles"

    app = RunSetupApp(audio)
    async with app.run_test() as pilot:
        app.query_one("#quality", Select).value = "quality"
        app.query_one("#glossary", Select).value = str(glossary)
        app.query_one("#manuscript", Select).value = str(manuscript)
        app.query_one("#output", Input).value = str(output)
        app.query_one("#start", Button).press()
        await pilot.pause()
        assert app.return_value is None
        confirmation = str(app.query_one("#confirmation", Static).render())
        assert "高质量" in confirmation
        assert "camera.yaml" in confirmation
        app.query_one("#start", Button).press()
        await pilot.pause()

    assert app.return_value == [
        sys.executable,
        "-m",
        "subtap.cli",
        "run",
        str(audio),
        "--mode",
        "quality",
        "--format",
        "srt",
        "--subtitle-language",
        "zh",
        "--glossary",
        str(glossary),
        "--reset-hotwords",
        "--script",
        str(manuscript),
        "--output-dir",
        str(output),
        "--tui",
    ]


@pytest.mark.asyncio
async def test_run_setup_rejects_blank_output(tmp_path, monkeypatch):
    from textual.widgets import Button, Input, Static

    from subtap.ui.textual_run_setup import RunSetupApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")
    app = RunSetupApp(audio)

    async with app.run_test() as pilot:
        app.query_one("#output", Input).value = ""
        app.query_one("#start", Button).press()
        await pilot.pause()
        assert "请选择输出目录" in str(app.query_one("#status", Static).render())
        app.query_one("#cancel", Button).press()
        await pilot.pause()

    assert app.return_value is None


@pytest.mark.asyncio
async def test_run_setup_explicitly_resets_optional_resources(tmp_path, monkeypatch):
    from textual.widgets import Button

    from subtap.ui.textual_run_setup import RunSetupApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    _create_default_glossary(tmp_path)
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")

    app = RunSetupApp(audio)
    async with app.run_test() as pilot:
        app.query_one("#start", Button).press()
        await pilot.pause()
        assert app.return_value is None
        app.query_one("#start", Button).press()
        await pilot.pause()

    assert "--default-glossary" in app.return_value
    assert "--no-script" in app.return_value


def test_run_setup_command_is_accepted_by_real_cli_parser(tmp_path, monkeypatch):
    from subtap.cli import app
    from subtap.schemas.task_request import SubtitleTaskRequest

    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")
    _create_default_glossary(tmp_path)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    request = SubtitleTaskRequest(
        input_path=audio,
        output_dir=tmp_path / "output",
        mode="quality",
        use_default_glossary=True,
        disable_script=True,
        reset_hotwords=True,
    )

    command = request.to_cli_command()
    root = get_command(app)
    root_context = root.make_context("subtap", [])
    run_command = root.get_command(root_context, "run")
    run_context = run_command.make_context("run", command[4:])

    assert run_context.params["mode"] == "quality"
    assert run_context.params["default_glossary"] is True
    assert run_context.params["no_script"] is True
    assert run_context.params["reset_hotwords"] is True


def test_default_glossary_selection_fails_when_default_file_is_missing(
    tmp_path, monkeypatch
):
    from subtap.schemas.task_request import SubtitleTaskRequest

    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    request = SubtitleTaskRequest(
        input_path=audio,
        output_dir=tmp_path / "output",
        mode="fast",
        use_default_glossary=True,
    )

    with pytest.raises(ValueError, match="默认热词表不存在"):
        request.validate()
