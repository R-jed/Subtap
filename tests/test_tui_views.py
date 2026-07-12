"""Tests for TUI view components."""

from __future__ import annotations


def test_status_bar_check_models_installed(tmp_path, monkeypatch):
    from subtap.ui.views.status_bar import StatusBar

    # Create minimal config so load_config succeeds
    subtap = tmp_path / ".subtap"
    subtap.mkdir(parents=True)
    (subtap / "config.yaml").write_text("models:\n  asr: asr_1.7b\n")

    # Mock ModelRegistry at its source module
    monkeypatch.setattr(
        "subtap.core.models.ModelRegistry",
        lambda config: type(
            "R",
            (),
            {
                "status": lambda self: [
                    type("S", (), {"name": "asr_1.7b", "installed": True})(),
                    type("S", (), {"name": "aligner", "installed": True})(),
                ]
            },
        )(),
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    bar = StatusBar()
    result = bar.check_models()
    assert result["all_ready"] is True
    assert result["installed_count"] == 2


def test_status_bar_check_models_failure(tmp_path, monkeypatch):
    from subtap.ui.views.status_bar import StatusBar

    # No config.yaml → load_config returns None → early return
    subtap = tmp_path / ".subtap"
    subtap.mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    bar = StatusBar()
    result = bar.check_models()
    assert result["all_ready"] is False
    assert result["installed_count"] == 0
    assert result["total"] == 0


def test_status_bar_check_models_registry_exception(tmp_path, monkeypatch):
    from subtap.ui.views.status_bar import StatusBar

    subtap = tmp_path / ".subtap"
    subtap.mkdir(parents=True)
    (subtap / "config.yaml").write_text("models:\n  asr: asr_1.7b\n")

    # ModelRegistry raises → except branch
    def boom(config):
        raise RuntimeError("registry exploded")

    monkeypatch.setattr("subtap.core.models.ModelRegistry", boom)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    bar = StatusBar()
    result = bar.check_models()
    assert result["all_ready"] is False
    assert result["installed_count"] == 0
    assert result["total"] == 0


def test_status_bar_check_disk(tmp_path, monkeypatch):
    from subtap.ui.views.status_bar import StatusBar

    subtap = tmp_path / ".subtap"
    subtap.mkdir()
    (subtap / "models").mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    bar = StatusBar()
    result = bar.check_disk()
    assert result["used_bytes"] == 0
    assert result["free_bytes"] > 0


def test_status_bar_check_pending_jobs(tmp_path, monkeypatch):
    from subtap.ui.views.status_bar import StatusBar

    jobs = tmp_path / ".subtap" / "jobs"
    jobs.mkdir(parents=True)
    (jobs / "task-001").mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    bar = StatusBar()
    assert bar.check_pending_jobs() == 1


def test_status_bar_render_returns_lines():
    from subtap.ui.views.status_bar import StatusBar

    bar = StatusBar()
    lines = bar.render()
    assert len(lines) == 3
    assert all(isinstance(line, str) for line in lines)


def test_home_view_builds_menu_items():
    from subtap.ui.views.home import HomeView

    view = HomeView()
    items = view.build_menu_items()
    assert len(items) >= 6
    assert any("新建字幕" in item for item in items)
    assert any("最近任务" in item for item in items)
    assert any("模型管理" in item for item in items)
    assert any("热词库" in item for item in items)
    assert any("文稿库" in item for item in items)
    assert any("设置" in item for item in items)


def test_home_view_detects_first_run(tmp_path, monkeypatch):
    from subtap.ui.views.home import HomeView

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    view = HomeView()
    assert view.is_first_run() is True


def test_home_view_not_first_run(tmp_path, monkeypatch):
    from subtap.ui.views.home import HomeView
    from subtap.core.state_store import StateStore

    subtap = tmp_path / ".subtap"
    subtap.mkdir()
    StateStore(subtap / "state.json").load()  # creates file
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    view = HomeView()
    assert view.is_first_run() is False


# --- FirstRunView tests ---

def test_first_run_view_checks_device():
    from subtap.ui.views.first_run import FirstRunView

    view = FirstRunView()
    result = view.check_device()
    assert "is_apple_silicon" in result
    assert "has_ffmpeg" in result


def test_first_run_view_recommends_model():
    from subtap.ui.views.first_run import FirstRunView

    view = FirstRunView()
    recommendation = view.recommend_model(fast_ok=True, quality_ok=True)
    assert recommendation in ("asr_0.6b", "asr_1.7b")


def test_first_run_view_recommends_fast_when_low_disk():
    from subtap.ui.views.first_run import FirstRunView

    view = FirstRunView()
    recommendation = view.recommend_model(fast_ok=True, quality_ok=False)
    assert recommendation == "asr_0.6b"


def test_first_run_view_recommends_raises_when_both_false():
    from subtap.ui.views.first_run import FirstRunView

    view = FirstRunView()
    import pytest

    with pytest.raises(ValueError, match="fast_ok 和 quality_ok 均为 False"):
        view.recommend_model(fast_ok=False, quality_ok=False)


def test_first_run_view_get_download_info():
    from subtap.ui.views.first_run import FirstRunView

    view = FirstRunView()
    info = view.get_download_info("asr_0.6b")
    assert "model_name" in info
    assert "size_bytes" in info
    assert "size_display" in info
    assert info["model_name"] == "asr_0.6b"


def test_first_run_view_mark_complete(tmp_path, monkeypatch):
    from subtap.ui.views.first_run import FirstRunView

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    view = FirstRunView()
    state_path = view.mark_complete()
    assert state_path == tmp_path / ".subtap" / "state.json"
    assert state_path.suffix == ".json"


# --- WizardView tests ---

def test_wizard_view_initializes_with_defaults():
    from subtap.ui.views.wizard import WizardView

    view = WizardView()
    state = view.get_state()
    assert state["step"] == 0
    assert state["quality"] is None
    assert state["file_path"] is None


def test_wizard_view_select_quality():
    from subtap.ui.views.wizard import WizardView

    view = WizardView()
    view.select_quality("fast")
    assert view.get_state()["quality"] == "fast"


def test_wizard_view_build_command(tmp_path):
    from subtap.ui.views.wizard import WizardView

    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"fake")
    view = WizardView()
    view.select_file(audio)
    view.select_quality("fast")
    cmd = view.build_run_command()
    assert str(audio) in cmd
    assert "--format" in cmd or "run" in cmd


