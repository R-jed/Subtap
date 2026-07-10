"""ASR backend registry and factory."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from subtap.schemas.config import ASRConfig, RemoteAPIConfig

if TYPE_CHECKING:
    from subtap.backends.asr.base import ASRBackend


def get_backend(
    config: ASRConfig,
    remote_api: RemoteAPIConfig | None = None,
    model_root: Path | None = None,
) -> ASRBackend:
    """Instantiate an ASR backend by name."""
    if config.backend == "mlx-qwen-asr":
        from subtap.backends.asr.mlx_qwen_asr import MLXQwenASR

        return MLXQwenASR(config, model_root=model_root)
    elif config.backend == "http-asr":
        from subtap.backends.asr.http_asr import HttpASRBackend

        return HttpASRBackend(config, remote_api)
    else:
        raise ValueError(f"Unknown ASR backend: {config.backend}")
