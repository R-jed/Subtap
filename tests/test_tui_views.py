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
