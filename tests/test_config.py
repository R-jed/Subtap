"""配置模型扩展测试 - 验证 LLM 功能字段。"""

from __future__ import annotations

from subtap.schemas.config import SubtapConfig


def test_subtap_config_has_llm_proofread_field():
    """SubtapConfig 应包含 llm_proofread 字段"""
    config = SubtapConfig()
    assert hasattr(config, 'llm_proofread')
    assert config.llm_proofread is None  # 默认未设置


def test_subtap_config_has_llm_hotword_field():
    """SubtapConfig 应包含 llm_hotword 字段"""
    config = SubtapConfig()
    assert hasattr(config, 'llm_hotword')
    assert config.llm_hotword is False  # 默认关闭


def test_subtap_config_translate_to_field():
    """SubtapConfig 应包含 translate_to 字段"""
    config = SubtapConfig()
    assert hasattr(config, 'translate_to')
    assert config.translate_to == ""  # 默认空值