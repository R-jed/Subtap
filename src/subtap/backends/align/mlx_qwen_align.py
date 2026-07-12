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

DEFAULT_MODEL_ROOT = Path.home() / ".subtap" / "models"


def _visible_len(text: str) -> int:
    """Count characters represented by forced-alignment words."""
    return sum(ch.isalnum() for ch in text)


class MLXQwenAligner:
    """Forced alignment backend using mlx_audio STT with text prompt."""

    name = "mlx-qwen-aligner"

    def __init__(self, config: AlignConfig, model_root: Path | None = None):
        self.config = config
        self.model_name = config.model
        self.quantization = config.quantization
        self.runtime_name = f"qwen3-forcedaligner-{self.quantization}"
        self._model = None
        self._model_path = str((model_root or DEFAULT_MODEL_ROOT) / "aligner")
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

        Each source chunk is aligned once with all sentences in that chunk,
        then word timestamps are assigned back to sentences by visible character count.
        Raises if alignment cannot produce word timestamps.
        """
        self._load_model()
        if self._model is None:
            raise RuntimeError("Aligner model is not loaded")
        model = self._model

        # Load chunk metadata
        chunks_jsonl = audio_path.parent.parent / "chunks" / "chunks.jsonl"
        work_dir = audio_path.parent.parent  # work/
        self._load_chunk_info(chunks_jsonl)

        results_by_id: dict[int, AlignedSegment] = {}
        groups: dict[int, list[SentenceSegment]] = {}
        for sent in sentences:
            groups.setdefault(sent.chunk_id, []).append(sent)

        for chunk_id, chunk_sentences in groups.items():
            chunk_info = self._chunk_info.get(chunk_id, {})
            chunk_offset = chunk_info.get("start_sec", 0.0)
            chunk_audio = self._get_chunk_audio_path(chunk_id, work_dir)

            if chunk_audio is None:
                raise FileNotFoundError(f"Chunk {chunk_id} audio not found")

            try:
                # ForcedAlignerModel.generate() returns word-level timestamps.
                # Align the whole chunk once; per-sentence calls restart at chunk start.
                full_text = " ".join(sent.text for sent in chunk_sentences)
                align_result = model.generate(
                    audio=str(chunk_audio),
                    text=full_text,
                    language=self.config.language,
                )

                # Collect word-level timing with chunk offset + time_offset
                time_offset = self.config.time_offset_sec
                chunk_words: list[dict] = []
                for item in align_result:
                    if _visible_len(item.text) == 0:
                        raise RuntimeError(
                            "aligner returned a word with no visible text"
                        )
                    start = chunk_offset + item.start_time + time_offset
                    end = chunk_offset + item.end_time + time_offset
                    # Enforce minimum duration (model may output start==end)
                    if end <= start:
                        end = start + 0.020
                    chunk_words.append(
                        {
                            "word": item.text,
                            "start_sec": round(start, 3),
                            "end_sec": round(end, 3),
                        }
                    )

                if chunk_words:
                    word_idx = 0
                    chunk_end = chunk_info.get("end_sec", chunk_words[-1]["end_sec"])
                    for sent_index, sent in enumerate(chunk_sentences):
                        start_word = word_idx
                        matched = 0
                        target = _visible_len(sent.text)
                        is_last = sent_index == len(chunk_sentences) - 1
                        while word_idx < len(chunk_words) and (
                            matched < target or is_last
                        ):
                            word_len = _visible_len(chunk_words[word_idx]["word"])
                            # Check if adding this word would exceed target
                            if (
                                not is_last
                                and matched + word_len > target
                                and matched > 0
                            ):
                                break
                            matched += word_len
                            word_idx += 1

                        words = chunk_words[start_word:word_idx]
                        if not words:
                            raise RuntimeError(
                                f"Failed to align sentence {sent.sentence_id} "
                                f"in chunk {chunk_id}: no words returned"
                            )

                        start = max(chunk_offset, min(words[0]["start_sec"], chunk_end))
                        end = max(start + 0.01, min(words[-1]["end_sec"], chunk_end))
                        results_by_id[sent.sentence_id] = AlignedSegment(
                            sentence_id=sent.sentence_id,
                            start_sec=round(start, 3),
                            end_sec=round(end, 3),
                            text=sent.text,
                            words=words,
                        )

                    logger.info(
                        "Aligned chunk %d: %d sentences, %d words",
                        chunk_id,
                        len(chunk_sentences),
                        len(chunk_words),
                    )
                    continue

            except Exception as e:
                raise RuntimeError(f"Failed to align chunk {chunk_id}: {e}") from e

            raise RuntimeError(f"Failed to align chunk {chunk_id}: no words returned")

        return [results_by_id[sent.sentence_id] for sent in sentences]
