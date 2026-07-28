import pytest
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from subtap.ui.v2 import SubtapV2App
from subtap.ui.v2.home import HomeScreen
from subtap.ui.v2.new_transcription import NewTranscriptionScreen


@pytest.mark.asyncio
async def test_v2_starts_on_home_with_signal_desk_chrome():
    app = SubtapV2App()

    async with app.run_test(size=(90, 40)):
        footer = app.screen.query_one(Footer)

        assert isinstance(app.screen, HomeScreen)
        assert app.theme == "signal-desk"
        assert app.ENABLE_COMMAND_PALETTE is False
        assert footer.compact is True
        assert footer.show_command_palette is False


@pytest.mark.asyncio
async def test_home_navigation_returns_stable_selected_action():
    app = SubtapV2App()

    async with app.run_test(size=(90, 40)) as pilot:
        menu = app.screen.query_one(OptionList)

        assert menu.highlighted == 0
        assert menu.get_option_at_index(0).id == "run"
        assert "新建字幕" in str(menu.get_option_at_index(0).prompt)

        await pilot.press("down")
        assert menu.highlighted == 1

        await pilot.press("up")
        assert menu.highlighted == 0

        await pilot.press("down", "enter")

    assert app.return_value == "batch"


@pytest.mark.asyncio
async def test_v2_home_uses_simplified_chinese_product_copy():
    app = SubtapV2App()

    async with app.run_test(size=(90, 40)):
        visible = "\n".join(str(widget.render()) for widget in app.screen.query(Static))
        menu = app.screen.query_one(OptionList)
        prompts = "\n".join(
            str(menu.get_option_at_index(index).prompt)
            for index in range(menu.option_count)
        )

        assert "本地优先的字幕工作台" in visible
        assert "音视频与模型推理均留在本机" in visible
        assert "工作台" in visible
        for label in (
            "新建字幕",
            "批量转录",
            "任务记录",
            "模型管理",
            "热词管理",
            "偏好设置",
            "环境检查",
        ):
            assert label in prompts


@pytest.mark.asyncio
async def test_new_transcription_opens_inside_v2_and_returns_home_on_escape():
    app = SubtapV2App()

    async with app.run_test(size=(90, 56)) as pilot:
        await pilot.press("enter")

        assert isinstance(app.screen, NewTranscriptionScreen)
        assert len(app.screen_stack) == 2

        await pilot.press("escape")

        assert isinstance(app.screen, HomeScreen)
        assert len(app.screen_stack) == 1
        assert app.is_running is True


@pytest.mark.asyncio
async def test_new_transcription_command_exits_v2_for_cli_execution():
    app = SubtapV2App()
    command = ["python", "-m", "subtap.cli", "run", "media.wav"]

    async with app.run_test() as pilot:
        await pilot.press("enter")
        app.screen.dismiss(command)
        await pilot.pause()

    assert app.return_value == command


@pytest.mark.asyncio
async def test_home_rejects_unknown_action():
    app = SubtapV2App()

    with pytest.raises(ValueError, match="Unknown Home action"):
        async with app.run_test() as pilot:
            menu = app.screen.query_one(OptionList)
            menu.add_option(Option("Unknown", id="unknown"))
            menu.highlighted = menu.option_count - 1
            await pilot.press("enter")


@pytest.mark.asyncio
async def test_q_exits_v2():
    app = SubtapV2App()

    async with app.run_test() as pilot:
        assert app.is_running is True
        await pilot.press("q")
        await pilot.pause()
        assert app.is_running is False

    assert app.return_value is None


@pytest.mark.asyncio
async def test_escape_returns_exactly_one_screen():
    app = SubtapV2App()

    async with app.run_test() as pilot:
        await app.push_screen(Screen())
        assert len(app.screen_stack) == 2

        await pilot.press("escape")

        assert len(app.screen_stack) == 1
        assert isinstance(app.screen, HomeScreen)


@pytest.mark.asyncio
async def test_v2_shell_tracks_responsive_classes_and_brand():
    app = SubtapV2App()

    async with app.run_test(size=(60, 40)) as pilot:
        compact_brand = app.screen.query_one("#brand-compact", Static)
        wide_brand = app.screen.query_one("#brand-wide", Static)

        assert "-compact" in app.screen.classes
        assert str(compact_brand.render()) == "SUBTAP"
        assert compact_brand.display is True
        assert wide_brand.display is False

        await pilot.resize_terminal(80, 40)
        await pilot.pause()
        assert "-regular" in app.screen.classes
        assert compact_brand.display is True
        assert wide_brand.display is False

        await pilot.resize_terminal(103, 40)
        await pilot.pause()
        assert "-regular" in app.screen.classes

        await pilot.resize_terminal(104, 40)
        await pilot.pause()
        assert "-wide" in app.screen.classes
        assert compact_brand.display is False
        assert wide_brand.display is True
        assert len(str(wide_brand.render()).splitlines()) == 3

        await pilot.resize_terminal(120, 40)
        await pilot.pause()
        assert app.screen.query_one("#home-shell", Vertical).region.width == 104
