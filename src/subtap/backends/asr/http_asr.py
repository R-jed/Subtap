"""HTTP ASR backend stub.

OpenAI-compatible POST /v1/audio/transcriptions interface.
"""

from __future__ import annotations

import logging
from typing import Optional

from subtap.schemas.config import ASRConfig
from subtap.schemas.models import Chunk, ASRSegment

logger = logging.getLogger(__name__)


class HttpASRBackend:
    """Stub HTTP ASR backend for future OpenAI-compatible API integration."""

    name = "http-asr"

    def __init__(self, config: ASRConfig):
        self.config = config

    def transcribe(
        self,
        chunks: list[Chunk],
        language: Optional[str] = None,
        hotwords: Optional[list[str]] = None,
    ) -> list[ASRSegment]:
        """Transcribe chunks via HTTP API (stub).

        Future implementation will POST each chunk's WAV to
        POST /v1/audio/transcriptions with multipart/form-data.

        Raises:
            NotImplementedError: Always, until real implementation.
        """
        raise NotImplementedError(
            "HttpASRBackend is a stub. "
            "Implement POST /v1/audio/transcriptions integration."
        )
