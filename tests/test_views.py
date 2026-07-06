# tests/test_views.py
from pathlib import Path
from subtap.ui.views.new_task import NewTaskView
from subtap.ui.config_manager import ConfigManager


class TestNewTaskView:
    def test_initial_state(self, tmp_path):
        cfg = ConfigManager(tmp_path / "config.yaml")
        view = NewTaskView(config=cfg, home_dir=tmp_path)
        assert view.selected_file is None

    def test_confirm_settings_reads_config(self, tmp_path):
        cfg = ConfigManager(tmp_path / "config.yaml")
        cfg.set("output.subtitle_language", "zh")
        cfg.set("output.subtitle_formats", ["srt"])
        view = NewTaskView(config=cfg, home_dir=tmp_path)
        settings = view.get_confirm_settings()
        assert settings["language"] == "中文"
        assert settings["format"] == "SRT"

    def test_confirm_settings_default(self, tmp_path):
        cfg = ConfigManager(tmp_path / "config.yaml")
        view = NewTaskView(config=cfg, home_dir=tmp_path)
        settings = view.get_confirm_settings()
        assert settings["language"] == "自动检测"
        assert settings["format"] == "SRT"

    def test_build_run_command(self, tmp_path):
        import sys
        cfg = ConfigManager(tmp_path / "config.yaml")
        cfg.set("output.subtitle_formats", ["srt"])
        view = NewTaskView(config=cfg, home_dir=tmp_path)
        view.select_file(Path("/test/audio.mp3"))
        cmd = view.build_run_command()
        assert cmd[0] == sys.executable
        assert cmd[1] == "-m"
        assert cmd[2] == "subtap"
        assert cmd[3] == "run"
        assert "/test/audio.mp3" in cmd

    def test_build_run_command_no_file(self, tmp_path):
        cfg = ConfigManager(tmp_path / "config.yaml")
        view = NewTaskView(config=cfg, home_dir=tmp_path)
        assert view.build_run_command() == []
