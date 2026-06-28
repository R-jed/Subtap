"""Phase 22: model and quantization policy."""

from __future__ import annotations

from subtap.backends.asr.mlx_qwen_asr import MLXQwenASR
from subtap.backends.align.mlx_qwen_align import MLXQwenAligner
from subtap.schemas.config import ASRConfig, AlignConfig


def test_asr_backend_uses_configured_model_and_quantization():
    """MLX ASR backend should expose configured model identity."""
    backend = MLXQwenASR(ASRConfig(model="asr_1.7b", quantization="q8"))

    assert backend.model_name == "asr_1.7b"
    assert backend.quantization == "q8"
    assert backend.runtime_name == "qwen3-asr-1.7b-q8"


def test_low_memory_policy_is_q4_0_6b():
    """Low-memory config should be expressible as 0.6B q4."""
    backend = MLXQwenASR(ASRConfig(model="asr_0.6b", quantization="q4"))

    assert backend.runtime_name == "qwen3-asr-0.6b-q4"


def test_aligner_backend_exposes_quantization():
    """Aligner backend should expose configured quantization."""
    backend = MLXQwenAligner(AlignConfig(model="aligner", quantization="q8"))

    assert backend.model_name == "aligner"
    assert backend.quantization == "q8"
    assert backend.runtime_name == "qwen3-forcedaligner-q8"
