"""Tests for batch config management."""

from __future__ import annotations


from subtap.batch_config import (
    BatchConfig,
    load_batch_config,
    save_batch_config,
)


class TestBatchConfig:
    """Test BatchConfig class."""

    def test_default_config(self):
        config = BatchConfig()
        assert config.mode is None
        assert config.enhance == "local"
        assert config.translate_to is None
        assert config.bilingual == "off"
        assert config.max_chars == 25
        assert config.punctuation is False
        assert config.subtitle_language == "zh"

    def test_config_from_dict(self):
        data = {
            "mode": "quality",
            "enhance": "api",
            "translate_to": "en",
            "bilingual": "source-first",
            "max_chars": 30,
            "punctuation": True,
            "subtitle_language": "en",
        }
        config = BatchConfig.from_dict(data)
        assert config.mode == "quality"
        assert config.enhance == "api"
        assert config.translate_to == "en"
        assert config.bilingual == "source-first"
        assert config.max_chars == 30
        assert config.punctuation is True
        assert config.subtitle_language == "en"

    def test_config_to_dict(self):
        config = BatchConfig(mode="quality", enhance="api")
        data = config.to_dict()
        assert data["mode"] == "quality"
        assert data["enhance"] == "api"
        assert "translate_to" in data
        assert "bilingual" in data

    def test_config_defaults(self):
        data = {"mode": "quality"}
        config = BatchConfig.from_dict(data)
        assert config.mode == "quality"
        assert config.enhance == "local"  # default


class TestLoadSaveConfig:
    """Test load and save functions."""

    def test_save_and_load(self, tmp_path):
        config_path = tmp_path / "batch-config.yaml"
        config = BatchConfig(mode="quality", translate_to="en")
        save_batch_config(config, config_path)

        loaded = load_batch_config(config_path)
        assert loaded.mode == "quality"
        assert loaded.translate_to == "en"

    def test_load_nonexistent(self, tmp_path):
        config_path = tmp_path / "nonexistent.yaml"
        config = load_batch_config(config_path)
        assert config.mode is None

    def test_load_invalid_yaml(self, tmp_path):
        config_path = tmp_path / "invalid.yaml"
        config_path.write_text("invalid: yaml: content: [")
        config = load_batch_config(config_path)
        assert config.mode is None
