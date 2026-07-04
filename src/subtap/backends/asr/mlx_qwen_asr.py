"""MLX Qwen ASR backend implementation.

Uses mlx_audio.stt.generate_transcription for speech-to-text.
"""

from __future__ import annotations

import logging
from pathlib import Path

from subtap.schemas.config import ASRConfig
from subtap.schemas.models import Chunk, ASRSegment

logger = logging.getLogger(__name__)

# Local model paths (relative to project root)
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_MODEL_0_6B = str(_PROJECT_ROOT / "models" / "asr_0.6b")
_MODEL_1_7B = str(_PROJECT_ROOT / "models" / "asr_1.7b")
_MODEL_MIMO = str(_PROJECT_ROOT / "models" / "mimo_asr")


class MLXQwenASR:
    """ASR backend using mlx_audio STT."""

    name = "mlx-qwen-asr"

    def __init__(self, config: ASRConfig):
        self.config = config
        self.model_name = config.model
        self.quantization = config.quantization
        if self.model_name == "mimo_asr":
            self.runtime_name = f"mimo-v2.5-asr-{self.quantization}"
        else:
            self.runtime_name = (
                f"qwen3-asr-{self.model_name.replace('asr_', '')}-{self.quantization}"
            )
        self._model = None
        _MODEL_PATHS = {
            "asr_0.6b": _MODEL_0_6B,
            "asr_1.7b": _MODEL_1_7B,
            "mimo_asr": _MODEL_MIMO,
        }
        self._model_path = _MODEL_PATHS.get(self.model_name, _MODEL_0_6B)

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

    def transcribe(
        self,
        chunks: list[Chunk],
        language: str | None = None,
        hotwords: list[str] | None = None,
    ) -> list[ASRSegment]:
        """Transcribe chunks sequentially using MLX STT."""
        self._load_model()
        segments: list[ASRSegment] = []

        for chunk in chunks:
            audio_path = Path(chunk.path)
            if not audio_path.is_absolute():
                audio_path = Path.cwd() / audio_path

            if not audio_path.exists():
                logger.warning("Chunk file not found: %s, skipping", audio_path)
                continue

            logger.info("Transcribing chunk %d: %s", chunk.chunk_id, audio_path)

            try:
                from mlx_audio.stt.generate import generate_transcription

                kwargs: dict = {
                    "model": self._model,
                    "audio": str(audio_path),
                    "format": "json",
                }
                if language and self.model_name == "mimo_asr":
                    kwargs["language"] = language

                result = generate_transcription(**kwargs)
            except Exception as e:
                logger.error("ASR failed for chunk %d: %s", chunk.chunk_id, e)
                continue

            # Extract text and timestamps from result
            text = ""
            result_segments: list[dict] | None = None
            if isinstance(result, dict):
                text = result.get("text", "")
                if not text and "segments" in result:
                    segs = result["segments"]
                    text = " ".join(s.get("text", "") for s in segs) if segs else ""
                result_segments = result.get("segments")
            elif isinstance(result, str):
                text = result
            elif hasattr(result, "text"):
                text = result.text
                if hasattr(result, "segments"):
                    result_segments = result.segments

            logger.info("Chunk %d result: %s", chunk.chunk_id, text[:100])

            if result_segments:
                for seg in result_segments:
                    seg_text = seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")
                    seg_start = seg.get("start", chunk.start_sec) if isinstance(seg, dict) else getattr(seg, "start", chunk.start_sec)
                    seg_end = seg.get("end", chunk.end_sec) if isinstance(seg, dict) else getattr(seg, "end", chunk.end_sec)
                    if seg_text.strip():
                        segments.append(
                            ASRSegment(
                                chunk_id=chunk.chunk_id,
                                segment_id=len(segments),
                                start_sec=chunk.start_sec + seg_start,
                                end_sec=chunk.start_sec + seg_end,
                                text=seg_text.strip(),
                                confidence=None,
                            )
                        )
            else:
                segments.append(
                    ASRSegment(
                        chunk_id=chunk.chunk_id,
                        segment_id=len(segments),
                        start_sec=chunk.start_sec,
                        end_sec=chunk.end_sec,
                        text=text.strip(),
                        confidence=None,
                    )
                )

        return segments
