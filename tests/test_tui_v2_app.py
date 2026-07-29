import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from subtap.core.state_store import StateStore
from subtap.ui.v2 import SubtapV2App
from subtap.ui.v2.home import HomeScreen
from subtap.ui.v2.new_transcription import NewTranscriptionScreen
from subtap.ui.v2.observer import ObserverTaskScreen
from subtap.ui.v2.screens import BatchScreen, TasksScreen


@pytest.fixture(autouse=True)
def _empty_home_task_index(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    class EmptyStore:
        def __init__(self, _path):
            pass

        def load(self):
            return SimpleNamespace(recent_tasks=[])

    monkeypatch.setattr("subtap.ui.v2.home.StateStore", EmptyStore)


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
        await pilot.pause()
        menu = app.screen.query_one(OptionList)

        assert menu.highlighted == 0
        assert menu.get_option_at_index(0).id == "run"
        assert "新建字幕" in str(menu.get_option_at_index(0).prompt)
        assert "&gt;" not in str(menu.get_option_at_index(0).prompt)

        await pilot.press("down")
        assert menu.highlighted == 1

        await pilot.press("up")
        assert menu.highlighted == 0

        await pilot.press("down", "enter")
        assert isinstance(app.screen, BatchScreen)
        assert app.is_running is True


@pytest.mark.asyncio
async def test_v2_home_uses_simplified_chinese_product_copy():
    app = SubtapV2App()

    async with app.run_test(size=(90, 40)):
        visible = "\n".join(str(widget.render()) for widget in app.screen.query(Static))
        prompts = "\n".join(
            str(menu.get_option_at_index(index).prompt)
            for menu in app.screen.query(OptionList)
            for index in range(menu.option_count)
        )

        assert "本地优先的字幕生成与转录" in visible
        assert "https://github.com/R-jed/Subtap" in visible
        assert "启用在线 ASR 时音频会上传" in visible
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
async def test_home_surfaces_running_task_as_primary_continuation(monkeypatch):
    class RunningStore:
        def __init__(self, _path):
            pass

        def load(self):
            return SimpleNamespace(
                recent_tasks=[
                    {
                        "task_id": "run-1",
                        "input_name": "访谈.mp3",
                        "status": "running",
                        "pid": os.getpid(),
                    }
                ]
            )

    monkeypatch.setattr("subtap.ui.v2.home.StateStore", RunningStore)
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._observer_process_matches_run_id",
        lambda _pid, _run_id: True,
    )
    app = SubtapV2App()

    async with app.run_test(size=(90, 40)):
        visible = "\n".join(str(widget.render()) for widget in app.screen.query(Static))
        assert "任务进行中 · 访谈.mp3" in visible
        assert app.screen.query_one("#continue-task").label.plain == "继续观察任务"


@pytest.mark.asyncio
async def test_new_transcription_opens_inside_v2_and_returns_home_on_escape():
    app = SubtapV2App()

    async with app.run_test(size=(90, 56)) as pilot:
        await pilot.pause()
        await pilot.press("enter")

        assert isinstance(app.screen, NewTranscriptionScreen)
        assert len(app.screen_stack) == 2

        await pilot.press("escape")

        assert isinstance(app.screen, HomeScreen)
        assert len(app.screen_stack) == 1
        assert app.is_running is True


@pytest.mark.asyncio
async def test_new_transcription_starts_inside_the_same_v2_app(monkeypatch):
    app = SubtapV2App()
    command = ["python", "-m", "subtap.cli", "run", "media.wav"]
    started = []
    monkeypatch.setattr(app, "start_transcription", started.append)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        app.screen.dismiss(command)
        await pilot.pause()

        assert started == [command]
        assert app.is_running is True
        assert isinstance(app.screen, HomeScreen)

    assert app.return_value is None


@pytest.mark.asyncio
async def test_home_rejects_unknown_action():
    app = SubtapV2App()

    with pytest.raises(ValueError, match="Unknown Home action"):
        async with app.run_test() as pilot:
            await pilot.pause()
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
        compact_brand = app.screen.query_one("#home-logo-compact", Static)
        full_brand = app.screen.query_one("#home-logo", Static)

        assert "-compact" in app.screen.classes
        assert str(compact_brand.render()) == "SUBTAP"
        assert compact_brand.display is True
        assert full_brand.display is False

        await pilot.resize_terminal(80, 40)
        await pilot.pause()
        assert "-regular" in app.screen.classes
        assert compact_brand.display is False
        assert full_brand.display is True

        await pilot.resize_terminal(103, 40)
        await pilot.pause()
        assert "-regular" in app.screen.classes
        assert full_brand.display is True

        await pilot.resize_terminal(104, 40)
        await pilot.pause()
        assert "-wide" in app.screen.classes
        assert compact_brand.display is False
        assert full_brand.display is True
        assert len(str(full_brand.render()).splitlines()) == 5

        await pilot.resize_terminal(104, 12)
        await pilot.pause()
        assert "-short" in app.screen.classes
        assert compact_brand.display is False
        assert full_brand.display is True

        await pilot.resize_terminal(120, 40)
        await pilot.pause()
        assert app.screen.query_one("#home-shell", Vertical).region.width == 104


