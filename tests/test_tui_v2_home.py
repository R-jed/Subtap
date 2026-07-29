from types import SimpleNamespace
import os
from pathlib import Path

import pytest
from textual.app import App
from textual.screen import Screen
from textual.widgets import Button, OptionList, Static

from subtap.core.state_store import StateStore
from subtap.ui.v2.home import HOME_CSS, HOME_LOGO, HomeScreen


class HomeApp(App[None]):
    CSS = HOME_CSS

    def get_default_screen(self):
        return HomeScreen()


@pytest.mark.asyncio
async def test_home_has_one_brand_and_one_navigation_menu(monkeypatch):
    monkeypatch.setattr(
        "subtap.ui.v2.home.StateStore",
        lambda _path: SimpleNamespace(load=lambda: SimpleNamespace(recent_tasks=[])),
    )

    async with HomeApp().run_test(size=(104, 30)) as pilot:
        screen = pilot.app.screen
        assert str(screen.query_one("#home-logo", Static).render()) == HOME_LOGO
        visible = "\n".join(str(widget.render()) for widget in screen.query(Static))
        menus = list(screen.query(OptionList))

        assert "本地优先的字幕生成与转录" in visible
        assert "音视频转录 · 批量处理 · 热词增强 · 时间轴生成" in visible
        assert "https://github.com/R-jed/Subtap" in visible
        assert len(menus) == 1
        assert menus[0].id == "home-menu"
        assert menus[0].option_count == 7
        assert not list(screen.query("#workspace-label"))
        assert not list(screen.query("#resources-label"))


@pytest.mark.asyncio
async def test_home_privacy_copy_discloses_online_asr_upload(monkeypatch):
    monkeypatch.setattr(
        "subtap.ui.v2.home.StateStore",
        lambda _path: SimpleNamespace(load=lambda: SimpleNamespace(recent_tasks=[])),
    )

    app = HomeApp()
    async with app.run_test():
        visible = "\n".join(str(widget.render()) for widget in app.screen.query(Static))

    assert "在线 ASR" in visible


@pytest.mark.asyncio
async def test_home_does_not_offer_to_continue_a_dead_running_task(
    tmp_path, monkeypatch
):
    task = {
        "task_id": "stale",
        "input_name": "stale.wav",
        "status": "running",
        "pid": 999_999_999,
        "log_path": str(tmp_path / "missing.jsonl"),
        "output_path": str(tmp_path / "missing.srt"),
    }

    class Store:
        def __init__(self, _path):
            pass

        def load(self):
            return SimpleNamespace(recent_tasks=[task])

    monkeypatch.setattr("subtap.ui.v2.home.StateStore", Store)

    app = HomeApp()
    async with app.run_test():
        assert not list(app.screen.query("#continue-task"))


@pytest.mark.asyncio
async def test_home_requires_pid_evidence_for_running_task(tmp_path, monkeypatch):
    task = {
        "task_id": "legacy",
        "input_name": "legacy.wav",
        "status": "running",
        "log_path": str(tmp_path / "run.log.jsonl"),
        "output_path": str(tmp_path / "legacy.srt"),
    }
    Path(task["log_path"]).write_text("", encoding="utf-8")

    class Store:
        def __init__(self, _path):
            pass

        def load(self):
            return SimpleNamespace(recent_tasks=[task])

    monkeypatch.setattr("subtap.ui.v2.home.StateStore", Store)

    app = HomeApp()
    async with app.run_test():
        assert not list(app.screen.query("#continue-task"))


@pytest.mark.asyncio
async def test_home_exposes_recent_tasks_as_direct_buttons(tmp_path, monkeypatch):
    tasks = [
        {
            "task_id": f"task-{index}",
            "input_name": f"recording-{index}.wav",
            "status": "completed",
            "output_path": str(tmp_path / f"recording-{index}.srt"),
        }
        for index in range(4)
    ]

    class Store:
        def __init__(self, _path):
            pass

        def load(self):
            return SimpleNamespace(recent_tasks=tasks)

    monkeypatch.setattr("subtap.ui.v2.home.StateStore", Store)

    async with HomeApp().run_test() as pilot:
        buttons = list(pilot.app.screen.query(".recent-task"))
        assert [button.name for button in buttons] == [
            "task-0",
            "task-1",
            "task-2",
        ]


@pytest.mark.asyncio
async def test_home_refreshes_task_state_when_resumed(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state.json")
    monkeypatch.setattr("subtap.ui.v2.home.StateStore", lambda _path: store)
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._observer_process_matches_run_id",
        lambda _pid, _run_id: True,
    )
    app = HomeApp()

    async with app.run_test() as pilot:
        assert not list(app.screen.query("#continue-task"))
        store.add_recent_task(
            "live",
            "voice.wav",
            str(tmp_path / "voice.srt"),
            status="running",
            pid=os.getpid(),
        )
        await app.push_screen(Screen())
        app.pop_screen()
        await pilot.pause()

        assert app.screen.query_one("#continue-task", Button)


@pytest.mark.asyncio
async def test_home_drops_continue_action_when_process_dies(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "state.json")
    store.add_recent_task(
        "live",
        "voice.wav",
        str(tmp_path / "voice.srt"),
        status="running",
        pid=123,
    )
    alive = True

    def probe(_pid, _signal):
        if not alive:
            raise ProcessLookupError

    monkeypatch.setattr("subtap.ui.v2.home.StateStore", lambda _path: store)
    monkeypatch.setattr(
        "subtap.ui.observer.os.kill",
        probe,
    )
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._observer_process_matches_run_id",
        lambda _pid, _run_id: True,
    )
    app = HomeApp()

    async with app.run_test() as pilot:
        assert app.screen.query_one("#continue-task", Button)
        alive = False
        await app.push_screen(Screen())
        app.pop_screen()
        await pilot.pause()

        assert not list(app.screen.query("#continue-task"))
