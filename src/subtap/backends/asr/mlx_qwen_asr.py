"""MLX Qwen ASR backend implementation.

Uses mlx_audio.stt.generate_transcription for speech-to-text.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from subtap.backends.asr.base import ProgressCallback
from subtap.schemas.config import ASRConfig
from subtap.schemas.models import Chunk, ASRSegment

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ROOT = Path.home() / ".subtap" / "models"
_TOKENS_PER_AUDIO_SECOND = 16
_TOKEN_BUDGET_HEADROOM = 64
_MAX_GENERATION_TOKENS = 2048
_HOTWORD_PROMPT_PREFIX = "请注意以下专业术语和人名："


def _generation_token_budget(duration_sec: float) -> int:
    """Bound decoder work to the amount of speech that can exist in a chunk."""
    return min(
        _MAX_GENERATION_TOKENS,
        max(
            _TOKEN_BUDGET_HEADROOM,
            int(duration_sec * _TOKENS_PER_AUDIO_SECOND) + _TOKEN_BUDGET_HEADROOM,
        ),
    )


def _extract_text(result) -> str:
    """Extract transcript text from the runtime's supported result shapes."""
    if isinstance(result, dict):
        if "text" in result:
            text = result["text"]
            if not isinstance(text, str):
                raise TypeError("unsupported result text type")
            if text or "segments" not in result:
                return text
        if "segments" in result:
            segments = result["segments"]
            if not isinstance(segments, list):
                raise TypeError("unsupported result segments type")
            segment_texts = []
            for segment in segments:
                if (
                    not isinstance(segment, dict)
                    or "text" not in segment
                    or not isinstance(segment["text"], str)
                ):
                    raise TypeError("unsupported result type in segments")
                segment_texts.append(segment["text"])
            text = " ".join(segment_texts)
        else:
            raise TypeError("unsupported result type: dict without text or segments")
        return text
    if isinstance(result, str):
        return result
    if hasattr(result, "text"):
        text = result.text
        if isinstance(text, str):
            return text
        raise TypeError("unsupported result text type")
    raise TypeError(f"unsupported result type: {type(result).__name__}")


def _has_runaway_repetition(text: str) -> bool:
    """Detect short decoder loops that cannot represent natural speech."""
    compact = re.sub(r"\s+", "", text)
    return len(compact) >= 20 and re.search(r"(.{1,4})\1{9,}", compact) is not None


def _generate_checked_transcript(generate, gen_kwargs: dict, chunk_id: int) -> str:
    """Generate a transcript with the same protocol checks on every attempt."""
    repetition_count = 0
    for attempt in range(3):
        text = _extract_text(generate(**gen_kwargs)).strip()
        if text.startswith(_HOTWORD_PROMPT_PREFIX):
            if "system_prompt" not in gen_kwargs:
                raise RuntimeError(
                    f"hotword prompt persisted for chunk {chunk_id} after retry"
                )
            logger.warning(
                "Chunk %d echoed the hotword prompt; retrying without it",
                chunk_id,
            )
            gen_kwargs.pop("system_prompt")
            continue
        if not _has_runaway_repetition(text):
            return text

        repetition_count += 1
        if repetition_count >= 2 and "system_prompt" in gen_kwargs:
            logger.warning(
                "Chunk %d repeated again; retrying without hotwords",
                chunk_id,
            )
            gen_kwargs.pop("system_prompt")
        else:
            logger.warning(
                "Chunk %d entered a decoder repetition loop; retrying",
                chunk_id,
            )
        if attempt == 2:
            break

    raise RuntimeError(f"ASR decoder repetition persisted for chunk {chunk_id}")


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
        self._progress_callback: ProgressCallback | None = None
        root = model_root or DEFAULT_MODEL_ROOT
        model_subdir = "asr_1.7b" if self.model_name == "asr_1.7b" else "asr_0.6b"
        self._model_path = str(root / model_subdir)

    def release_model(self) -> None:
        """Release the in-memory MLX model after the ASR stage."""
        self._model = None

    def set_progress_callback(self, callback: ProgressCallback | None) -> None:
        """Report completion immediately after each audio chunk."""
        self._progress_callback = callback

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
        return f"{_HOTWORD_PROMPT_PREFIX}{word_list}"

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

        total = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
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
                    "max_tokens": _generation_token_budget(
                        chunk.end_sec - chunk.start_sec
                    ),
                }
                if system_prompt:
                    gen_kwargs["system_prompt"] = system_prompt

                text = _generate_checked_transcript(
                    generate_transcription, gen_kwargs, chunk.chunk_id
                )
            except Exception as e:
                raise RuntimeError(f"ASR failed for chunk {chunk.chunk_id}: {e}") from e

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
            if self._progress_callback is not None:
                self._progress_callback(index, total, chunk)

        return segments
