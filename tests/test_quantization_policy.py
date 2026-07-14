"""Phase 22: model and quantization policy."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from subtap.backends.asr.mlx_qwen_asr import MLXQwenASR
from subtap.backends.align.mlx_qwen_align import MLXQwenAligner
from subtap.schemas.config import ASRConfig, AlignConfig


def test_asr_backend_uses_configured_model_and_quantization():
    """MLX ASR backend should expose configured model identity."""
    backend = MLXQwenASR(ASRConfig(model="asr_1.7b", quantization="q8"))

    assert backend.model_name == "asr_1.7b"
    assert backend.quantization == "q8"
    assert backend.runtime_name == "qwen3-asr-1.7b-q8"


def test_qwen_configs_default_to_q8():
    assert ASRConfig().quantization == "q8"
    assert AlignConfig().quantization == "q8"


@pytest.mark.parametrize("config_type", [ASRConfig, AlignConfig])
@pytest.mark.parametrize("quantization", ["q4", "f16"])
def test_qwen_configs_reject_non_q8_quantization(config_type, quantization):
    with pytest.raises(ValidationError):
        config_type(quantization=quantization)


def test_aligner_backend_exposes_quantization():
    """Aligner backend should expose configured quantization."""
    backend = MLXQwenAligner(AlignConfig(model="aligner", quantization="q8"))

    assert backend.model_name == "aligner"
    assert backend.quantization == "q8"
    assert backend.runtime_name == "qwen3-forcedaligner-q8"
