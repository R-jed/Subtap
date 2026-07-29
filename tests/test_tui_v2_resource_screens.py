from types import SimpleNamespace
import json
import os
from pathlib import Path
import sys
import time

import pytest
from textual.app import App
from textual.widgets import Button, Input, OptionList, Select, Static

from subtap.core.state_store import StateStore
from subtap.schemas.glossary import load_glossary
from subtap.ui.v2 import SubtapV2App
from subtap.ui.v2.screens import (
    BatchScreen,
    BatchTaskScreen,
    HotwordsScreen,
    ModelsScreen,
    PreferencesScreen,
    RecordedTaskScreen,
    TasksScreen,
    SystemCheckScreen,
)


class ScreenApp(App[None]):
    pass


@pytest.mark.asyncio
async def test_batch_start_uses_existing_cli_without_leaving_app(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "clip.mp3").write_bytes(b"audio")
    glossary_root = tmp_path / ".subtap" / "glossaries"
    glossary_root.mkdir(parents=True)
    (glossary_root / "default.txt").write_text("GR IV = GR4\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    started = []

    class Process:
        pid = 4321

        def poll(self):
            return None

    monkeypatch.setattr(
        "subtap.ui.v2.screens.subprocess.Popen",
        lambda command, **kwargs: started.append((command, kwargs)) or Process(),
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        screen = BatchScreen()
        screen.input_dir = media_dir
        screen.output_dir = output_dir
        await app.push_screen(screen)
        screen.query_one("#review-batch", Button).disabled = False
        screen.query_one("#review-batch", Button).press()
        await pilot.pause()

        assert isinstance(app.screen, BatchTaskScreen)
        assert started[0][0][3:7] == [
            "batch-transcribe",
            "--dir",
            str(media_dir),
            "--mode",
        ]
        assert "--no-confirm" in started[0][0]
        assert str(output_dir) in started[0][0]
        assert started[0][0][started[0][0].index("--hotwords") + 1] == "GR IV,GR4"
        assert "运行中" in str(
            app.screen.query_one("#batch-run-status", Static).render()
        )
        task = StateStore(tmp_path / ".subtap" / "state.json").load().recent_tasks[0]
        assert task["task_id"].startswith("batch-")
        assert task["status"] == "running"
        assert task["pid"] == 4321
        assert task["output_path"] == str(output_dir / "manifest.json")


@pytest.mark.asyncio
async def test_batch_selection_reports_unsupported_files(tmp_path, monkeypatch):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "clip.mp3").write_bytes(b"audio")
    (media_dir / "notes.txt").write_text("not media", encoding="utf-8")
    monkeypatch.setattr(
        "subtap.ui.v2.screens.choose_folder",
        lambda _prompt: media_dir,
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(BatchScreen())
        app.screen.query_one("#choose-batch", Button).press()
        await pilot.pause()

        status = str(app.screen.query_one("#batch-status", Static).render())
        assert "找到 1 个媒体文件" in status
        assert "1 个不可处理" in status
        assert "notes.txt" in status


@pytest.mark.asyncio
async def test_batch_does_not_spawn_when_task_registration_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    output_dir = tmp_path / "output"
    started = []

    def fail_registration(*args, **kwargs):
        raise OSError("状态文件不可写")

    monkeypatch.setattr(
        "subtap.ui.v2.screens.StateStore.add_recent_task",
        fail_registration,
    )
    monkeypatch.setattr(
        "subtap.ui.v2.screens.subprocess.Popen",
        lambda *args, **kwargs: started.append(args),
    )
    app = ScreenApp()

    async with app.run_test():
        screen = BatchScreen()
        screen.input_dir = media_dir
        screen.output_dir = output_dir
        await app.push_screen(screen)

        with pytest.raises(OSError, match="状态文件不可写"):
            screen.start_batch()

        assert started == []


@pytest.mark.asyncio
async def test_batch_stops_child_when_pid_registration_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    stopped = []

    class Process:
        pid = 4321

    process = Process()

    def fail_pid_registration(*args, **kwargs):
        raise OSError("状态文件不可写")

    monkeypatch.setattr(
        "subtap.ui.v2.screens.subprocess.Popen",
        lambda *args, **kwargs: process,
    )
    monkeypatch.setattr(
        "subtap.ui.v2.screens.StateStore.attach_recent_task_process",
        fail_pid_registration,
    )
    monkeypatch.setattr(
        "subtap.ui.v2.screens._stop_observer_child",
        lambda child: stopped.append(child),
    )
    app = ScreenApp()

    async with app.run_test():
        screen = BatchScreen()
        screen.input_dir = media_dir
        screen.output_dir = tmp_path / "output"
        await app.push_screen(screen)

        with pytest.raises(OSError, match="状态文件不可写"):
            screen.start_batch()

        assert stopped == [process]


@pytest.mark.asyncio
async def test_tasks_use_structured_running_without_log_and_recorded_for_history(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    store = StateStore(tmp_path / ".subtap" / "state.json")
    history_log = tmp_path / "history.log.jsonl"
    history_log.write_text("", encoding="utf-8")
    store.add_recent_task(
        "history-1",
        "history.mp3",
        str(tmp_path / "history.srt"),
        log_path=str(history_log),
        status="recorded",
    )
    store.add_recent_task(
        "running-2",
        "running-with-log.mp3",
        str(tmp_path / "running-with-log.srt"),
        log_path=str(history_log),
        status="running",
        pid=999_999_999,
    )
    store.add_recent_task(
        "running-1",
        "running.mp3",
        str(tmp_path / "running.srt"),
        log_path=str(tmp_path / "missing.log.jsonl"),
        status="running",
        pid=999_999_998,
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(TasksScreen())
        await pilot.pause()
        task_list = app.screen.query_one("#task-list", OptionList)

        assert "状态未知" in str(task_list.get_option_at_index(0).prompt)
        assert "状态未知" in str(task_list.get_option_at_index(1).prompt)
        assert "任务记录" in str(task_list.get_option_at_index(2).prompt)


@pytest.mark.asyncio
async def test_tasks_can_auto_open_a_persisted_task_by_id(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text("", encoding="utf-8")
    StateStore(tmp_path / ".subtap" / "state.json").add_recent_task(
        "run-1",
        "clip.mp3",
        str(tmp_path / "clip.srt"),
        log_path=str(log_path),
        status="recorded",
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(TasksScreen(auto_open_task_id="run-1"))
        await pilot.pause()

        assert isinstance(app.screen, RecordedTaskScreen)


@pytest.mark.asyncio
async def test_tasks_open_live_pid_as_running_in_read_only_observer(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text("", encoding="utf-8")
    StateStore(tmp_path / ".subtap" / "state.json").add_recent_task(
        "run-live",
        "clip.mp3",
        str(tmp_path / "clip.srt"),
        log_path=str(log_path),
        status="running",
        pid=os.getpid(),
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(TasksScreen(auto_open_task_id="run-live"))
        await pilot.pause()

        visible = "\n".join(str(widget.render()) for widget in app.screen.query(Static))
        assert isinstance(app.screen, RecordedTaskScreen)
        assert "任务运行中" in visible


@pytest.mark.asyncio
async def test_reopened_live_task_q_returns_to_tasks_and_x_offers_stop(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "event_type": "stage_start",
                "timestamp": 1.0,
                "data": {"stage": "asr"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    StateStore(tmp_path / ".subtap" / "state.json").add_recent_task(
        "run-live",
        "clip.mp3",
        str(tmp_path / "clip.srt"),
        log_path=str(log_path),
        status="running",
        pid=os.getpid(),
    )
    monkeypatch.setattr(
        "subtap.ui.v2.screens._observer_process_matches_run_id",
        lambda _pid, _task_id: True,
    )
    app = SubtapV2App()

    async with app.run_test() as pilot:
        tasks = TasksScreen(auto_open_task_id="run-live")
        await app.push_screen(tasks)
        await pilot.pause()

        await pilot.press("x")
        await pilot.pause()
        assert "停止当前任务" in "\n".join(
            str(widget.render()) for widget in app.screen.query(Static)
        )
        await pilot.press("n")
        await pilot.pause()

        await pilot.press("q")
        await pilot.pause()
        assert app.is_running is True
        assert app.screen is tasks


@pytest.mark.asyncio
async def test_reopened_live_task_confirmed_stop_targets_persisted_process_group(
    tmp_path, monkeypatch
):
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "run_id": "run-live",
                "event_type": "stage_start",
                "timestamp": time.time(),
                "data": {"stage": "asr"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    stopped = []
    recorded = []
    monkeypatch.setattr(
        "subtap.ui.v2.screens._stop_observer_process_group",
        stopped.append,
    )
    monkeypatch.setattr(
        "subtap.ui.v2.screens._record_interrupted_task",
        lambda *args, **kwargs: recorded.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "subtap.ui.v2.screens._observer_process_matches_run_id",
        lambda _pid, _task_id: True,
    )
    monkeypatch.setattr("subtap.ui.observer._pid_is_alive", lambda _pid: True)
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(
            RecordedTaskScreen(
                log_path,
                tmp_path / "clip.srt",
                pid=4321,
                task_id="run-live",
            )
        )
        await pilot.press("x")
        await pilot.press("y")
        await pilot.pause()

    assert stopped == [4321]
    assert recorded[0][0][1] == "run-live"


@pytest.mark.asyncio
async def test_reopened_live_task_refuses_to_stop_reused_pid(tmp_path, monkeypatch):
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text("", encoding="utf-8")
    monkeypatch.setattr("subtap.ui.observer._pid_is_alive", lambda _pid: True)
    monkeypatch.setattr(
        "subtap.ui.v2.screens._observer_process_matches_run_id",
        lambda _pid, _task_id: False,
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        screen = RecordedTaskScreen(
            log_path,
            tmp_path / "clip.srt",
            pid=4321,
            task_id="run-live",
        )
        await app.push_screen(screen)
        await pilot.press("x")
        await pilot.pause()

        assert app.screen is screen


@pytest.mark.asyncio
async def test_tasks_can_reopen_running_batch_from_persisted_manifest(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    manifest_path = tmp_path / "output" / "manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "version": 2,
                "items": [
                    {
                        "input_path": str(tmp_path / "clip.mp3"),
                        "status": "running",
                    }
                ],
                "succeeded": 0,
                "failed": 0,
                "interrupted": 0,
            }
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "batch.log"
    log_path.write_text("", encoding="utf-8")
    StateStore(tmp_path / ".subtap" / "state.json").add_recent_task(
        "batch-run-1",
        "media（批量）",
        str(manifest_path),
        log_path=str(log_path),
        status="running",
        pid=999_999_997,
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        tasks = TasksScreen(auto_open_task_id="batch-run-1")
        await app.push_screen(tasks)
        await pilot.pause()

        assert isinstance(app.screen, BatchTaskScreen)
        assert "状态未知" in str(
            app.screen.query_one("#batch-run-status", Static).render()
        )

        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is tasks


@pytest.mark.asyncio
async def test_tasks_reconciles_terminal_batch_manifest_into_unified_state(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    manifest_path = tmp_path / "output" / "manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "version": 2,
                "items": [
                    {"input_path": "ok.mp3", "status": "succeeded"},
                    {"input_path": "failed.mp3", "status": "failed"},
                ],
                "succeeded": 1,
                "failed": 1,
                "interrupted": 0,
            }
        ),
        encoding="utf-8",
    )
    store = StateStore(tmp_path / ".subtap" / "state.json")
    store.add_recent_task(
        "batch-run-1",
        "media（批量）",
        str(manifest_path),
        status="running",
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(TasksScreen())
        await pilot.pause()
        prompt = (
            app.screen.query_one("#task-list", OptionList).get_option_at_index(0).prompt
        )

        assert "部分失败" in str(prompt)
        assert store.load().recent_tasks[0]["status"] == "partial_failure"


@pytest.mark.asyncio
async def test_hotwords_accept_all_moves_valid_terms_to_user_file(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    root = tmp_path / ".subtap" / "glossaries"
    root.mkdir(parents=True)
    (root / "default.txt").write_text("Subtap\n", encoding="utf-8")
    (root / "learned.txt").write_text("GR IV = GR4\n", encoding="utf-8")
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(HotwordsScreen())
        app.screen.query_one("#accept-learned", Button).press()
        await pilot.pause()

        words = [term.canonical for term in load_glossary(root / "default.txt").terms]
        assert words == ["Subtap", "GR IV"]
        assert (root / "learned.txt").read_text(encoding="utf-8") == ""
        assert "已加入 1 个热词" in str(
            app.screen.query_one("#hotword-status", Static).render()
        )


@pytest.mark.asyncio
async def test_hotwords_rejects_invalid_learned_file_without_writing_default(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    root = tmp_path / ".subtap" / "glossaries"
    root.mkdir(parents=True)
    default = root / "default.txt"
    default.write_text("Subtap\n", encoding="utf-8")
    (root / "learned.txt").write_text("GR IV =\n", encoding="utf-8")
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(HotwordsScreen())
        app.screen.query_one("#accept-learned", Button).press()
        await pilot.pause()

        assert default.read_text(encoding="utf-8") == "Subtap\n"
        status = str(app.screen.query_one("#hotword-status", Static).render())
        assert "无法加入" in status
        assert "第 1 行" in status


@pytest.mark.asyncio
async def test_hotwords_can_accept_one_learned_term(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    root = tmp_path / ".subtap" / "glossaries"
    root.mkdir(parents=True)
    (root / "learned.txt").write_text("GR4 = GR IV\nSubtap\n", encoding="utf-8")
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(HotwordsScreen())
        app.screen.query_one("#accept-selected-learned", Button).press()
        await pilot.pause()

        assert "GR4 = GR IV" in (root / "default.txt").read_text(encoding="utf-8")
        assert (root / "learned.txt").read_text(encoding="utf-8") == "Subtap\n"


@pytest.mark.asyncio
async def test_hotwords_migrates_legacy_file_without_overwriting_source(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    legacy = tmp_path / "camera.yaml"
    legacy_content = "terms:\n  - canonical: GR4\n    aliases: [GR IV]\n"
    legacy.write_text(legacy_content, encoding="utf-8")
    monkeypatch.setattr(
        "subtap.ui.v2.screens.choose_file",
        lambda _prompt: legacy,
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(HotwordsScreen())
        app.screen.query_one("#migrate-glossary", Button).press()
        await pilot.pause()

        migrated = tmp_path / ".subtap" / "glossaries" / "camera.txt"
        assert migrated.read_text(encoding="utf-8") == "GR4 = GR IV\n"
        assert legacy.read_text(encoding="utf-8") == legacy_content


@pytest.mark.asyncio
async def test_models_use_product_names_instead_of_registry_ids(monkeypatch):
    class FakeRegistry:
        def __init__(self, _config):
            pass

        def status(self):
            return [
                SimpleNamespace(name="asr_0.6b", installed=True, path="/models/fast"),
                SimpleNamespace(
                    name="asr_1.7b", installed=False, path="/models/quality"
                ),
            ]

    monkeypatch.setattr(
        "subtap.ui.v2.screens.load_config",
        lambda *args, **kwargs: SimpleNamespace(asr=SimpleNamespace(model="asr_0.6b")),
    )
    monkeypatch.setattr("subtap.ui.v2.screens.ModelRegistry", FakeRegistry)
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(ModelsScreen())
        await pilot.pause()
        visible = "\n".join(str(widget.render()) for widget in app.screen.query(Static))

        assert "快速模式 · 0.6B" in visible
        assert "高质量模式 · 1.7B" in visible
        assert "文件不完整" in visible


@pytest.mark.asyncio
async def test_preferences_reports_save_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.v2.screens.load_config",
        lambda *args, **kwargs: SimpleNamespace(
            asr=SimpleNamespace(model="asr_0.6b"),
            output=SimpleNamespace(max_chars=30),
        ),
    )

    def fail_save(_self):
        raise OSError("磁盘不可写")

    monkeypatch.setattr("subtap.ui.v2.screens.ConfigManager.save", fail_save)
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(PreferencesScreen())
        app.screen.query_one("#save-preferences", Button).press()
        await pilot.pause()

        assert "保存失败：磁盘不可写" in str(
            app.screen.query_one("#preference-status", Static).render()
        )


@pytest.mark.asyncio
async def test_models_failed_install_stops_polling_and_allows_retry(
    tmp_path, monkeypatch
):
    class FakeRegistry:
        def __init__(self, _config):
            pass

        def status(self):
            return [
                SimpleNamespace(
                    name="asr_1.7b", installed=False, path="/models/quality"
                )
            ]

    class FailedProcess:
        def __init__(self):
            self.poll_count = 0

        def poll(self):
            self.poll_count += 1
            return 1

    process = FailedProcess()
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.v2.screens.load_config",
        lambda *args, **kwargs: SimpleNamespace(asr=SimpleNamespace(model="asr_0.6b")),
    )
    monkeypatch.setattr("subtap.ui.v2.screens.ModelRegistry", FakeRegistry)
    monkeypatch.setattr(
        "subtap.ui.v2.screens.subprocess.Popen", lambda *args, **kwargs: process
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(ModelsScreen())
        app.screen.query_one(".model-install", Button).press()
        await pilot.pause(1.1)

        button = app.screen.query_one(".model-install", Button)
        status = str(app.screen.query_one("#model-status", Static).render())
        poll_count = process.poll_count
        assert button.disabled is False
        assert "安装失败" in status

        await pilot.pause(1.1)
        assert process.poll_count == poll_count


@pytest.mark.asyncio
async def test_models_full_verification_runs_hash_check_command(tmp_path, monkeypatch):
    class FakeRegistry:
        def __init__(self, _config):
            pass

        def status(self):
            return [
                SimpleNamespace(name="asr_0.6b", installed=True, path="/models/fast")
            ]

    class SuccessfulProcess:
        pid = 4321

        def poll(self):
            return 0

    started = []
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.v2.screens.load_config",
        lambda *args, **kwargs: SimpleNamespace(asr=SimpleNamespace(model="asr_0.6b")),
    )
    monkeypatch.setattr("subtap.ui.v2.screens.ModelRegistry", FakeRegistry)
    monkeypatch.setattr(
        "subtap.ui.v2.screens.subprocess.Popen",
        lambda command, **kwargs: started.append(command) or SuccessfulProcess(),
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(ModelsScreen())
        app.screen.query_one("#verify-models", Button).press()
        await pilot.pause(1.1)

        assert started == [[sys.executable, "-m", "subtap.cli", "models", "verify"]]
        assert "完整校验通过" in str(
            app.screen.query_one("#model-status", Static).render()
        )


@pytest.mark.asyncio
async def test_models_reclaim_running_operation_after_returning(tmp_path, monkeypatch):
    class FakeRegistry:
        def __init__(self, _config):
            pass

        def status(self):
            return [
                SimpleNamespace(name="asr_0.6b", installed=True, path="/models/fast")
            ]

    class RunningProcess:
        pid = 4321

        def poll(self):
            return None

    process = RunningProcess()
    started = []
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.v2.screens.load_config",
        lambda *args, **kwargs: SimpleNamespace(asr=SimpleNamespace(model="asr_0.6b")),
    )
    monkeypatch.setattr("subtap.ui.v2.screens.ModelRegistry", FakeRegistry)
    monkeypatch.setattr(
        "subtap.ui.v2.screens.subprocess.Popen",
        lambda *args, **kwargs: started.append(args) or process,
    )
    app = SubtapV2App()

    async with app.run_test() as pilot:
        await app.push_screen(ModelsScreen())
        app.screen.query_one("#verify-models", Button).press()
        await pilot.pause()
        app.pop_screen()
        await app.push_screen(ModelsScreen())
        await pilot.pause()

        assert len(started) == 1
        assert app.screen.query_one("#verify-models", Button).disabled is True
        assert "正在进行" in str(app.screen.query_one("#model-status", Static).render())


@pytest.mark.asyncio
async def test_preferences_dirty_back_requires_discard_confirmation(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.v2.screens.load_config",
        lambda *args, **kwargs: SimpleNamespace(
            asr=SimpleNamespace(model="asr_0.6b"),
            output=SimpleNamespace(max_chars=30),
        ),
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        root_screen = app.screen
        preferences = PreferencesScreen()
        await app.push_screen(preferences)
        preferences.query_one("#default-chars", Input).value = "32"
        await pilot.press("escape")
        await pilot.pause()

        visible = "\n".join(str(widget.render()) for widget in app.screen.query(Static))
        assert "未保存" in visible
        assert app.screen is not preferences

        app.screen.query_one("#discard-preferences", Button).press()
        await pilot.pause()
        assert app.screen is root_screen


@pytest.mark.asyncio
async def test_preferences_reads_user_config(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config_path = tmp_path / ".subtap" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text(
        "mode: online\n"
        "asr:\n  model: asr_1.7b\n"
        "output:\n  max_chars: 42\n  directory: /tmp/subtap-output\n",
        encoding="utf-8",
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(PreferencesScreen())
        await pilot.pause()

        assert app.screen.query_one("#default-model", Select).value == "asr_1.7b"
        assert app.screen.query_one("#default-chars", Input).value == "42"
        assert (
            app.screen.query_one("#default-output", Input).value == "/tmp/subtap-output"
        )
        assert app.screen.query_one("#default-service-mode", Select).value == "online"


@pytest.mark.asyncio
async def test_tasks_empty_state_offers_new_transcription(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(TasksScreen())
        await pilot.pause()

        assert app.screen.query_one("#empty-new-task", Button).label.plain == "新建字幕"


@pytest.mark.asyncio
async def test_system_check_distinguishes_warning_from_blocked(monkeypatch):
    app = ScreenApp()

    async with app.run_test() as pilot:
        screen = SystemCheckScreen()
        monkeypatch.setattr(
            screen,
            "_run_checks",
            lambda: [
                ("权限与空间", "磁盘空间", "8.0 GB", "warning"),
                ("依赖", "音视频处理", "/usr/bin/ffmpeg", "ok"),
            ],
        )
        await app.push_screen(screen)
        screen.query_one("#rerun-system-check", Button).press()
        await pilot.pause()

        visible = "\n".join(str(widget.render()) for widget in screen.query(Static))
        assert "需要处理" in visible
        assert "无法使用" not in visible
        assert screen.query_one(".check-card.warning")


@pytest.mark.asyncio
async def test_system_check_reports_missing_config_as_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(SystemCheckScreen())
        initial = "\n".join(str(widget.render()) for widget in app.screen.query(Static))
        assert "尚未开始检查" in initial

        app.screen.query_one("#rerun-system-check", Button).press()
        await pilot.pause()
        visible = "\n".join(str(widget.render()) for widget in app.screen.query(Static))

        assert "配置文件" in visible
        assert "依赖" in visible
        assert "模型" in visible
        assert "路径与配置" in visible
        assert "权限与空间" in visible
        assert "存在阻塞项" in visible
        assert app.screen.query(".check-card").first().has_class("blocked")


def test_system_check_uses_configured_output_directory(tmp_path, monkeypatch):
    output_dir = tmp_path / "read-only-output"
    output_dir.mkdir()
    config_path = tmp_path / ".subtap" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text(
        f"output:\n  directory: {output_dir}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.v2.screens.ModelRegistry.status",
        lambda _self: [],
    )
    monkeypatch.setattr(
        "subtap.ui.v2.screens.os.access",
        lambda path, _mode: Path(path) != output_dir,
    )

    checks = SystemCheckScreen()._run_checks()
    output_check = next(check for check in checks if check[1] == "默认输出目录")

    assert output_check[2] == str(output_dir)
    assert output_check[3] == "blocked"


def test_system_check_rejects_regular_file_as_output_directory(tmp_path, monkeypatch):
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("", encoding="utf-8")
    config_path = tmp_path / ".subtap" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text(
        f"output:\n  directory: {output_file}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.v2.screens.ModelRegistry.status",
        lambda _self: [],
    )

    checks = SystemCheckScreen()._run_checks()
    output_check = next(check for check in checks if check[1] == "默认输出目录")

    assert output_check[3] == "blocked"


@pytest.mark.asyncio
async def test_batch_unchanged_ticks_do_no_manifest_work(tmp_path, monkeypatch):
    """500 items, 100 unchanged ticks: load_manifest NOT called"""
    from subtap.ui.v2.screens import BatchTaskScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    manifest_path = tmp_path / "manifest.json"
    items = [{"input_path": f"/audio/{i}.wav", "status": "pending"} for i in range(500)]
    manifest_path.write_text(
        json.dumps(
            {
                "version": 2,
                "items": items,
                "succeeded": 0,
                "failed": 0,
                "interrupted": 0,
            }
        ),
        encoding="utf-8",
    )

    call_count = [0]
    import subtap.batch as batch_module

    original_load = batch_module.load_manifest

    def spy_load_manifest(path):
        call_count[0] += 1
        return original_load(path)

    monkeypatch.setattr("subtap.batch.load_manifest", spy_load_manifest)

    class Process:
        def poll(self):
            return None

    app = ScreenApp()
    async with app.run_test() as pilot:
        screen = BatchTaskScreen(
            process=Process(),
            manifest_path=manifest_path,
            log_path=tmp_path / "batch.log",
            task_id="batch-1",
        )
        await app.push_screen(screen)
        await pilot.pause()

        for _ in range(100):
            screen.refresh_batch()
            await pilot.pause()

    assert call_count[0] <= 1


@pytest.mark.asyncio
async def test_tasks_list_cold_open_does_not_read_terminal_batch_manifests(
    tmp_path, monkeypatch
):
    """Opening TasksScreen with 20 terminal batch tasks: zero manifest reads"""
    from subtap.ui.v2.screens import TasksScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    store = StateStore(tmp_path / ".subtap" / "state.json")
    for i in range(20):
        store.add_recent_task(
            f"batch-{i}",
            f"batch_{i}",
            str(tmp_path / f"manifest_{i}.json"),
            status="completed",
        )
        (tmp_path / f"manifest_{i}.json").write_text(
            json.dumps(
                {
                    "version": 2,
                    "items": [],
                    "succeeded": 0,
                    "failed": 0,
                    "interrupted": 0,
                }
            ),
            encoding="utf-8",
        )

    call_count = [0]
    import subtap.batch as batch_module

    original_load = batch_module.load_manifest

    def spy_load_manifest(path):
        call_count[0] += 1
        return original_load(path)

    monkeypatch.setattr("subtap.batch.load_manifest", spy_load_manifest)

    app = ScreenApp()
    async with app.run_test() as pilot:
        screen = TasksScreen()
        await app.push_screen(screen)
        await pilot.pause()

    assert call_count[0] == 0


@pytest.mark.asyncio
async def test_recorded_task_interrupted_via_pipeline_end(tmp_path, monkeypatch):
    """RecordedTaskScreen with pipeline_end(interrupted) shows INTERRUPTED."""
    from subtap.ui.v2.screens import RecordedTaskScreen

    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "run_id": "task-int",
                "event_type": "stage_start",
                "timestamp": 1.0,
                "data": {"stage": "asr"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "schema_version": 2,
                "run_id": "task-int",
                "event_type": "pipeline_end",
                "timestamp": 10.0,
                "data": {
                    "stage": "export",
                    "status": "interrupted",
                    "total_duration_sec": 9.0,
                    "output_ready": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    app = ScreenApp()

    async with app.run_test() as pilot:
        await app.push_screen(
            RecordedTaskScreen(
                log_path, output_path=tmp_path / "out.srt", task_id="task-int"
            )
        )
        await pilot.pause()

        visible = "\n".join(str(widget.render()) for widget in app.screen.query(Static))
        assert "已中断" in visible
        assert "任务未完成" in visible


@pytest.mark.asyncio
async def test_batch_persisted_pid_dies_yields_observation_error(tmp_path, monkeypatch):
    """BatchTaskScreen with dead persisted PID shows observation_error."""
    from subtap.ui.v2.screens import BatchTaskScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 2,
                "items": [
                    {"input_path": str(tmp_path / "clip.mp3"), "status": "running"}
                ],
                "succeeded": 0,
                "failed": 0,
                "interrupted": 0,
            }
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "batch.log"
    log_path.write_text("", encoding="utf-8")
    dead_pid = 999_999_999  # extremely unlikely to exist

    app = ScreenApp()
    async with app.run_test() as pilot:
        screen = BatchTaskScreen(
            process=None,
            manifest_path=manifest_path,
            log_path=log_path,
            task_id="batch-dead",
            persisted_live=True,
            persisted_pid=dead_pid,
        )
        await app.push_screen(screen)
        await pilot.pause()

        status = str(app.screen.query_one("#batch-run-status", Static).render())
        assert "状态未知" in status


@pytest.mark.asyncio
async def test_consecutive_terminal_to_new_task_stack_stays_bounded(
    tmp_path,
    monkeypatch,
):
    """10 cycles of terminal→NewTask keep screen stack depth bounded (≤ 3)."""
    from subtap.ui.v2.task_views import TaskScreen
    from subtap.ui.observer import TaskState, TaskPresentation
    from subtap.ui.v2.new_transcription import NewTranscriptionScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True)
    (tmp_path / ".subtap" / "glossaries").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".subtap" / "glossaries" / "default.txt").write_text(
        "", encoding="utf-8"
    )
    config_path = tmp_path / ".subtap" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        f"workspace:\n  root: {work_dir}\n"
        "output:\n  max_chars: 25\n"
        "  directory: " + str(tmp_path / "output") + "\n"
        "asr:\n  model: asr_0.6b\n",
        encoding="utf-8",
    )

    class FakeProcess:
        def __init__(self):
            self.pid = 999_999_998

        def poll(self):
            return 0

    monkeypatch.setattr(
        "subtap.ui.v2.app.subprocess.Popen",
        lambda *args, **kwargs: FakeProcess(),
    )
    monkeypatch.setattr(
        "subtap.ui.v2.app.StateStore",
        lambda _path: type(
            "FakeStore",
            (),
            {
                "add_recent_task": lambda *a, **kw: None,
                "attach_recent_task_process": lambda *a, **kw: True,
            },
        )(),
    )
    monkeypatch.setattr(
        "subtap.ui.v2.screens.StateStore",
        lambda _path: type(
            "FakeStore",
            (),
            {
                "load": lambda: type("State", (), {"recent_tasks": []})(),
                "add_recent_task": lambda *a, **kw: None,
                "attach_recent_task_process": lambda *a, **kw: True,
            },
        )(),
    )

    pres = TaskPresentation(
        status="任务已完成",
        stage="export",
        progress=100,
        model="fast",
        counts="ASR 草稿：1  已对齐：1",
        current_work="完成",
        stage_lines=(),
        recent_texts=(),
        output_text="[green]✓ 字幕已生成[/green]\n/test.srt",
        state=TaskState.COMPLETED,
        elapsed_sec=10,
        stage_durations=(),
    )

    from subtap.ui.v2 import SubtapV2App

    app = SubtapV2App()

    async with app.run_test(size=(90, 56)) as pilot:
        await pilot.pause()
        initial_depth = len(app.screen_stack)
        max_depth = initial_depth

        for cycle in range(10):
            screen = TaskScreen(pres)
            await app.push_screen(screen)
            await pilot.pause()

            screen.action_new_task()
            await pilot.pause()

            # Dismiss NewTranscriptionScreen with a command to trigger callback
            # (simulates user confirming the new task form)
            nts = app.screen
            assert isinstance(nts, NewTranscriptionScreen)
            nts.dismiss(["run", str(tmp_path / f"clip_{cycle}.wav")])
            await pilot.pause()

            current_depth = len(app.screen_stack)
            max_depth = max(max_depth, current_depth)

            # After dismissal + callback, terminal screen is popped
            # and start_transcription pushes ObserverTaskScreen
            # Stack should be bounded
            assert current_depth <= initial_depth + 3, (
                f"Cycle {cycle}: stack depth {current_depth} "
                f"exceeded {initial_depth + 3}"
            )

        final_depth = len(app.screen_stack)
        assert (
            final_depth <= initial_depth + 3
        ), f"Final stack depth {final_depth} exceeded {initial_depth + 3}"
