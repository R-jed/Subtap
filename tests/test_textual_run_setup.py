"""Textual new-subtitle setup flow tests."""

from __future__ import annotations

import sys

import pytest
from typer.main import get_command

pytest.importorskip("textual")


def _create_default_glossary(home):
    default = home / ".subtap" / "glossaries" / "default.txt"
    default.parent.mkdir(parents=True, exist_ok=True)
    default.write_text("", encoding="utf-8")
    return default


@pytest.mark.asyncio
async def test_run_setup_returns_selected_pipeline_command(tmp_path, monkeypatch):
    from textual.widgets import Button, Input, Select, Static

    from subtap.ui.textual_run_setup import ReviewTaskScreen, RunSetupApp

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
        app.query_one("#max-chars", Input).value = "32"
        app.query_one("#output", Input).value = str(output)
        app.query_one("#start", Button).press()
        await pilot.pause()
        assert app.return_value is None
        assert isinstance(app.screen, ReviewTaskScreen)
        confirmation = str(app.screen.query_one("#review-summary", Static).render())
        assert "高质量" in confirmation
        assert "camera.yaml" in confirmation
        assert app.screen.query_one("#confirm-start", Button).label == "开始转录"
        await pilot.press("y")
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
        "--max-chars",
        "32",
        "--local-only",
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
async def test_run_setup_selects_and_reselects_input_inside_form(tmp_path, monkeypatch):
    from textual.widgets import Button, Static

    from subtap.ui.textual_run_setup import RunSetupApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    first = tmp_path / "first.wav"
    second = tmp_path / "second.mov"
    first.write_bytes(b"audio")
    second.write_bytes(b"video")
    selected = iter([first, second])
    monkeypatch.setattr(
        "subtap.ui.textual_run_setup._choose_native_file",
        lambda _prompt: next(selected),
    )

    app = RunSetupApp()
    async with app.run_test() as pilot:
        assert "尚未选择" in str(app.query_one("#input-path", Static).render())

        app.query_one("#choose-input", Button).press()
        await pilot.pause()
        assert str(first) in str(app.query_one("#input-path", Static).render())

        app.query_one("#choose-input", Button).press()
        await pilot.pause()
        assert str(second) in str(app.query_one("#input-path", Static).render())


@pytest.mark.asyncio
async def test_run_setup_picker_cancel_preserves_current_selection(
    tmp_path, monkeypatch
):
    from textual.widgets import Button, Static

    from subtap.ui.textual_run_setup import RunSetupApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")
    selected = iter([audio, None])
    monkeypatch.setattr(
        "subtap.ui.textual_run_setup._choose_native_file",
        lambda _prompt: next(selected),
    )

    app = RunSetupApp()
    async with app.run_test() as pilot:
        app.query_one("#choose-input", Button).press()
        await pilot.pause()
        app.query_one("#choose-input", Button).press()
        await pilot.pause()

        assert str(audio) in str(app.query_one("#input-path", Static).render())


@pytest.mark.asyncio
async def test_glossary_actions_share_one_aligned_row(tmp_path, monkeypatch):
    from textual.widgets import Button

    from subtap.ui.textual_run_setup import RunSetupApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    app = RunSetupApp()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        actions = [
            app.query_one("#edit-default-glossary", Button),
            app.query_one("#view-learned-glossary", Button),
            app.query_one("#choose-glossary", Button),
        ]

        assert {button.parent.id for button in actions} == {"glossary-actions"}
        assert len({button.region.width for button in actions}) == 1
        assert len({button.region.height for button in actions}) == 1


@pytest.mark.asyncio
async def test_resource_pickers_share_rows_with_their_fields(tmp_path, monkeypatch):
    from textual.widgets import Button, Input, Select

    from subtap.ui.textual_run_setup import RunSetupApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    app = RunSetupApp()
    async with app.run_test(size=(100, 40)):
        manuscript = app.query_one("#manuscript", Select)
        manuscript_button = app.query_one("#choose-manuscript", Button)
        output = app.query_one("#output", Input)
        output_button = app.query_one("#choose-output", Button)

        assert manuscript.parent is manuscript_button.parent
        assert manuscript.parent.id == "manuscript-row"
        assert output.parent is output_button.parent
        assert output.parent.id == "output-row"


