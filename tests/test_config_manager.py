# tests/test_config_manager.py
import pytest

from subtap.ui.config_manager import ConfigManager


class TestConfigManager:
    def test_load_existing_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("mode: online\nasr:\n  model: asr_0.6b\n")
        mgr = ConfigManager(config_file)
        assert mgr.get("mode") == "online"
        assert mgr.get("asr.model") == "asr_0.6b"

    def test_load_missing_config_returns_defaults(self, tmp_path):
        mgr = ConfigManager(tmp_path / "missing.yaml")
        assert mgr.get("mode") is None

    def test_invalid_config_fails_without_overwriting_user_file(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        invalid = "asr: [broken"
        config_file.write_text(invalid, encoding="utf-8")

        with pytest.raises(RuntimeError, match="配置文件读取失败"):
            ConfigManager(config_file)

        assert config_file.read_text(encoding="utf-8") == invalid

    @pytest.mark.parametrize("invalid", ["- item\n", "scalar\n"])
    def test_non_mapping_config_fails_without_overwriting_user_file(
        self, tmp_path, invalid
    ):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(invalid, encoding="utf-8")

        with pytest.raises(RuntimeError, match="配置文件读取失败"):
            ConfigManager(config_file)

        assert config_file.read_text(encoding="utf-8") == invalid

    def test_set_and_save(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("mode: offline\n")
        mgr = ConfigManager(config_file)
        mgr.set("mode", "online")
        mgr.save()
        assert "online" in config_file.read_text()

    def test_get_nested_key(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("asr:\n  model: test\n  backend: mlx\n")
        mgr = ConfigManager(config_file)
        assert mgr.get("asr.model") == "test"
        assert mgr.get("asr.backend") == "mlx"

    def test_get_missing_key_returns_none(self, tmp_path):
        mgr = ConfigManager(tmp_path / "empty.yaml")
        assert mgr.get("nonexistent") is None
        assert mgr.get("nonexistent.key") is None

    def test_set_nested_key_creates_path(self, tmp_path):
        mgr = ConfigManager(tmp_path / "new.yaml")
        mgr.set("asr.model", "new_model")
        assert mgr.get("asr.model") == "new_model"

    def test_config_dir_created_on_save(self, tmp_path):
        config_file = tmp_path / "sub" / "config.yaml"
        mgr = ConfigManager(config_file)
        mgr.set("mode", "online")
        mgr.save()
        assert config_file.exists()
