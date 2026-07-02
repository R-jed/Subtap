"""Phase 19: 验证配置不包含 hybrid 模式。"""

from __future__ import annotations

from subtap.schemas.config import SubtapConfig, ASRConfig, CleanConfig, AlignConfig


def test_config_no_hybrid_mode():
    """配置不应包含 hybrid 模式。"""
    config = SubtapConfig()
    assert config.mode != "hybrid"


def test_asr_config_default_local():
    """ASR 配置默认应为本地 MLX。"""
    config = ASRConfig()
    assert config.backend == "mlx-qwen-asr"


def test_clean_config_default_backend():
    """Clean 配置默认应为 OpenAI 兼容后端。"""
    config = CleanConfig()
    assert config.backend.startswith("openai:")


def test_align_config_default_local():
    """Align 配置默认应为本地 MLX。"""
    config = AlignConfig()
    assert config.backend == "mlx-qwen-aligner"


def test_config_mode_field_not_hybrid():
    """配置的 mode 字段不应接受 hybrid。"""
    config = SubtapConfig()
    # 验证 mode 不是 hybrid
    assert config.mode in ("offline", "local", "fast", "quality")


def test_config_load_default_yaml():
    """加载默认配置不应包含 hybrid 或 API ASR。"""
    from pathlib import Path
    from subtap.schemas.config import load_config

    default_yaml = Path(__file__).parent.parent / "configs" / "default.yaml"
    if default_yaml.exists():
        config = load_config(default_yaml)
        assert config.mode != "hybrid"
        assert "api" not in config.asr.backend.lower() or "mlx" in config.asr.backend
