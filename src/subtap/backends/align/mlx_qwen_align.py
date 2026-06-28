"""MLX Qwen ForcedAligner implementation.

Uses mlx_audio.stt.generate_transcription with text parameter for forced alignment.
Each sentence is aligned against its source chunk audio for accurate positioning.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from subtap.schemas.config import AlignConfig
from subtap.schemas.models import SentenceSegment, AlignedSegment

logger = logging.getLogger(__name__)

# Local aligner model path (relative to project root)
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_MODEL = str(_PROJECT_ROOT / "models" / "aligner")


class MLXQwenAligner:
    """Forced alignment backend using mlx_audio STT with text prompt."""

    name = "mlx-qwen-aligner"

    def __init__(self, config: AlignConfig):
        self.config = config
        self.model_name = config.model
        self.quantization = config.quantization
        self.runtime_name = f"qwen3-forcedaligner-{self.quantization}"
        self._model = None
        self._model_path = _DEFAULT_MODEL
        self._chunk_info: dict[int, dict] = {}  # chunk_id → {start_sec, path}

    def release_model(self) -> None:
        """Release the in-memory MLX aligner after the alignment stage."""
        self._model = None

    def _load_model(self):
        """Lazy-load the MLX alignment model."""
        if self._model is not None:
            return
        try:
            from mlx_audio.stt.generate import load_model

            logger.info("Loading aligner model: %s", self._model_path)
            self._model = load_model(self._model_path)
            logger.info("Aligner model loaded successfully")
        except ImportError:
            raise ImportError(
                "mlx_audio is required for MLX Qwen Aligner. "
                "Install: pip install mlx-audio"
            )

    def _load_chunk_info(self, chunks_jsonl: Path):
        """Load chunk metadata for offset and path lookup."""
        if self._chunk_info:
            return
        if not chunks_jsonl.exists():
            logger.warning("chunks.jsonl not found: %s", chunks_jsonl)
            return
        with open(chunks_jsonl) as f:
            for line in f:
                line = line.strip()
                if line:
                    chunk = json.loads(line)
                    self._chunk_info[chunk["chunk_id"]] = {
                        "start_sec": chunk["start_sec"],
                        "end_sec": chunk["end_sec"],
                        "path": chunk["path"],
                    }
        logger.info("Loaded %d chunk infos", len(self._chunk_info))

    def _get_chunk_audio_path(self, chunk_id: int, work_dir: Path) -> Path | None:
        """Resolve chunk WAV file absolute path."""
        info = self._chunk_info.get(chunk_id)
        if info is None:
            return None
        chunk_path = work_dir / info["path"]
        return chunk_path if chunk_path.exists() else None

    def align(
        self,
        sentences: list[SentenceSegment],
        audio_path: Path,
    ) -> list[AlignedSegment]:
        """Align sentences to audio using forced alignment.

        Each sentence is aligned against its SOURCE CHUNK audio (not the full file),
        then timestamps are offset by the chunk's start time for absolute positioning.
        Falls back to sentence timing if alignment fails.
        """
        self._load_model()

        # Load chunk metadata
        chunks_jsonl = audio_path.parent.parent / "chunks" / "chunks.jsonl"
        work_dir = audio_path.parent.parent  # work/
        self._load_chunk_info(chunks_jsonl)

        results: list[AlignedSegment] = []

        for sent in sentences:
            chunk_info = self._chunk_info.get(sent.chunk_id, {})
            chunk_offset = chunk_info.get("start_sec", 0.0)
            chunk_audio = self._get_chunk_audio_path(sent.chunk_id, work_dir)

            if chunk_audio is None:
                logger.warning(
                    "Chunk %d audio not found, using fallback", sent.chunk_id
                )
                results.append(
                    AlignedSegment(
                        sentence_id=sent.sentence_id,
                        start_sec=sent.start_sec,
                        end_sec=sent.end_sec,
                        text=sent.text,
                    )
                )
                continue

            try:
                from mlx_audio.stt.generate import generate_transcription

                # Align against chunk audio
                result = generate_transcription(
                    model=self._model,
                    audio=str(chunk_audio),
                    text=sent.text,
                    format="json",
                )

                # Extract character-level alignment
                if hasattr(result, "segments") and result.segments:
                    segs = result.segments
                    raw_start = segs[0].get("start", 0.0)
                    raw_end = segs[-1].get("end", raw_start + 0.1)

                    # Offset by chunk start time
                    start = chunk_offset + raw_start
                    end = chunk_offset + raw_end

                    # Clamp to chunk boundaries
                    chunk_end = chunk_info.get("end_sec", end + 1.0)
                    start = max(chunk_offset, min(start, chunk_end))
                    end = max(start + 0.01, min(end, chunk_end))

                    results.append(
                        AlignedSegment(
                            sentence_id=sent.sentence_id,
                            start_sec=round(start, 3),
                            end_sec=round(end, 3),
                            text=sent.text,
                        )
                    )
                    logger.info(
                        "Aligned sentence %d: %.3f - %.3f (chunk %d, offset=%.2f)",
                        sent.sentence_id,
                        start,
                        end,
                        sent.chunk_id,
                        chunk_offset,
                    )
                    continue

            except Exception as e:
                logger.warning(
                    "Alignment failed for sentence %d: %s, using fallback",
                    sent.sentence_id,
                    e,
                )

            # Fallback: use sentence timing
            results.append(
                AlignedSegment(
                    sentence_id=sent.sentence_id,
                    start_sec=sent.start_sec,
                    end_sec=sent.end_sec,
                    text=sent.text,
                )
            )

        return results
