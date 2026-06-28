"""Pydantic v2 config schema with default merge."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class VADConfig(BaseModel):
    """VAD / silence splitting parameters."""

    min_silence_sec: float = 0.4
    min_chunk_sec: float = 1.0
    max_chunk_sec: float = 30.0


class AudioConfig(BaseModel):
    """Audio extraction and processing settings."""

    sample_rate: int = 16000
    channels: int = 1
    format: str = "wav"
    vad: VADConfig = Field(default_factory=VADConfig)


class ASRConfig(BaseModel):
    """ASR backend configuration."""

    backend: str = "mlx-qwen-asr"
    model: str = "asr_0.6b"
    quantization: str = "q8"
    keep_model_alive: bool = False
    warmup: bool = False
    hotwords: list[str] = Field(default_factory=list)
    batch_size: int = 4


class CleanConfig(BaseModel):
    """Text cleaning / LLM backend configuration."""

    backend: str = "ollama:qwen3-coder"
    glossary_path: str | None = None
    style_rules: list[str] = Field(default_factory=list)


class AlignConfig(BaseModel):
    """Forced alignment backend configuration."""

    backend: str = "mlx-qwen-aligner"
    model: str = "aligner"
    quantization: str = "q8"
    keep_model_alive: bool = False
    warmup: bool = False
    language: str = Field(
        default="Chinese",
        description="对齐语言（Chinese/English/Japanese/Korean）",
    )
    time_offset_sec: float = Field(
        default=-0.15,
        description="对齐时间偏移（秒），负值=提前，用于补偿模型系统性延迟",
    )


class RemoteAPIConfig(BaseModel):
    """Optional remote API backend configuration."""

    provider: str = "openai-compatible"
    base_url: str = ""
    api_key_env: str = "SUBTAP_API_KEY"
    model: str = ""
    timeout_sec: int = 60


class ModelConfig(BaseModel):
    """Model management configuration."""

    root: str = "models"
    auto_download: bool = False
    hf_endpoint: str = "https://huggingface.co"
    hf_mirror_endpoint: str = "https://hf-mirror.com"


class WorkspaceConfig(BaseModel):
    """Workspace directory settings."""

    root: str = "./work"
    keep_intermediate: bool = True


class OutputConfig(BaseModel):
    """Output system configuration."""

    keep_versions: int = 5
    generate_report: bool = True
    generate_metrics: bool = True
    timestamp: bool = True
    subtitle_punctuation: bool = Field(
        default=False,
        description="字幕是否带标点符号（默认不带）",
    )
    subtitle_language: str = Field(
        default="zh",
        description="字幕输出语种（zh/en/ja），影响标点全角/半角规范",
    )


class MetricsConfig(BaseModel):
    """性能指标配置。"""

    enabled: bool = True
    slow_threshold: float = 1.5
    output_path: str = "performance.json"


class SubtapConfig(BaseModel):
    """Root configuration for Subtap."""

    mode: str = "offline"
    audio: AudioConfig = Field(default_factory=AudioConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    clean: CleanConfig = Field(default_factory=CleanConfig)
    align: AlignConfig = Field(default_factory=AlignConfig)
    remote_api: RemoteAPIConfig = Field(default_factory=RemoteAPIConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "default.yaml"


def load_config(config_path: Optional[Path] = None) -> SubtapConfig:
    """Load config from YAML, merging with defaults.

    Priority: user config overrides defaults for any specified keys.
    """
    defaults = SubtapConfig()

    if config_path and config_path.exists():
        with open(config_path) as f:
            user_data = yaml.safe_load(f) or {}
        return SubtapConfig.model_validate(user_data)

    return defaults
