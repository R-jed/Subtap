"""Subtitle export: aligned.jsonl → SRT / ASS / TXT."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path

from subtap.core.itn import chinese_to_num
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


def _fmt_vtt_time(seconds: float) -> str:
    """Format seconds to VTT timestamp HH:MM:SS.mmm."""
    return _fmt_srt_time(seconds).replace(",", ".")


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


_SPLIT_RE = re.compile(r"(?<=[，。？！、,.?!])")


def _split_subtitle_lines(
    text: str,
    words: list[dict],
    start_sec: float,
    end_sec: float,
    max_chars: int = 20,
) -> list[dict]:
    """Split subtitle text by punctuation, interpolate time from word timestamps."""
    parts = _SPLIT_RE.split(text)
    parts = [p.strip() for p in parts if p.strip()]

    if not parts:
        return [{"text": text, "start_sec": start_sec, "end_sec": end_sec}]

    # Force-split long parts
    final_parts: list[str] = []
    for part in parts:
        while len(part) > max_chars:
            cut = max_chars
            for sep in ["，", "、", " ", "。"]:
                idx = part.rfind(sep, 0, max_chars)
                if idx > 0:
                    cut = idx + 1
                    break
            final_parts.append(part[:cut])
            part = part[cut:]
        if part:
            final_parts.append(part)

    if len(final_parts) <= 1:
        return [{"text": text, "start_sec": start_sec, "end_sec": end_sec}]

    # Time interpolation
    if words:
        return _interpolate_from_words(text, final_parts, words, start_sec, end_sec)
    else:
        return _interpolate_proportional(final_parts, start_sec, end_sec)


def _interpolate_from_words(
    original_text: str,
    parts: list[str],
    words: list[dict],
    start_sec: float,
    end_sec: float,
) -> list[dict]:
    """Interpolate sub-sentence times from word timestamps."""
    _PUNCT = set("，。？！、,.?! ")

    result = []
    word_idx = 0

    for part in parts:
        part_start_word = word_idx
        # Count visible chars in this part (excluding punctuation)
        visible_chars = [ch for ch in part if ch not in _PUNCT]

        matched = 0
        while word_idx < len(words) and matched < len(visible_chars):
            w_text = words[word_idx]["word"]
            # This word matches some visible chars
            matched += len([ch for ch in w_text if ch not in _PUNCT])
            word_idx += 1

        part_words = words[part_start_word:word_idx]
        if part_words:
            s = part_words[0]["start_sec"]
            e = part_words[-1]["end_sec"]
        else:
            # Fallback: use previous word's end time
            s = (
                words[part_start_word - 1]["end_sec"]
                if part_start_word > 0
                else start_sec
            )
            e = s + 0.1

        result.append({"text": part, "start_sec": round(s, 3), "end_sec": round(e, 3)})

    # Ensure last part ends at end_sec
    if result:
        result[-1]["end_sec"] = round(end_sec, 3)

    return result


def _interpolate_proportional(
    parts: list[str],
    start_sec: float,
    end_sec: float,
) -> list[dict]:
    """Interpolate sub-sentence times by visible character ratio."""
    vis_counts = []
    for part in parts:
        count = sum(1 for ch in part if ch not in "，。？！、,.?! ")
        vis_counts.append(max(count, 1))

    total = sum(vis_counts)
    duration = end_sec - start_sec

    result = []
    current = start_sec
    for i, (part, vc) in enumerate(zip(parts, vis_counts)):
        if i == len(parts) - 1:
            s, e = current, end_sec
        else:
            s = current
            e = current + duration * vc / total
            current = e
        result.append({"text": part, "start_sec": round(s, 3), "end_sec": round(e, 3)})

    return result


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
        sorted_segs = sorted(segments, key=lambda s: s.start_sec)
        lines: list[str] = []
        index = 0
        for seg in sorted_segs:
            sub_lines = _split_subtitle_lines(
                seg.text, seg.words, seg.start_sec, seg.end_sec, max_chars=20
            )
            for sub in sub_lines:
                index += 1
                start = _fmt_srt_time(sub["start_sec"])
                end = _fmt_srt_time(sub["end_sec"])
                text = chinese_to_num(sub["text"])
                lines.append(str(index))
                lines.append(f"{start} --> {end}")
                lines.append(text)
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


def _final_json_item(seg: AlignedSegment) -> dict:
    """Convert aligned segment to final.json schema."""
    return {
        "subtitle_id": seg.sentence_id,
        "start_sec": seg.start_sec,
        "end_sec": seg.end_sec,
        "text": seg.text,
        "words": [
            {"word": w["word"], "start_sec": w["start_sec"], "end_sec": w["end_sec"]}
            for w in seg.words
        ],
        "chars": [],
        "source_trace": {
            "source": "forced_aligner",
            "aligned_segment_id": seg.sentence_id,
        },
        "alignment_confidence": None,
    }


def run_final_exports(aligned_jsonl: Path, output_dir: Path) -> dict:
    """Export aligned subtitles to the stable final.* output contract."""
    if not aligned_jsonl.exists():
        return run_export(aligned_jsonl, output_dir, fmt="srt", stem="final")

    segments = load_aligned(aligned_jsonl)
    if not segments:
        raise ValueError(f"No aligned segments found in {aligned_jsonl}")

    output_dir.mkdir(parents=True, exist_ok=True)
    srt_path = output_dir / "final.srt"
    vtt_path = output_dir / "final.vtt"
    json_path = output_dir / "final.json"
    tsv_path = output_dir / "final.tsv"

    srt_path.write_text(SRTExporter().render(segments), encoding="utf-8")

    vtt_lines = ["WEBVTT", ""]
    vtt_index = 0
    for seg in sorted(segments, key=lambda s: s.start_sec):
        sub_lines = _split_subtitle_lines(
            seg.text, seg.words, seg.start_sec, seg.end_sec, max_chars=20
        )
        for sub in sub_lines:
            vtt_index += 1
            text = chinese_to_num(sub["text"])
            vtt_lines.extend(
                [
                    str(vtt_index),
                    f"{_fmt_vtt_time(sub['start_sec'])} --> {_fmt_vtt_time(sub['end_sec'])}",
                    text,
                    "",
                ]
            )
    vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")

    final_payload = [_final_json_item(seg) for seg in segments]
    json_path.write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    tsv_lines = ["subtitle_id\tstart_sec\tend_sec\ttext"]
    for seg in sorted(segments, key=lambda s: s.start_sec):
        text = seg.text.replace("\t", " ").replace("\n", " ")
        tsv_lines.append(f"{seg.sentence_id}\t{seg.start_sec}\t{seg.end_sec}\t{text}")
    tsv_path.write_text("\n".join(tsv_lines), encoding="utf-8")

    run_log_path = output_dir / "run.log.jsonl"
    if not run_log_path.exists():
        run_log_path.write_text(
            json.dumps(
                {"event": "output_contract_written", "contract": "final"},
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    return {
        "output_path": str(srt_path),
        "outputs": [str(srt_path), str(vtt_path), str(json_path), str(tsv_path)],
        "format": "final",
        "segment_count": len(segments),
        "output_contract": "final",
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
