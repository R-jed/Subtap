"""Textual command deck behavior."""

from __future__ import annotations

import pytest

pytest.importorskip("textual")


def test_command_deck_logo_and_title_use_separate_lines():
    from subtap.ui.command_deck import build_root_command_deck_renderable

    rendered = build_root_command_deck_renderable().plain

    assert "|_|\n       Subtap Command Deck" in rendered


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
        await pilot.press("down", "down", "down", "down")
        await pilot.resize_terminal(80, 24)
        await pilot.resize_terminal(30, 10)
        menu = app.query_one("#menu", OptionList)

        assert app.selected_index == 4
        assert menu.highlighted == 4
        assert menu.region.height > 0
        assert app.size == (30, 10)
