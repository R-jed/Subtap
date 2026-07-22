"""配置模型扩展测试 - 验证 LLM 功能字段。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

from subtap.schemas.config import (
    OutputConfig,
    SubtapConfig,
    load_config,
)


def test_subtap_config_has_llm_proofread_field():
    """SubtapConfig 应包含 llm_proofread 字段"""
    config = SubtapConfig()
    assert config.llm_proofread is None  # 默认未设置


def test_subtap_config_has_llm_hotword_field():
    """SubtapConfig 应包含 llm_hotword 字段"""
    config = SubtapConfig()
    assert config.llm_hotword is False  # 默认关闭


def test_subtap_config_translate_to_field():
    """SubtapConfig 应包含 translate_to 字段"""
    config = SubtapConfig()
    assert config.translate_to == ""  # 默认空值


def test_output_config_exposes_only_maximum_character_limit():
    output = OutputConfig(max_chars=15)

    assert output.max_chars == 15
    assert "min_chars" not in OutputConfig.model_fields


def test_load_config_reports_removed_minimum_character_limit(tmp_path, caplog):
    path = tmp_path / "config.yaml"
    path.write_text("output:\n  max_chars: 30\n  min_chars: 10\n", encoding="utf-8")

    config = load_config(path)

    assert config.output.max_chars == 30
    assert "output.min_chars=10" in caplog.text


def test_config_load_round_trip():
    """从 YAML 加载配置后字段值正确"""
    config_data = {"llm_proofread": True, "llm_hotword": True, "translate_to": "zh"}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        config = load_config(Path(temp_path))
        assert config.llm_proofread is True
        assert config.llm_hotword is True
        assert config.translate_to == "zh"
    finally:
        os.unlink(temp_path)


def test_load_config_migrates_removed_vad_chunk_limit(tmp_path: Path, caplog):
    """Old config remains loadable but reports that mechanical splitting is gone."""
    path = tmp_path / "config.yaml"
    path.write_text("audio:\n  vad:\n    max_chunk_sec: 30\n", encoding="utf-8")

    config = load_config(path)

    assert not hasattr(config.audio.vad, "max_chunk_sec")
    assert "max_chunk_sec=30" in caplog.text
