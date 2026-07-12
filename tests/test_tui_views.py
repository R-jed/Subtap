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


def test_wizard_view_build_command_includes_output_dir(tmp_path, monkeypatch):
    from subtap.ui.views.wizard import WizardView

    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"fake")
    out_dir = tmp_path / "my_output"
    out_dir.mkdir()
    view = WizardView()
    view.select_file(audio)
    view.select_quality("fast")
    view.select_output_dir(out_dir)
    cmd = view.build_run_command()
    assert "--output-dir" in cmd
    assert str(out_dir) in cmd


def test_wizard_view_build_command_includes_glossary(tmp_path, monkeypatch):
    from subtap.ui.views.wizard import WizardView

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    glossary_dir = tmp_path / ".subtap" / "glossary"
    glossary_dir.mkdir(parents=True)
    (glossary_dir / "my_terms.yaml").write_text("terms: []")

    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"fake")
    view = WizardView()
    view.select_file(audio)
    view.select_quality("fast")
    view.select_glossary(glossary_dir / "my_terms.yaml")
    cmd = view.build_run_command()
    assert "--glossary" in cmd
    assert str(glossary_dir / "my_terms.yaml") in cmd


def test_wizard_view_build_command_includes_manuscript(tmp_path, monkeypatch):
    from subtap.ui.views.wizard import WizardView

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    ms_dir = tmp_path / ".subtap" / "manuscripts"
    ms_dir.mkdir(parents=True)
    (ms_dir / "draft.txt").write_text("hello")

    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"fake")
    view = WizardView()
    view.select_file(audio)
    view.select_quality("fast")
    view.select_manuscript(ms_dir / "draft.txt")
    cmd = view.build_run_command()
    assert "--script" in cmd
    assert str(ms_dir / "draft.txt") in cmd


def test_wizard_view_list_glossaries(tmp_path, monkeypatch):
    from subtap.ui.views.wizard import WizardView

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    glossary_dir = tmp_path / ".subtap" / "glossary"
    glossary_dir.mkdir(parents=True)
    (glossary_dir / "a.yaml").write_text("")
    (glossary_dir / "b.txt").write_text("")
    (glossary_dir / "c.md").write_text("")  # not a supported suffix

    result = WizardView.list_glossaries()
    names = [p.stem for p in result]
    assert "a" in names
    assert "b" in names
    assert "c" not in names


def test_wizard_view_list_manuscripts(tmp_path, monkeypatch):
    from subtap.ui.views.wizard import WizardView

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    ms_dir = tmp_path / ".subtap" / "manuscripts"
    ms_dir.mkdir(parents=True)
    (ms_dir / "doc1.txt").write_text("")
    (ms_dir / "doc2.md").write_text("")
    (ms_dir / "doc3.pdf").write_text("")  # not a supported suffix

    result = WizardView.list_manuscripts()
    names = [p.stem for p in result]
    assert "doc1" in names
    assert "doc2" in names
    assert "doc3" not in names


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
    from pathlib import Path

    from subtap.ui.views.wizard import WizardView

    view = WizardView()
    p = Path("/tmp/my_glossary.yaml")
    view.select_glossary(p)
    assert view.get_state()["glossary_path"] == p


def test_wizard_view_select_manuscript():
    from pathlib import Path

    from subtap.ui.views.wizard import WizardView

    view = WizardView()
    p = Path("/tmp/my_manuscript.txt")
    view.select_manuscript(p)
    assert view.get_state()["manuscript_path"] == p


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


# --- ModelsPage tests ---


def test_models_page_builds_items():
    from subtap.ui.views.models_page import ModelsPage

    page = ModelsPage()
    items = page.build_model_items([
        type("S", (), {"name": "asr_1.7b", "installed": True, "path": "/m", "missing_files": []})(),
        type("S", (), {"name": "aligner", "installed": False, "path": "/m", "missing_files": ["config.json"]})(),
    ])
    assert len(items) == 2
    assert "✓" in items[0]
    assert "✗" in items[1]


def test_models_page_action_install():
    from subtap.ui.views.models_page import ModelsPage

    page = ModelsPage()
    actions = page.get_actions(installed=False)
    assert "安装" in actions
    assert "删除" not in actions


def test_models_page_action_delete():
    from subtap.ui.views.models_page import ModelsPage

    page = ModelsPage()
    actions = page.get_actions(installed=True)
    assert "删除" in actions
    assert "安装" not in actions


# --- GlossaryPage tests ---


