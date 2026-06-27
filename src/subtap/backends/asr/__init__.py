"""ASR backend registry and factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from subtap.schemas.config import ASRConfig

if TYPE_CHECKING:
    from subtap.backends.asr.base import ASRBackend


def get_backend(config: ASRConfig) -> ASRBackend:
    """Instantiate an ASR backend by name."""
    if config.backend == "mlx-qwen-asr":
        from subtap.backends.asr.mlx_qwen_asr import MLXQwenASR

        return MLXQwenASR(config)
    elif config.backend == "http-asr":
        from subtap.backends.asr.http_asr import HttpASRBackend

        return HttpASRBackend(config)
    else:
        raise ValueError(f"Unknown ASR backend: {config.backend}")
