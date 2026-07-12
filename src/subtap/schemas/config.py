"""Pydantic v2 config schema with default merge."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class VADConfig(BaseModel):
    """VAD / silence splitting parameters."""

    # 用户配置：灵敏度（唯一用户可调参数）
    sensitivity: str = "normal"  # low/normal/high

    # VAD 引擎选择
    use_silero_vad: bool = True  # True=Silero VAD, False=pydub detect_nonsilent

    # Silero VAD 参数（可通过配置调整）
    silero_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Silero VAD 语音检测阈值（越高越严格）",
    )
    silero_min_speech_duration_ms: int = Field(
        default=250,
        ge=0,
        description="Silero VAD 最短语音段时长（ms）",
    )

    # 内部参数（用户无需关心）
    min_silence_sec: float = 0.4
    min_chunk_sec: float = 1.0
    max_chunk_sec: float = 30.0


class AudioConfig(BaseModel):
    """Audio extraction and processing settings."""

    sample_rate: int = 16000
    channels: int = 1
    vad: VADConfig = Field(default_factory=VADConfig)


class ASRConfig(BaseModel):
    """ASR backend configuration."""

    backend: str = "mlx-qwen-asr"
    model: str = "asr_0.6b"
    quantization: str = "q8"
    keep_model_alive: bool = False
    hotwords: list[str] = Field(default_factory=list)


class CleanConfig(BaseModel):
    """Text cleaning / LLM backend configuration."""

    backend: str = (
        "openai:gpt-4o-mini"  # 内部固定，用户无需配置；实际模型由 remote_api.model 决定
    )
    glossary_path: str | None = None
    style_rules: list[str] = Field(default_factory=list)


class AlignConfig(BaseModel):
    """Forced alignment backend configuration."""

    backend: str = "mlx-qwen-aligner"
    model: str = "aligner"
    quantization: str = "q8"
    keep_model_alive: bool = False
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
    batch_size: int = 50


class ModelConfig(BaseModel):
    """Model management configuration."""

    root: str = "models"
    hf_endpoint: str = "https://huggingface.co"
    hf_mirror_endpoint: str = "https://hf-mirror.com"


class CleanupConfig(BaseModel):
    """清理策略配置。"""

    auto_cleanup: bool = Field(
        default=True,
        description="执行完成后自动清理临时文件（L1）",
    )
    keep_chunks: bool = Field(
        default=False,
        description="保留 chunk WAV 文件（不推荐，会占用大量磁盘空间）",
    )


class WorkspaceConfig(BaseModel):
    """Workspace directory settings."""

    root: str = "./work"


class OutputConfig(BaseModel):
    """Output system configuration."""

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
    max_chars: int = Field(
        default=25,
        description="每行字幕最大字符数（中文字符计1）",
        ge=10,
        le=60,
    )
    min_chars: int = Field(
        default=10,
        description="每行字幕最小字符数（低于此值不做停顿断句）",
        ge=4,
        le=30,
    )

    @model_validator(mode="after")
    def validate_character_limits(self):
        if self.min_chars > self.max_chars:
            raise ValueError("min_chars 不能大于 max_chars")
        return self

    subtitle_formats: set[str] = Field(
        default={"srt"},
        description="输出字幕格式（srt/vtt/json/tsv）",
    )
    subtitle_stem: str = Field(
        default="final",
        description="输出文件名前缀（不含扩展名）",
    )
    script_path: str | None = Field(
        default=None,
        description="文稿文件路径（可选），启用文稿匹配",
    )
    script_mode: str = Field(
        default="follow_script",
        description="文稿匹配模式：follow_script | correct_only",
    )


def with_output_character_limits(
    output: object, *, max_chars: int | None, min_chars: int | None
) -> OutputConfig:
    values = {
        name: getattr(output, name)
        for name in OutputConfig.model_fields
        if hasattr(output, name)
    }
    if max_chars is not None:
        values["max_chars"] = max_chars
    if min_chars is not None:
        values["min_chars"] = min_chars
    return OutputConfig.model_validate(values)


class MetricsConfig(BaseModel):
    """性能指标配置。"""

    output_path: str = "metrics.json"


class SubtapConfig(BaseModel):
    """Root configuration for Subtap."""

    model_config = ConfigDict(extra="ignore")

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
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)

    # LLM 功能配置
    llm_proofread: bool | None = Field(
        default=None, description="AI 校对开关（None=未设置，首次接入向导开启）"
    )
    llm_hotword: bool = Field(default=False, description="AI 热词替换开关（默认关闭）")
    translate_to: str = Field(
        default="", description="AI 翻译目标语言（空值表示不翻译）"
    )


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "default.yaml"


def load_config(config_path: Optional[Path] = None) -> SubtapConfig:
    """Load config from YAML, merging with defaults.

    Priority: user config overrides defaults for any specified keys.
    """
    defaults = SubtapConfig()

    if config_path and config_path.exists():
        with open(config_path) as f:
            result = yaml.safe_load(f)
            user_data = result if isinstance(result, dict) else {}
        return SubtapConfig.model_validate(user_data)

    return defaults
