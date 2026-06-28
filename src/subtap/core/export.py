"""Subtitle export: aligned.jsonl → SRT / ASS / TXT."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from subtap.schemas.models import AlignedSegment, ASRSegment


def _fmt_srt_time(seconds: float) -> str:
    """Format seconds to SRT timestamp HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_ass_time(seconds: float) -> str:
    """Format seconds to ASS timestamp H:MM:SS.cc."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def load_aligned(aligned_jsonl: Path) -> list[AlignedSegment]:
    """Load AlignedSegments from JSONL, sorted by sentence_id."""
    segments: list[AlignedSegment] = []
    with open(aligned_jsonl) as f:
        for line in f:
            line = line.strip()
            if line:
                segments.append(AlignedSegment.model_validate_json(line))
    segments.sort(key=lambda s: s.sentence_id)
    return segments


def load_asr_draft(asr_jsonl: Path) -> list[ASRSegment]:
    """Load ASR reference-timing segments from JSONL."""
    segments: list[ASRSegment] = []
    with open(asr_jsonl) as f:
        for line in f:
            line = line.strip()
            if line:
                segments.append(ASRSegment.model_validate_json(line))
    segments.sort(key=lambda s: (s.chunk_id, s.segment_id))
    return segments


class BaseExporter(ABC):
    """Base class for subtitle exporters."""

    @property
    @abstractmethod
    def extension(self) -> str:
        """File extension (e.g. 'srt')."""

    @abstractmethod
    def render(self, segments: list[AlignedSegment]) -> str:
        """Render segments to subtitle format string."""

    def export(self, segments: list[AlignedSegment], output_path: Path) -> Path:
        """Write subtitle file to disk."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = self.render(segments)
        output_path.write_text(content, encoding="utf-8")
        return output_path


class SRTExporter(BaseExporter):
    """SRT subtitle exporter."""

    @property
    def extension(self) -> str:
        return "srt"

    def render(self, segments: list[AlignedSegment]) -> str:
        sorted_segs = sorted(segments, key=lambda s: s.sentence_id)
        lines: list[str] = []
        for i, seg in enumerate(sorted_segs, 1):
            start = _fmt_srt_time(seg.start_sec)
            end = _fmt_srt_time(seg.end_sec)
            lines.append(str(i))
            lines.append(f"{start} --> {end}")
            lines.append(seg.text)
            lines.append("")
        return "\n".join(lines)


class ASSExporter(BaseExporter):
    """ASS subtitle exporter (minimal viable)."""

    HEADER = (
        "[Script Info]\n"
        "Title: Subtap Export\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    @property
    def extension(self) -> str:
        return "ass"

    def render(self, segments: list[AlignedSegment]) -> str:
        lines = [self.HEADER]
        for seg in segments:
            start = _fmt_ass_time(seg.start_sec)
            end = _fmt_ass_time(seg.end_sec)
            # Escape newlines for ASS
            text = seg.text.replace("\n", "\\N")
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
        return "\n".join(lines)


class TXTExporter(BaseExporter):
    """Plain text exporter with timestamps."""

    @property
    def extension(self) -> str:
        return "txt"

    def render(self, segments: list[AlignedSegment]) -> str:
        lines: list[str] = []
        for seg in segments:
            start = _fmt_srt_time(seg.start_sec).replace(",", ".")
            end = _fmt_srt_time(seg.end_sec).replace(",", ".")
            lines.append(f"[{start} → {end}]")
            lines.append(seg.text)
            lines.append("")
        return "\n".join(lines)


EXPORTERS: dict[str, type[BaseExporter]] = {
    "srt": SRTExporter,
    "ass": ASSExporter,
    "txt": TXTExporter,
}


def run_export(
    aligned_jsonl: Path,
    output_dir: Path,
    fmt: str = "srt",
    stem: str = "output",
) -> dict:
    """Export aligned.jsonl to subtitle file.

    Args:
        aligned_jsonl: Path to aligned.jsonl.
        output_dir: Output directory.
        fmt: Export format (srt/ass/txt).
        stem: Output file stem (without extension).

    Returns:
        Dict with output_path and format.
    """
    exporter_cls = EXPORTERS.get(fmt)
    if exporter_cls is None:
        raise ValueError(
            f"Unknown export format: {fmt}. Supported: {list(EXPORTERS.keys())}"
        )

    segments = load_aligned(aligned_jsonl)
    if not segments:
        raise ValueError(f"No aligned segments found in {aligned_jsonl}")

    exporter = exporter_cls()
    output_path = output_dir / f"{stem}.{exporter.extension}"
    exporter.export(segments, output_path)

    return {
        "output_path": str(output_path),
        "format": fmt,
        "segment_count": len(segments),
    }


def run_draft_export(asr_jsonl: Path, output_dir: Path) -> dict:
    """Export ASR reference timing as draft.srt and draft.json."""
    segments = load_asr_draft(asr_jsonl)
    if not segments:
        raise ValueError(f"No ASR draft segments found in {asr_jsonl}")

    output_dir.mkdir(parents=True, exist_ok=True)
    srt_path = output_dir / "draft.srt"
    json_path = output_dir / "draft.json"

    lines: list[str] = []
    payload: list[dict] = []
    for index, seg in enumerate(segments, start=1):
        lines.extend(
            [
                str(index),
                f"{_fmt_srt_time(seg.start_sec)} --> {_fmt_srt_time(seg.end_sec)}",
                seg.text,
                "",
            ]
        )
        payload.append(
            {
                "index": index,
                "start_sec": seg.start_sec,
                "end_sec": seg.end_sec,
                "text": seg.text,
                "source": "asr_reference_timing",
            }
        )

    import json

    srt_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "output_path": str(srt_path),
        "json_path": str(json_path),
        "format": "draft",
        "segment_count": len(segments),
        "alignment_enabled": False,
    }
