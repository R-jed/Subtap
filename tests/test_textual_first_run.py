"""Textual first-run flow tests."""

from __future__ import annotations

import time
from threading import Event, get_ident

import pytest

pytest.importorskip("textual")


def _device(*, free_gb: float = 100) -> dict:
    return {
        "is_apple_silicon": True,
        "has_ffmpeg": True,
        "has_mlx": True,
        "memory_gb": 32,
        "free_gb": free_gb,
    }


@pytest.mark.asyncio
async def test_textual_first_run_prepares_model_plan_off_main_thread(
    tmp_path, monkeypatch
):
    from subtap.ui.command_deck import CommandDeckApp
    from subtap.ui.textual_first_run import FirstRunScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.check_device", lambda self: _device()
    )
    main_thread = get_ident()
    plan_threads = []

    def build_plan(self, names, **kwargs):
        plan_threads.append(get_ident())
        return {
            "model_names": names,
            "size_bytes": 1024,
            "download_bytes": 1024,
            "existing_bytes_by_file": {},
            "verified_files": set(),
            "size_display": "0.1 GB",
            "estimated_seconds": 1,
            "target_dir": str(tmp_path / ".subtap" / "models"),
        }

    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.get_download_plan", build_plan
    )

    app = CommandDeckApp()
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        assert isinstance(app.screen, FirstRunScreen)
        assert plan_threads
        assert all(thread != main_thread for thread in plan_threads)


@pytest.mark.asyncio
async def test_textual_first_run_plan_error_is_visible_and_retryable(
    tmp_path, monkeypatch
):
    from subtap.ui.command_deck import CommandDeckApp
    from subtap.ui.textual_first_run import FirstRunScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.check_device", lambda self: _device()
    )
    attempts = []

    def build_plan(self, names, **kwargs):
        attempts.append(names)
        if len(attempts) == 1:
            raise OSError("permission denied")
        return {
            "model_names": names,
            "size_bytes": 1024,
            "download_bytes": 1024,
            "existing_bytes_by_file": {},
            "verified_files": set(),
            "size_display": "0.1 GB",
            "estimated_seconds": 1,
            "target_dir": str(tmp_path / ".subtap" / "models"),
        }

    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.get_download_plan", build_plan
    )

    app = CommandDeckApp()
    async with app.run_test() as pilot:
        await pilot.pause(0.1)

        assert isinstance(app.screen, FirstRunScreen)
        assert "扫描失败" in str(app.screen.query_one("#status").render())
        assert app.screen.query_one("#download").disabled is False
        assert str(app.screen.query_one("#download").label) == "重新扫描"

        await pilot.click("#download")
        await pilot.pause(0.1)
        assert app.screen.config is not None
        assert str(app.screen.query_one("#download").label) == "下载并自检"


@pytest.mark.asyncio
async def test_command_deck_uses_textual_first_run_and_blocks_insufficient_disk(
    tmp_path, monkeypatch
):
    from subtap.ui.command_deck import CommandDeckApp
    from subtap.ui.textual_first_run import FirstRunScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.check_device",
        lambda self: _device(free_gb=1),
    )
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.get_download_plan",
        lambda self, names, **kwargs: {
            "model_names": names,
            "size_bytes": 2 * 1024**3,
            "download_bytes": 2 * 1024**3,
            "existing_bytes_by_file": {},
            "size_display": "2.0 GB",
            "estimated_seconds": 200,
            "target_dir": str(tmp_path / ".subtap" / "models"),
        },
    )

    app = CommandDeckApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        assert isinstance(app.screen, FirstRunScreen)
        assert app.screen.query_one("#download").disabled is True
        assert "空间不足" in str(app.screen.query_one("#status").render())