def test_wizard_view_next_prev_step():
    from subtap.ui.views.wizard import WizardView

    view = WizardView()
    assert view.get_state()["step"] == 0
    view.next_step()
    assert view.get_state()["step"] == 1
    view.prev_step()
    assert view.get_state()["step"] == 0


def test_wizard_view_prev_step_clamps_at_zero():
    from subtap.ui.views.wizard import WizardView

    view = WizardView()
    view.prev_step()
    assert view.get_state()["step"] == 0


def test_wizard_view_next_step_clamps_at_max():
    from subtap.ui.views.wizard import WizardView

    view = WizardView()
    for _ in range(20):
        view.next_step()
    assert view.get_state()["step"] == len(WizardView.STEPS) - 1


def test_wizard_view_select_glossary():
    from subtap.ui.views.wizard import WizardView

    view = WizardView()
    view.select_glossary("my_glossary")
    assert view.get_state()["glossary_name"] == "my_glossary"


def test_wizard_view_select_manuscript():
    from subtap.ui.views.wizard import WizardView

    view = WizardView()
    view.select_manuscript("my_manuscript")
    assert view.get_state()["manuscript_name"] == "my_manuscript"


def test_wizard_view_select_output_dir():
    from subtap.ui.views.wizard import WizardView

    view = WizardView()
    view.select_output_dir("/tmp/output")
    assert view.get_state()["output_dir"] == "/tmp/output"


def test_wizard_view_is_complete():
    from subtap.ui.views.wizard import WizardView

    view = WizardView()
    assert view.is_complete() is False

    view.select_file("/tmp/test.mp3")
    assert view.is_complete() is False  # quality not set

    view.select_quality("fast")
    assert view.is_complete() is True


def test_wizard_view_get_confirm_items():
    from subtap.ui.views.wizard import WizardView

    view = WizardView()
    view.select_file("/tmp/test.mp3")
    view.select_quality("fast")
    items = view.get_confirm_items()
    assert len(items) >= 3
    assert any("test.mp3" in item for item in items)
    assert any("快速" in item for item in items)


def test_wizard_view_steps_count():
    from subtap.ui.views.wizard import WizardView

    assert len(WizardView.STEPS) == 6
