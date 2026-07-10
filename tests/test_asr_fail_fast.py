"""ASR backend fail-fast behavior."""

from __future__ import annotations

import pytest

from subtap.backends.asr.mlx_qwen_asr import MLXQwenASR
from subtap.schemas.config import ASRConfig
from subtap.schemas.models import Chunk


def test_mlx_asr_missing_chunk_fails_fast(tmp_path):
    backend = MLXQwenASR(ASRConfig(), model_root=tmp_path / "models")
    backend._model = object()
    missing = tmp_path / "missing.wav"
    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=1.0, path=str(missing))

    with pytest.raises(FileNotFoundError, match="ASR chunk file not found"):
        backend.transcribe([chunk])
