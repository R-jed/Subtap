"""MLX Qwen ASR backend implementation.

Uses mlx_audio.stt.generate_transcription for speech-to-text.
"""

from __future__ import annotations

import logging
from pathlib import Path

from subtap.schemas.config import ASRConfig
from subtap.schemas.models import Chunk, ASRSegment

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ROOT = Path.home() / ".subtap" / "models"


class MLXQwenASR:
    """ASR backend using mlx_audio STT."""

    name = "mlx-qwen-asr"

    def __init__(self, config: ASRConfig, model_root: Path | None = None):
        self.config = config
        self.model_name = config.model
        self.quantization = config.quantization
        self.runtime_name = (
            f"qwen3-asr-{self.model_name.replace('asr_', '')}-{self.quantization}"
        )
        self._model = None
        root = model_root or DEFAULT_MODEL_ROOT
        model_subdir = "asr_1.7b" if self.model_name == "asr_1.7b" else "asr_0.6b"
        self._model_path = str(root / model_subdir)

    def release_model(self) -> None:
        """Release the in-memory MLX model after the ASR stage."""
        self._model = None

    def _load_model(self):
        """Lazy-load the MLX STT model."""
        if self._model is not None:
            return
        try:
            from mlx_audio.stt.generate import load_model

            logger.info("Loading ASR model from: %s", self._model_path)
            self._model = load_model(self._model_path)
            logger.info("ASR model loaded successfully")
        except ImportError:
            raise ImportError(
                "mlx_audio is required for MLX Qwen ASR. "
                "Install: pip install mlx-audio"
            )

    def load_model(self) -> None:
        """Load the model explicitly so pipeline metrics can time it."""
        self._load_model()

    def _build_hotword_prompt(self, hotwords: list[str]) -> str | None:
        """Build system_prompt from hotword list for ASR attention biasing."""
        if not hotwords:
            return None
        word_list = "、".join(hotwords)
        return f"请注意以下专业术语和人名：{word_list}"

    def transcribe(
        self,
        chunks: list[Chunk],
        language: str | None = None,
        hotwords: list[str] | None = None,
    ) -> list[ASRSegment]:
        """Transcribe chunks sequentially using MLX STT."""
        self._load_model()
        segments: list[ASRSegment] = []
        system_prompt = self._build_hotword_prompt(hotwords or [])
        if system_prompt:
            logger.info("Hotword injection enabled: %s", system_prompt)

        for chunk in chunks:
            audio_path = Path(chunk.path)
            if not audio_path.is_absolute():
                audio_path = Path.cwd() / audio_path

            if not audio_path.exists():
                raise FileNotFoundError(f"ASR chunk file not found: {audio_path}")

            logger.info("Transcribing chunk %d: %s", chunk.chunk_id, audio_path)

            try:
                from mlx_audio.stt.generate import generate_transcription

                gen_kwargs = {
                    "model": self._model,
                    "audio": str(audio_path),
                    "format": "json",
                }
                if system_prompt:
                    gen_kwargs["system_prompt"] = system_prompt

                result = generate_transcription(**gen_kwargs)
            except Exception as e:
                raise RuntimeError(f"ASR failed for chunk {chunk.chunk_id}: {e}") from e

            # Extract text from result
            text = ""
            if isinstance(result, dict):
                text = result.get("text", "")
                if not text and "segments" in result:
                    segs = result["segments"]
                    text = " ".join(s.get("text", "") for s in segs) if segs else ""
            elif isinstance(result, str):
                text = result
            elif hasattr(result, "text"):
                text = result.text

            logger.info("Chunk %d result: %s", chunk.chunk_id, text[:100])
            segments.append(
                ASRSegment(
                    chunk_id=chunk.chunk_id,
                    segment_id=0,
                    start_sec=chunk.start_sec,
                    end_sec=chunk.end_sec,
                    text=text.strip(),
                    confidence=None,
                )
            )

        return segments
