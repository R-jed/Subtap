"""配置模型扩展测试 - 验证 LLM 功能字段。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

from subtap.schemas.config import SubtapConfig, load_config


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