@pytest.mark.asyncio
async def test_start_transcription_keeps_task_inside_app_and_q_only_detaches(
    tmp_path, monkeypatch
):
    class FakeProcess:
        pid = 101

        def poll(self):
            return None

    launched = []
    registration_statuses: list[str] = []

    def fake_popen(command, **kwargs):
        store = StateStore(tmp_path / ".subtap" / "state.json")
        task = store.load().recent_tasks[0]
        registration_statuses.append(str(task["status"]))
        store.update_recent_task_status(str(task["task_id"]), "success")
        launched.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(
        "subtap.ui.v2.app.load_config",
        lambda _path, **_kwargs: SimpleNamespace(
            workspace=SimpleNamespace(root=str(tmp_path / "work"))
        ),
    )
    monkeypatch.setattr("subtap.ui.v2.app.subprocess.Popen", fake_popen)
    app = SubtapV2App()
    command = [
        "python",
        "-m",
        "subtap.cli",
        "run",
        str(tmp_path / "media.wav"),
        "--output-dir",
        str(tmp_path / "output"),
        "--tui-v2",
    ]

    async with app.run_test(size=(90, 40)) as pilot:
        app.start_transcription(command)
        await pilot.pause()

        assert isinstance(app.screen, ObserverTaskScreen)
        assert "--tui-v2" not in launched[0][0]
        assert launched[0][0][-2:] == ["--observer-child", "--no-tui"]
        assert app._output_path == Path(tmp_path / "output" / "media.srt")
        assert app._log_path.parent.parent == tmp_path / "work" / "jobs"
        assert launched[0][1]["env"]["SUBTAP_EVENT_LOG"] == str(app._log_path)
        task = StateStore(tmp_path / ".subtap" / "state.json").load().recent_tasks[0]
        assert registration_statuses == ["starting"]
        assert task["pid"] == 101
        assert task["status"] == "success"

        await pilot.press("q")
        await pilot.pause()

        assert isinstance(app.screen, TasksScreen)
        assert app._process.poll() is None
        assert app.is_running is True


@pytest.mark.asyncio
async def test_start_transcription_spawn_failure_removes_reserved_task(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "subtap.ui.v2.app.load_config",
        lambda _path, **_kwargs: SimpleNamespace(
            workspace=SimpleNamespace(root=str(tmp_path / "work"))
        ),
    )
    monkeypatch.setattr(
        "subtap.ui.v2.app.subprocess.Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("spawn failed")),
    )
    app = SubtapV2App()

    async with app.run_test():
        with pytest.raises(OSError, match="spawn failed"):
            app.start_transcription(
                [
                    "python",
                    "-m",
                    "subtap.cli",
                    "run",
                    str(tmp_path / "media.wav"),
                ]
            )

    state = StateStore(tmp_path / ".subtap" / "state.json").load()
    assert state.recent_tasks == []


@pytest.mark.asyncio
async def test_start_transcription_does_not_spawn_when_task_registration_fails(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "subtap.ui.v2.app.load_config",
        lambda _path, **_kwargs: SimpleNamespace(
            workspace=SimpleNamespace(root=str(tmp_path / "work"))
        ),
    )
    monkeypatch.setattr(
        "subtap.ui.v2.app.StateStore.add_recent_task",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("状态文件不可写")),
    )
    launched = []
    monkeypatch.setattr(
        "subtap.ui.v2.app.subprocess.Popen",
        lambda *args, **kwargs: launched.append((args, kwargs)),
    )
    app = SubtapV2App()

    async with app.run_test():
        with pytest.raises(OSError, match="状态文件不可写"):
            app.start_transcription(
                [
                    "python",
                    "-m",
                    "subtap.cli",
                    "run",
                    str(tmp_path / "media.wav"),
                ]
            )

    assert launched == []