def test_glossary_page_builds_items():
    from subtap.ui.views.glossary_page import GlossaryPage

    page = GlossaryPage()
    items = page.build_glossary_items([
        type("H", (), {"word": "理光", "aliases": ["李光", "理广"]})(),
        type("H", (), {"word": "VITURE", "aliases": ["维图尔"]})(),
    ])
    assert len(items) == 2
    assert "理光" in items[0]


def test_glossary_page_empty():
    from subtap.ui.views.glossary_page import GlossaryPage

    page = GlossaryPage()
    items = page.build_glossary_items([])
    assert len(items) == 1
    assert "暂无" in items[0]


def test_glossary_page_get_actions():
    from subtap.ui.views.glossary_page import GlossaryPage

    page = GlossaryPage()
    actions = page.get_actions()
    assert "添加 (A)" in actions
    assert "删除 (D)" in actions
    assert "编辑 (E)" in actions
    assert "返回 (Esc)" in actions


# --- ManuscriptsPage tests ---


def test_manuscripts_page_builds_items():
    from subtap.ui.views.manuscripts_page import ManuscriptsPage

    page = ManuscriptsPage()
    items = page.build_items([
        {"name": "讲稿.docx", "path": "/test/讲稿.docx", "exists": True, "recent_use_time": None},
        {"name": "旧稿.txt", "path": "/test/旧稿.txt", "exists": False, "recent_use_time": None},
    ])
    assert len(items) == 2
    assert "✓" in items[0]
    assert "✗" in items[1]


def test_manuscripts_page_empty():
    from subtap.ui.views.manuscripts_page import ManuscriptsPage

    page = ManuscriptsPage()
    items = page.build_items([])
    assert len(items) == 1
    assert "暂无" in items[0]


def test_manuscripts_page_get_actions():
    from subtap.ui.views.manuscripts_page import ManuscriptsPage

    page = ManuscriptsPage()
    actions = page.get_actions()
    assert "添加" in actions[0]
    assert "删除" in actions[1]
    assert "返回" in actions[2]


# --- RecentTasksPage tests ---


def test_recent_tasks_page_builds_items():
    from subtap.ui.views.recent_tasks import RecentTasksPage

    page = RecentTasksPage()
    items = page.build_items([
        {"task_id": "task-001", "input_name": "视频.srt", "output_path": "/out/final.srt", "time": "2026-07-12T10:00:00"},
    ])
    assert len(items) == 1
    assert "task-001" in items[0] or "视频" in items[0]


def test_recent_tasks_page_empty():
    from subtap.ui.views.recent_tasks import RecentTasksPage

    page = RecentTasksPage()
    items = page.build_items([])
    assert len(items) == 1
    assert "暂无" in items[0]


def test_recent_tasks_page_get_actions():
    from subtap.ui.views.recent_tasks import RecentTasksPage

    page = RecentTasksPage()
    actions = page.get_actions()
    assert any("查看" in a for a in actions)
    assert any("返回" in a for a in actions)


# --- CompletionPage tests ---


def test_completion_page_builds_items():
    from subtap.ui.views.completion import CompletionPage

    page = CompletionPage()
    items = page.build_items(
        output_path="/output/final.srt",
        duration_sec=120,
    )
    assert len(items) >= 4
    assert any("打开字幕" in item for item in items)
    assert any("输出目录" in item for item in items)


def test_completion_page_format_duration():
    from subtap.ui.views.completion import CompletionPage

    page = CompletionPage()
    assert page.format_duration(65) == "1 分 5 秒"
    assert page.format_duration(30) == "30 秒"
    assert page.format_duration(3661) == "61 分 1 秒"


def test_completion_page_get_actions():
    from subtap.ui.views.completion import CompletionPage

    page = CompletionPage()
    actions = page.get_actions()
    assert len(actions) == 5
    assert "打开字幕" in actions
    assert "打开输出目录" in actions
    assert "重新生成" in actions
    assert "处理另一个文件" in actions
    assert "返回" in actions


def test_completion_page_format_duration_zero():
    from subtap.ui.views.completion import CompletionPage

    page = CompletionPage()
    assert page.format_duration(0) == "0 秒"


def test_completion_page_format_duration_exact_minute():
    from subtap.ui.views.completion import CompletionPage

    page = CompletionPage()
    assert page.format_duration(60) == "1 分 0 秒"


def test_tui_app_render_and_read_has_completion_state():
    """Verify completion state is routed in _render_and_read."""
    import inspect
    from subtap.ui.tui_app import TuiApp

    source = inspect.getsource(TuiApp._render_and_read)
    assert "completion" in source
