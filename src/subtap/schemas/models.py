"""Data models for Subtap pipeline artifacts."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class MediaInfo(BaseModel):
    """Parsed media file metadata from ffprobe."""

    duration: float = Field(description="Duration in seconds")
    sample_rate: int = Field(default=16000, description="Audio sample rate in Hz")
    channels: int = Field(default=1, description="Number of audio channels")
    fps: Optional[float] = Field(
        default=None, description="Video frames per second if available"
    )


class Chunk(BaseModel):
    """A single audio chunk produced by VAD segmentation."""

    chunk_id: int = Field(description="Zero-based chunk index")
    start_sec: float = Field(description="Start time in seconds")
    end_sec: float = Field(description="End time in seconds")
    path: str = Field(description="Relative path to chunk WAV file")


class ASRSegment(BaseModel):
    """A single transcription segment produced by an ASR backend."""

    chunk_id: int = Field(description="Source chunk index")
    segment_id: int = Field(description="Segment index within the chunk (0-based)")
    start_sec: float = Field(description="Start time in seconds (chunk-level fallback)")
    end_sec: float = Field(description="End time in seconds")
    text: str = Field(description="Transcribed text")
    confidence: Optional[float] = Field(
        default=None, description="Confidence score if available"
    )


class CleanSegment(BaseModel):
    """A cleaned transcription segment with glossary tracking."""

    segment_id: int = Field(description="Segment index (maps to ASR segment)")
    source_chunk_id: int = Field(
        default=0, description="Source chunk index for traceability"
    )
    original_text: str = Field(description="Original ASR text before cleaning")
    cleaned_text: str = Field(description="Text after cleaning")
    glossary_applied: list[str] = Field(
        default_factory=list, description="Glossary terms applied"
    )


class SentenceSegment(BaseModel):
    """A structured sentence segment for subtitle generation."""

    sentence_id: int = Field(description="Sentence index (0-based)")
    chunk_id: int = Field(description="Source chunk index")
    start_sec: float = Field(description="Start time in seconds")
    end_sec: float = Field(description="End time in seconds")
    text: str = Field(description="Segmented sentence text")
    source_text: str = Field(description="Original cleaned_text from CleanSegment")


class AlignedSegment(BaseModel):
    """An aligned segment with precise timing from forced alignment."""

    sentence_id: int = Field(description="Sentence index (maps to SentenceSegment)")
    start_sec: float = Field(description="Aligned start time in seconds")
    end_sec: float = Field(description="Aligned end time in seconds")
    text: str = Field(description="Sentence text (may be hotword-replaced)")
    aligned_text: str | None = Field(
        default=None,
        description="Original aligned text before hotword replacement (for word filtering)",
    )
    words: list[dict] = Field(
        default_factory=list,
        description="Word-level timing [{word, start_sec, end_sec}]",
    )