@pytest.mark.asyncio
async def test_textual_first_run_uses_remaining_bytes_for_resume_space_check(
    tmp_path, monkeypatch
):
    from subtap.ui.command_deck import CommandDeckApp
    from subtap.ui.textual_first_run import FirstRunScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.check_device",
        lambda self: _device(free_gb=1),
    )
    total = 2 * 1024**3
    remaining = 100 * 1024**2
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.get_download_plan",
        lambda self, names, **kwargs: {
            "model_names": names,
            "size_bytes": total,
            "download_bytes": remaining,
            "existing_bytes_by_file": {
                ("asr_1.7b", "model.safetensors"): total - remaining
            },
            "size_display": "2.0 GB",
            "estimated_seconds": 10,
            "target_dir": str(tmp_path / ".subtap" / "models"),
        },
    )

    app = CommandDeckApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        assert isinstance(app.screen, FirstRunScreen)
        assert app.screen.query_one("#download").disabled is False
        assert "还需下载：0.1 GB" in str(app.screen.query_one("#summary").render())
        progress = app.screen.query_one("#progress")
        assert progress.total == total
        assert progress.progress == total - remaining


@pytest.mark.asyncio
async def test_textual_first_run_downloads_and_verifies_before_completion(
    tmp_path, monkeypatch
):
    from subtap.schemas.config import load_config
    from subtap.ui.command_deck import CommandDeckApp
    from subtap.ui.textual_first_run import FirstRunScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.check_device",
        lambda self: _device(),
    )
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.get_download_plan",
        lambda self, names, **kwargs: {
            "model_names": names,
            "size_bytes": 1024,
            "download_bytes": 1024,
            "existing_bytes_by_file": {},
            "size_display": "0.1 GB",
            "estimated_seconds": 1,
            "target_dir": str(tmp_path / ".subtap" / "models"),
        },
    )
    downloaded = []
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.download_required_models",
        lambda self, config, **kwargs: downloaded.append(
            (config.asr.model, kwargs["source"])
        ),
    )
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.run_required_offline_self_check",
        lambda self, config, **kwargs: None,
    )

    app = CommandDeckApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, FirstRunScreen)

        await pilot.click("#download")
        await pilot.pause(0.2)

        assert not isinstance(app.screen, FirstRunScreen)

    assert downloaded == [("asr_1.7b", "hf")]
    assert load_config(tmp_path / ".subtap" / "config.yaml").asr.model == "asr_1.7b"
    assert (tmp_path / ".subtap" / "state.json").exists()


@pytest.mark.asyncio
async def test_textual_first_run_can_cancel_and_resume_later(tmp_path, monkeypatch):
    from subtap.core.models import DownloadCancelled
    from subtap.ui.command_deck import CommandDeckApp
    from subtap.ui.textual_first_run import FirstRunScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.check_device",
        lambda self: _device(),
    )
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.get_download_plan",
        lambda self, names, **kwargs: {
            "model_names": names,
            "size_bytes": 1024,
            "download_bytes": 1024,
            "existing_bytes_by_file": {},
            "size_display": "0.1 GB",
            "estimated_seconds": 1,
            "target_dir": str(tmp_path / ".subtap" / "models"),
        },
    )

    def wait_for_cancel(self, config, *, progress, cancelled, **kwargs):
        while not cancelled():
            progress("asr_1.7b", "model.safetensors", 512, 1024)
            time.sleep(0.01)
        raise DownloadCancelled("cancelled")

    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.download_required_models",
        wait_for_cancel,
    )

    app = CommandDeckApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#download")
        await pilot.pause(0.05)
        await pilot.press("escape")
        await pilot.pause(0.1)

        assert isinstance(app.screen, FirstRunScreen)
        assert "再次开始" in str(app.screen.query_one("#status").render())
        assert app.screen.query_one("#download").disabled is False

    assert not (tmp_path / ".subtap" / "state.json").exists()


