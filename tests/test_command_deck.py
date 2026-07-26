"""Textual command deck behavior."""

from __future__ import annotations

import pytest

pytest.importorskip("textual")


def test_command_deck_uses_task_oriented_menu_and_compact_chrome():
    from subtap.ui.command_deck import (
        FOOTER_KEYS,
        OPTIONS,
        build_root_command_deck_renderable,
    )

    rendered = build_root_command_deck_renderable().plain

    assert [option.label for option in OPTIONS] == [
        "Transcribe",
        "Batch",
        "Observe",
        "Models",
        "Glossary",
        "Setup",
        "Doctor",
    ]
    assert [option.action for option in OPTIONS] == [
        "run",
        "batch",
        "observe",
        "models",
        "glossary",
        "setup",
        "doctor",
    ]
    assert "➤ 1. Transcribe" in rendered
    assert "SUBTAP" in rendered
    assert "█" in rendered
    assert "单个音频或视频生成字幕" in rendered
    assert "本地离线字幕生成" in rendered
    assert FOOTER_KEYS == "↑↓  移动   Enter  选择   Q  退出"
    logo_end = rendered.index("SUBTAP")
    description_start = rendered.index("本地离线字幕生成")
    assert description_start > logo_end


@pytest.mark.asyncio
async def test_command_deck_moves_selection_marker_without_full_row_prompt(
    tmp_path, monkeypatch
):
    from textual.widgets import OptionList

    from subtap.ui.command_deck import CommandDeckApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    state = tmp_path / ".subtap" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text("{}", encoding="utf-8")

    app = CommandDeckApp()
    async with app.run_test(size=(80, 24)) as pilot:
        menu = app.query_one("#menu", OptionList)
        assert menu.get_option_at_index(0).prompt.plain.startswith("➤ 1.")
        assert menu.get_option_at_index(1).prompt.plain.startswith("  2.")

        await pilot.press("down")

        assert menu.get_option_at_index(0).prompt.plain.startswith("  1.")
        assert menu.get_option_at_index(1).prompt.plain.startswith("➤ 2.")


@pytest.mark.asyncio
async def test_transcribe_opens_setup_inside_command_deck(tmp_path, monkeypatch):
    from textual.widgets import Button

    from subtap.ui.command_deck import CommandDeckApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    state = tmp_path / ".subtap" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text("{}", encoding="utf-8")

    app = CommandDeckApp()
    async with app.run_test(size=(90, 40)) as pilot:
        await pilot.press("enter")
        await pilot.pause()

        assert app.return_value is None
        assert app.screen.query_one("#choose-input", Button).label == "选择文件…"

        await pilot.press("escape")
        assert app.query_one("#menu").display is True


@pytest.mark.asyncio
async def test_command_deck_q_exits_without_action(tmp_path, monkeypatch):
    from subtap.ui.command_deck import CommandDeckApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    state = tmp_path / ".subtap" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text("{}", encoding="utf-8")

    app = CommandDeckApp()
    async with app.run_test() as pilot:
        await pilot.press("q")

    assert app.return_value is None


@pytest.mark.asyncio
async def test_secondary_pages_return_to_command_deck(tmp_path, monkeypatch):
    from textual.widgets import Static

    from subtap.ui.command_deck import CommandDeckApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    state = tmp_path / ".subtap" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text("{}", encoding="utf-8")

    app = CommandDeckApp()
    async with app.run_test(size=(90, 36)) as pilot:
        await pilot.press("6")
        await pilot.pause()
        assert "设置" in str(app.screen.query_one("#page-title", Static).render())

        await pilot.press("escape")
        assert app.query_one("#menu").display is True


@pytest.mark.asyncio
async def test_batch_and_observe_choose_paths_inside_their_pages(tmp_path, monkeypatch):
    from textual.widgets import Button

    from subtap.ui.command_deck import CommandDeckApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    state = tmp_path / ".subtap" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text("{}", encoding="utf-8")

    app = CommandDeckApp()
    async with app.run_test(size=(90, 36)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        assert app.screen.query_one("#choose-path", Button).label == "选择媒体文件夹…"

        await pilot.press("escape", "3")
        await pilot.pause()
        assert app.screen.query_one("#choose-path", Button).label == (
            "选择 run.log.jsonl…"
        )


@pytest.mark.asyncio
async def test_glossary_page_aligns_its_actions(tmp_path, monkeypatch):
    from textual.widgets import Button

    from subtap.ui.command_deck import CommandDeckApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    state = tmp_path / ".subtap" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text("{}", encoding="utf-8")

    app = CommandDeckApp()
    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.press("5")
        await pilot.pause()
        actions = list(app.screen.query("#glossary-page-actions Button"))

        assert len(actions) == 3
        assert all(isinstance(button, Button) for button in actions)
        widths = [button.region.width for button in actions]
        assert max(widths) - min(widths) <= 1

        await pilot.resize_terminal(60, 36)
        await pilot.pause()
        assert len({button.region.y for button in actions}) == 3


def test_command_deck_uses_lowercase_product_title():
    from subtap.ui.command_deck import CommandDeckApp

    assert CommandDeckApp.TITLE == "subtap"


def test_number_bindings_are_derived_from_menu_options():
    from subtap.ui.command_deck import CommandDeckApp, OPTIONS

    number_bindings = CommandDeckApp.BINDINGS[5 : 5 + len(OPTIONS)]

    assert [binding[0] for binding in number_bindings] == [
        str(index) for index in range(1, len(OPTIONS) + 1)
    ]
    assert [binding[2] for binding in number_bindings] == [
        option.label for option in OPTIONS
    ]


@pytest.mark.asyncio
async def test_command_deck_keeps_selection_visible_in_compact_terminal(
    tmp_path, monkeypatch
):
    from textual.widgets import OptionList

    from subtap.ui.command_deck import CommandDeckApp

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    state = tmp_path / ".subtap" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text("{}", encoding="utf-8")

    app = CommandDeckApp()
    async with app.run_test(size=(30, 10)) as pilot:
        await pilot.press("down", "down", "down", "down", "down")
        await pilot.resize_terminal(80, 24)
        await pilot.resize_terminal(30, 10)
        menu = app.query_one("#menu", OptionList)

        assert app.selected_index == 5
        assert menu.highlighted == 5
        assert menu.region.height > 0
        assert app.size == (30, 10)


def test_command_deck_glossary_action_opens_glossary_library(tmp_path, monkeypatch):
    from subtap.cli import _handle_command_deck_action

    opened = []
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.cli.hotword_cli._open_file_cross_platform",
        lambda path: opened.append(path),
    )

    _handle_command_deck_action("glossary")

    glossary_dir = tmp_path / ".subtap" / "glossaries"
    assert opened == [glossary_dir]
    assert (glossary_dir / "default.txt").is_file()
