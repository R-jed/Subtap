"""HTTP ASR backend stub.

OpenAI-compatible POST /v1/audio/transcriptions interface.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

from subtap.schemas.config import ASRConfig, RemoteAPIConfig
from subtap.schemas.models import Chunk, ASRSegment

logger = logging.getLogger(__name__)


class HttpASRBackend:
    """HTTP ASR backend for OpenAI-compatible transcription APIs."""

    name = "http-asr"

    def __init__(self, config: ASRConfig, remote_api: RemoteAPIConfig | None = None):
        self.config = config
        self.remote_api = remote_api or RemoteAPIConfig()
        self.base_url = (
            self.remote_api.base_url or "https://api.openai.com/v1"
        ).rstrip("/")
        self.api_key = os.environ.get(self.remote_api.api_key_env, "")
        self.model = self.remote_api.model or "whisper-1"
        self.timeout_sec = self.remote_api.timeout_sec
        self.provider = self.remote_api.provider

    def transcribe(
        self,
        chunks: list[Chunk],
        language: Optional[str] = None,
        hotwords: Optional[list[str]] = None,
    ) -> list[ASRSegment]:
        """Transcribe chunks via remote API."""
        segments: list[ASRSegment] = []
        with httpx.Client(timeout=self.timeout_sec) as client:
            for chunk in chunks:
                if self.provider.startswith("anthropic"):
                    audio_b64 = base64.b64encode(Path(chunk.path).read_bytes()).decode()
                    resp = client.post(
                        f"{self.base_url}/messages",
                        headers={
                            "x-api-key": self.api_key,
                            "anthropic-version": "2023-06-01",
                        },
                        json={
                            "model": self.model,
                            "max_tokens": 4096,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": (
                                        "Transcribe this base64 audio and return text "
                                        f"only:\n{audio_b64}"
                                    ),
                                }
                            ],
                        },
                    )
                else:
                    with open(chunk.path, "rb") as audio:
                        resp = client.post(
                            f"{self.base_url}/audio/transcriptions",
                            headers={"Authorization": f"Bearer {self.api_key}"},
                            data={
                                "model": self.model,
                                "language": language or "",
                                "prompt": " ".join(hotwords or []),
                            },
                            files={
                                "file": (
                                    os.path.basename(chunk.path),
                                    audio,
                                    "audio/wav",
                                )
                            },
                        )
                resp.raise_for_status()
                data = resp.json()
                if self.provider.startswith("anthropic"):
                    text = str(data.get("content", [{}])[0].get("text", "")).strip()
                else:
                    text = str(data.get("text", "")).strip()
                segments.append(
                    ASRSegment(
                        chunk_id=chunk.chunk_id,
                        segment_id=0,
                        start_sec=chunk.start_sec,
                        end_sec=chunk.end_sec,
                        text=text,
                    )
                )
        return segments