@pytest.mark.asyncio
async def test_textual_first_run_cancel_during_self_check_never_marks_complete(
    tmp_path, monkeypatch
):
    from subtap.ui.command_deck import CommandDeckApp
    from subtap.ui.textual_first_run import FirstRunScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.check_device", lambda self: _device()
    )
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.get_download_plan",
        lambda self, names, **kwargs: {
            "model_names": names,
            "size_bytes": 1024,
            "download_bytes": 1024,
            "existing_bytes_by_file": {},
            "size_display": "0.1 GB",
            "estimated_seconds": 1,
            "target_dir": str(tmp_path / ".subtap" / "models"),
        },
    )
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.download_required_models",
        lambda self, config, **kwargs: None,
    )
    checking = Event()
    release_check = Event()

    def slow_self_check(self, config, **kwargs):
        checking.set()
        while not release_check.is_set():
            time.sleep(0.01)

    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.run_required_offline_self_check",
        slow_self_check,
    )

    app = CommandDeckApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#download")
        await pilot.pause(0.05)
        assert checking.is_set()
        await pilot.press("escape")
        release_check.set()
        await pilot.pause(0.1)

        assert isinstance(app.screen, FirstRunScreen)
        assert "再次开始" in str(app.screen.query_one("#status").render())

    assert not (tmp_path / ".subtap" / "state.json").exists()


@pytest.mark.asyncio
async def test_textual_first_run_drops_stale_hash_cache_after_self_check_failure(
    tmp_path, monkeypatch
):
    from subtap.ui.command_deck import CommandDeckApp
    from subtap.ui.textual_first_run import FirstRunScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.check_device", lambda self: _device()
    )
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.get_download_plan",
        lambda self, names, **kwargs: {
            "model_names": names,
            "size_bytes": 1024,
            "download_bytes": 0,
            "existing_bytes_by_file": {("asr_1.7b", "model.bin"): 1024},
            "verified_files": {("asr_1.7b", "model.bin")},
            "size_display": "0.1 GB",
            "estimated_seconds": 0,
            "target_dir": str(tmp_path / ".subtap" / "models"),
        },
    )
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.download_required_models",
        lambda self, config, **kwargs: None,
    )
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.run_required_offline_self_check",
        lambda self, config, **kwargs: (_ for _ in ()).throw(
            RuntimeError("hash changed")
        ),
    )

    app = CommandDeckApp()
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        await pilot.click("#download")
        await pilot.pause(0.1)

        assert isinstance(app.screen, FirstRunScreen)
        assert app.screen.plan["verified_files"] == set()
        assert app.screen.query_one("#download").disabled is False


@pytest.mark.asyncio
async def test_textual_first_run_does_not_change_config_before_confirmation(
    tmp_path, monkeypatch
):
    from subtap.schemas.config import load_config
    from subtap.ui.command_deck import CommandDeckApp
    from subtap.ui.textual_first_run import FirstRunScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config_path = tmp_path / ".subtap" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    original = "asr:\n  model: asr_0.6b\n"
    config_path.write_text(original)
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.check_device", lambda self: _device()
    )
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.get_download_plan",
        lambda self, names, **kwargs: {
            "model_names": names,
            "size_bytes": 1024,
            "download_bytes": 1024,
            "existing_bytes_by_file": {},
            "size_display": "0.1 GB",
            "estimated_seconds": 1,
            "target_dir": str(tmp_path / ".subtap" / "models"),
        },
    )

    app = CommandDeckApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, FirstRunScreen)
        assert load_config(config_path).asr.model == "asr_0.6b"
        assert config_path.read_text() == original


@pytest.mark.asyncio
async def test_textual_first_run_shows_invalid_field_config_without_overwrite(
    tmp_path, monkeypatch
):
    from subtap.ui.command_deck import CommandDeckApp
    from subtap.ui.textual_first_run import FirstRunScreen

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config_path = tmp_path / ".subtap" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    invalid = "asr:\n  quantization: q4\n"
    config_path.write_text(invalid)
    monkeypatch.setattr(
        "subtap.ui.views.first_run.FirstRunView.check_device", lambda self: _device()
    )

    app = CommandDeckApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        assert isinstance(app.screen, FirstRunScreen)
        assert app.screen.query_one("#download").disabled is True
        assert "配置文件读取失败" in str(app.screen.query_one("#status").render())

    assert config_path.read_text() == invalid


def test_tui_command_uses_textual_command_deck(monkeypatch):
    from typer.testing import CliRunner

    from subtap.cli import app

    calls = []
    monkeypatch.setattr(
        "subtap.ui.command_deck.CommandDeckApp.run",
        lambda self: calls.append("run"),
    )

    result = CliRunner().invoke(app, ["tui"])

    assert result.exit_code == 0
    assert calls == ["run"]
