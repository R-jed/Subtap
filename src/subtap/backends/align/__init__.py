"""Aligner backend registry and factory."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from subtap.schemas.config import AlignConfig

if TYPE_CHECKING:
    from subtap.backends.align.base import AlignerBackend


def get_aligner_backend(
    config: AlignConfig, model_root: Path | None = None
) -> AlignerBackend:
    """Instantiate an aligner backend by name."""
    if config.backend == "mlx-qwen-aligner":
        from subtap.backends.align.mlx_qwen_align import MLXQwenAligner

        return MLXQwenAligner(config, model_root=model_root)
    elif config.backend == "mock-aligner":
        from subtap.backends.align.mock import MockAligner

        return MockAligner(config)
    else:
        raise ValueError(f"Unknown aligner backend: {config.backend}")
