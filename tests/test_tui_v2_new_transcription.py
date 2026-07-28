"""Signal Desk New Transcription screen tests."""

from __future__ import annotations

import sys
import logging

import pytest
from typer.main import get_command

pytest.importorskip("textual")

from textual.app import App
from textual.widgets import Button, Static

from subtap.ui.v2.new_transcription import NewTranscriptionScreen


class _ScreenApp(App[list[str] | None]):
    def __init__(self, screen: NewTranscriptionScreen) -> None:
        super().__init__()
        self.target_screen = screen


@pytest.mark.asyncio
async def test_new_transcription_and_review_use_simplified_chinese(
    tmp_path, monkeypatch
):
    from textual.widgets import Input

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")
    default_glossary = tmp_path / ".subtap" / "glossaries" / "default.txt"
    default_glossary.parent.mkdir(parents=True)
    default_glossary.write_text("Subtap\n", encoding="utf-8")
    screen = NewTranscriptionScreen(audio)
    app = _ScreenApp(screen)

    async with app.run_test(size=(90, 56)) as pilot:
        await app.push_screen(screen, app.exit)
        await pilot.pause()
        visible = "\n".join(str(widget.render()) for widget in screen.query(Static))

        assert "新建字幕" in visible
        assert "媒体文件" in visible
        assert "任务设置" in visible
        assert "设置摘要" in visible
        assert screen.query_one("#choose-media", Button).label.plain == "选择…"
        assert screen.query_one("#start", Button).label.plain == "开始转录"

        screen.query_one("#output", Input).value = str(tmp_path / "exports")
        screen.query_one("#start", Button).press()
        await pilot.pause()

        review = "\n".join(str(widget.render()) for widget in app.screen.query(Static))
        assert "复核转录设置" in review
        assert "媒体文件" in review
        assert "输出目录" in review
        assert "转录质量" in review
        assert "字幕目标" in review
        assert app.screen.query_one("#review-cancel", Button).label.plain == "返回修改"
        assert app.screen.query_one("#review-confirm", Button).label.plain == "开始转录"


@pytest.mark.asyncio
async def test_new_transcription_returns_complete_pipeline_command(
    tmp_path, monkeypatch
):
    from textual.widgets import Button, Input, Select

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    audio = tmp_path / "interview.mov"
    audio.write_bytes(b"video")
    glossary = tmp_path / ".subtap" / "glossaries" / "camera.yaml"
    glossary.parent.mkdir(parents=True)
    glossary.write_text("Subtap\n", encoding="utf-8")
    manuscript = tmp_path / ".subtap" / "manuscripts" / "draft.txt"
    manuscript.parent.mkdir(parents=True)
    manuscript.write_text("reference", encoding="utf-8")
    output = tmp_path / "exports"

    app = _ScreenApp(NewTranscriptionScreen(audio))
    async with app.run_test(size=(90, 40)) as pilot:
        await app.push_screen(app.target_screen, app.exit)
        await pilot.pause()
        screen = app.target_screen
        screen.query_one("#quality", Select).value = "quality"
        screen.query_one("#glossary", Select).value = str(glossary)
        screen.query_one("#manuscript", Select).value = str(manuscript)
        screen.query_one("#max-chars", Input).value = "32"
        screen.query_one("#output", Input).value = str(output)
        screen.query_one("#start", Button).press()
        await pilot.pause()
        app.screen.query_one("#review-confirm", Button).press()
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
        "--tui-v2",
    ]
    from subtap.cli import app as cli_app

    root = get_command(cli_app)
    root_context = root.make_context("subtap", [])
    run_command = root.get_command(root_context, "run")
    run_context = run_command.make_context("run", app.return_value[4:])
    assert run_context.params["mode"] == "quality"
    assert run_context.params["output_dir"] == str(output)
    assert run_context.params["tui_v2"] is True