@pytest.mark.asyncio
async def test_run_setup_defaults_to_configured_asr_model(tmp_path, monkeypatch):
    from textual.widgets import Select

    from subtap.ui.textual_run_setup import RunSetupApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config_path = tmp_path / ".subtap" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("asr:\n  model: asr_1.7b\n", encoding="utf-8")
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")

    app = RunSetupApp(audio)
    async with app.run_test():
        assert app.query_one("#quality", Select).value == "quality"


@pytest.mark.asyncio
async def test_run_setup_explains_and_selects_local_resources(tmp_path, monkeypatch):
    from textual.widgets import Button, Input, Select, Static

    from subtap.ui.textual_run_setup import RunSetupApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    glossary_dir = tmp_path / ".subtap" / "glossaries"
    glossary_dir.mkdir(parents=True)
    (glossary_dir / "default.txt").write_text("", encoding="utf-8")
    (glossary_dir / "learned.txt").write_text("", encoding="utf-8")
    external_glossary = tmp_path / "camera.yaml"
    external_glossary.write_text("", encoding="utf-8")
    external_manuscript = tmp_path / "draft.txt"
    external_manuscript.write_text("参考文稿", encoding="utf-8")
    output_dir = tmp_path / "exports"
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")

    monkeypatch.setattr(
        "subtap.ui.textual_run_setup._choose_native_file",
        lambda prompt: external_glossary if "热词" in prompt else external_manuscript,
    )
    monkeypatch.setattr(
        "subtap.ui.textual_run_setup._choose_native_folder",
        lambda _prompt: output_dir,
    )

    app = RunSetupApp(audio)
    async with app.run_test() as pilot:
        help_text = str(app.query_one("#glossary-help", Static).render())
        assert str(glossary_dir) in help_text
        assert "default.txt" in help_text
        assert "learned.txt" in help_text
        assert "手动修改可能被覆盖" in help_text

        app.query_one("#choose-glossary", Button).press()
        app.query_one("#choose-manuscript", Button).press()
        app.query_one("#choose-output", Button).press()
        await pilot.pause()

        assert app.query_one("#glossary", Select).value == str(external_glossary)
        assert app.query_one("#manuscript", Select).value == str(external_manuscript)
        assert app.query_one("#output", Input).value == str(output_dir)


@pytest.mark.asyncio
async def test_run_setup_can_open_owned_and_learned_glossaries(tmp_path, monkeypatch):
    from textual.widgets import Button, Static

    from subtap.ui.textual_run_setup import RunSetupApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    glossary_dir = tmp_path / ".subtap" / "glossaries"
    glossary_dir.mkdir(parents=True)
    default = glossary_dir / "default.txt"
    learned = glossary_dir / "learned.txt"
    default.write_text("", encoding="utf-8")
    learned.write_text("", encoding="utf-8")
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")
    opened = []
    monkeypatch.setattr(
        "subtap.cli.hotword_cli._open_file_cross_platform",
        lambda path: opened.append(path),
    )

    app = RunSetupApp(audio)
    async with app.run_test() as pilot:
        assert str(app.query_one("#choose-glossary", Button).label) == (
            "选择其他热词表…"
        )
        assert "建议 25" in str(app.query_one("#max-chars-help", Static).render())

        app.query_one("#edit-default-glossary", Button).press()
        app.query_one("#view-learned-glossary", Button).press()
        await pilot.pause()

    assert opened == [default, learned]


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
async def test_run_setup_rejects_invalid_maximum_characters(tmp_path, monkeypatch):
    from textual.widgets import Button, Input, Static

    from subtap.ui.textual_run_setup import RunSetupApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")
    app = RunSetupApp(audio)

    async with app.run_test() as pilot:
        app.query_one("#max-chars", Input).value = "9"
        app.query_one("#start", Button).press()
        await pilot.pause()

        assert "10 到 60" in str(app.query_one("#status", Static).render())


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
        await pilot.press("y")
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


@pytest.mark.asyncio
async def test_run_setup_uses_native_footer_and_responsive_glossary_actions(
    tmp_path, monkeypatch
):
    from textual.widgets import Footer

    from subtap.ui.textual_run_setup import RunSetupApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    app = RunSetupApp()

    async with app.run_test(size=(60, 40)) as pilot:
        assert len(list(app.query(Footer))) == 1
        assert "-compact" in app.screen.classes
        assert len(list(app.query("#hint"))) == 0
        assert len(list(app.query("#confirmation"))) == 0

        await pilot.resize_terminal(90, 40)
        assert "-regular" in app.screen.classes