@pytest.mark.asyncio
async def test_start_transcription_stops_child_when_pid_registration_fails(
    tmp_path, monkeypatch
):
    process = SimpleNamespace(pid=102)
    stopped = []
    monkeypatch.setattr(
        "subtap.ui.v2.app.load_config",
        lambda _path, **_kwargs: SimpleNamespace(
            workspace=SimpleNamespace(root=str(tmp_path / "work"))
        ),
    )
    monkeypatch.setattr("subtap.ui.v2.app.subprocess.Popen", lambda *_a, **_k: process)
    monkeypatch.setattr(
        "subtap.ui.v2.app.StateStore.attach_recent_task_process",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "subtap.ui.v2.app._stop_observer_child",
        lambda child: stopped.append(child),
    )
    app = SubtapV2App()

    async with app.run_test():
        with pytest.raises(RuntimeError, match="任务不存在"):
            app.start_transcription(
                [
                    "python",
                    "-m",
                    "subtap.cli",
                    "run",
                    str(tmp_path / "media.wav"),
                ]
            )

    assert stopped == [process]


@pytest.mark.asyncio
async def test_consecutive_tasks_receive_distinct_persistent_logs(
    tmp_path, monkeypatch
):
    class FinishedProcess:
        pid = 102

        def poll(self):
            return 0

    monkeypatch.setattr(
        "subtap.ui.v2.app.load_config",
        lambda _path, **_kwargs: SimpleNamespace(
            workspace=SimpleNamespace(root=str(tmp_path / "work"))
        ),
    )
    monkeypatch.setattr(
        "subtap.ui.v2.app.subprocess.Popen",
        lambda *_args, **_kwargs: FinishedProcess(),
    )
    app = SubtapV2App()

    async with app.run_test() as pilot:
        for filename in ("first.wav", "second.wav"):
            app.start_transcription(
                [
                    "python",
                    "-m",
                    "subtap.cli",
                    "run",
                    str(tmp_path / filename),
                    "--output-dir",
                    str(tmp_path / "output"),
                ]
            )
            await pilot.pause()
            if filename == "first.wav":
                first_log = app._log_path
                app.action_quit_observer()
                await pilot.pause()

        assert first_log != app._log_path
        assert first_log.parent != app._log_path.parent


def test_app_keeps_only_live_batch_processes():
    class Process:
        def __init__(self):
            self.returncode = None

        def poll(self):
            return self.returncode

    process = Process()
    app = SubtapV2App()

    app.register_batch_process("batch-1", process)

    assert app.get_batch_process("batch-1") is process
    process.returncode = 0
    assert app.get_batch_process("batch-1") is None
    assert app.get_batch_process("batch-1") is None


@pytest.mark.asyncio
async def test_resume_observer_only_reopens_the_live_task_owned_by_app(
    tmp_path, monkeypatch
):
    class Process:
        pid = os.getpid()

        def poll(self):
            return None

    app = SubtapV2App()
    app._run_id = "live-task"
    app._process = Process()
    app._log_path = tmp_path / "run.log.jsonl"
    app._output_path = tmp_path / "result.srt"
    app._diagnostic_path = tmp_path / "run.log"

    async with app.run_test() as pilot:
        assert app.resume_observer("other-task") is False
        assert app.resume_observer("live-task") is True
        await pilot.pause()
        assert isinstance(app.screen, ObserverTaskScreen)
        timer = app._observer_timer
        assert timer is not None
        stop = Mock(wraps=timer.stop)
        monkeypatch.setattr(timer, "stop", stop)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, TasksScreen)
        assert app._observer_timer is None
        assert app._task_screen is None
        assert stop.call_count == 1


def test_app_keeps_model_operation_until_screen_presents_the_result():
    class Process:
        returncode = None

        def poll(self):
            return self.returncode

    process = Process()
    app = SubtapV2App()

    app.register_model_process(process, "完整校验")
    assert app.get_model_process() == (process, "完整校验")

    process.returncode = 0
    assert app.get_model_process() == (process, "完整校验")

    app.clear_model_process(process)
    assert app.get_model_process() is None


@pytest.mark.asyncio
async def test_app_stops_untracked_model_operation_when_tool_exits(monkeypatch):
    class Process:
        def poll(self):
            return None

    process = Process()
    stopped = []
    monkeypatch.setattr(
        "subtap.ui.v2.app._stop_observer_child",
        lambda child: stopped.append(child),
    )
    app = SubtapV2App()
    app.register_model_process(process, "安装")

    async with app.run_test():
        pass

    assert stopped == [process]