@pytest.mark.asyncio
async def test_review_back_preserves_configured_form(tmp_path, monkeypatch):
    from textual.widgets import Button, Input

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    audio = tmp_path / "interview.mov"
    audio.write_bytes(b"video")
    default_glossary = tmp_path / ".subtap" / "glossaries" / "default.txt"
    default_glossary.parent.mkdir(parents=True)
    default_glossary.write_text("Subtap\n", encoding="utf-8")
    app = _ScreenApp(NewTranscriptionScreen(audio))

    async with app.run_test(size=(90, 40)) as pilot:
        await app.push_screen(app.target_screen, app.exit)
        output = app.target_screen.query_one("#output", Input)
        output.value = str(tmp_path / "exports")
        app.target_screen.query_one("#start", Button).press()
        await pilot.pause()

        app.screen.query_one("#review-cancel", Button).focus()
        await pilot.press("enter")
        await pilot.pause()

        assert app.screen is app.target_screen
        assert output.value == str(tmp_path / "exports")
        assert app.return_value is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "value", "message"),
    [
        ("media", "", "请选择音频或视频文件"),
        ("output", "", "请选择输出目录"),
        ("max-chars", "not-a-number", "必须是 10 到 60 的整数"),
        ("max-chars", "9", "必须在 10 到 60 之间"),
        ("max-chars", "61", "必须在 10 到 60 之间"),
    ],
)
async def test_new_transcription_shows_field_errors(
    tmp_path, monkeypatch, case, value, message
):
    from textual.widgets import Button, Input, Static

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")
    screen = NewTranscriptionScreen(None if case == "media" else audio)
    app = _ScreenApp(screen)

    async with app.run_test() as pilot:
        await app.push_screen(screen, app.exit)
        await pilot.pause()
        if case == "output":
            screen.query_one("#output", Input).value = value
        elif case == "max-chars":
            screen.query_one("#max-chars", Input).value = value
        screen.query_one("#start", Button).press()
        await pilot.pause()

        assert message in str(screen.query_one("#status", Static).render())
        assert app.screen is screen


@pytest.mark.asyncio
async def test_media_picker_cancel_preserves_current_selection(tmp_path, monkeypatch):
    from textual.widgets import Button, Static

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    media = tmp_path / "voice.wav"
    media.write_bytes(b"audio")
    selections = iter([media, None])
    monkeypatch.setattr(
        "subtap.ui.v2.new_transcription.choose_file",
        lambda _prompt: next(selections),
    )
    screen = NewTranscriptionScreen()
    app = _ScreenApp(screen)

    async with app.run_test() as pilot:
        await app.push_screen(screen, app.exit)
        await pilot.pause()
        screen.query_one("#choose-media", Button).press()
        await pilot.pause()
        screen.query_one("#choose-media", Button).press()
        await pilot.pause()

        assert screen.input_path == media
        assert str(media) in str(screen.query_one("#media-path", Static).render())


@pytest.mark.asyncio
async def test_picker_failure_is_logged_and_visible(tmp_path, monkeypatch, caplog):
    from textual.widgets import Button, Static

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    def fail_picker(_prompt):
        raise RuntimeError("picker unavailable")

    monkeypatch.setattr(
        "subtap.ui.v2.new_transcription.choose_file",
        fail_picker,
    )
    screen = NewTranscriptionScreen()
    app = _ScreenApp(screen)

    with caplog.at_level(logging.ERROR):
        async with app.run_test() as pilot:
            await app.push_screen(screen, app.exit)
            await pilot.pause()
            screen.query_one("#choose-media", Button).press()
            await pilot.pause()

            assert "picker unavailable" in str(
                screen.query_one("#status", Static).render()
            )
            assert screen.input_path is None

    assert "无法打开系统选择器" in caplog.text


@pytest.mark.asyncio
async def test_new_transcription_uses_config_defaults_and_responsive_layout(
    tmp_path, monkeypatch
):
    from textual.widgets import Button, Input, Select

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config = tmp_path / ".subtap" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "asr:\n  model: asr_1.7b\noutput:\n  max_chars: 44\n",
        encoding="utf-8",
    )
    screen = NewTranscriptionScreen()
    app = _ScreenApp(screen)

    async with app.run_test(size=(60, 56)) as pilot:
        await app.push_screen(screen, app.exit)
        await pilot.pause()
        assert screen.query_one("#quality", Select).value == "quality"
        assert screen.query_one("#max-chars", Input).value == "44"
        assert "-compact" in screen.classes
        assert screen.query_one("#new-shell").max_scroll_x == 0

        await pilot.resize_terminal(90, 56)
        await pilot.pause()
        assert "-regular" in screen.classes
        picker_buttons = [
            screen.query_one(f"#{button_id}", Button)
            for button_id in (
                "choose-glossary",
                "choose-manuscript",
                "choose-output",
            )
        ]
        assert (
            len(
                {
                    (button.region.x, button.region.width, button.region.height)
                    for button in picker_buttons
                }
            )
            == 1
        )
        assert [
            button.id for button in screen.query(Button) if button.variant == "primary"
        ] == ["start"]

        await pilot.resize_terminal(104, 56)
        assert "-wide" in screen.classes
        assert screen.query_one("#new-shell").region.width == 104


@pytest.mark.asyncio
async def test_back_dismisses_without_command(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    screen = NewTranscriptionScreen()
    app = _ScreenApp(screen)

    async with app.run_test() as pilot:
        await app.push_screen(screen, app.exit)
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert app.return_value is None
