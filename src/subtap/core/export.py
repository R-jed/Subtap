"""Subtitle export: aligned.jsonl → SRT / ASS / TXT."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path

from subtap.core.itn import chinese_to_num


_PUNCT_MAP = str.maketrans(
    ",.?!;:()",
    "，。？！；：（）",
)

# All punctuation (both half-width and full-width) for stripping
_ALL_PUNCT_RE = re.compile(r"[，。？！、；：“”‘’（）《》,.?!;:\"'()\[\]{}\-—…·]")


def _normalize_punct(text: str, language: str = "zh") -> str:
    """Normalize punctuation by language.

    zh/ja: full-width Chinese punctuation
    en: half-width English punctuation
    """
    if language in ("zh", "ja"):
        return text.translate(_PUNCT_MAP)
    # English: convert full-width back to half-width
    _EN_PUNCT_MAP = str.maketrans(
        "，。？！；：（）",
        ",.?!;:()",
    )
    return text.translate(_EN_PUNCT_MAP)


def _strip_punct(text: str) -> str:
    """Remove all punctuation from text."""
    return _ALL_PUNCT_RE.sub("", text)


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


_PUNCT_CHARS = set("，。？！、；：""''（）《》,.?!;:\"'()[]{}\-—…·")


def _inject_punct(words: list[dict], text: str) -> list[dict]:
    """Inject punctuation from original text into word list.

    The forced aligner strips punctuation from word-level output.
    This function restores punctuation as pseudo-words with interpolated timestamps,
    so _smart_split can use them for sentence/comma breaks.
    """
    if not words or not text:
        return words

    result: list[dict] = []
    word_idx = 0
    text_idx = 0

    while text_idx < len(text) and word_idx < len(words):
        ch = text[text_idx]
        if ch in _PUNCT_CHARS:
            # Interpolate timestamp between previous and next word
            prev_end = result[-1]["end_sec"] if result else words[0]["start_sec"]
            next_start = words[word_idx]["start_sec"] if word_idx < len(words) else prev_end
            t = (prev_end + next_start) / 2
            result.append({"word": ch, "start_sec": round(t, 3), "end_sec": round(t, 3)})
            text_idx += 1
        elif word_idx < len(words):
            # Consume the next word from the word list
            result.append(words[word_idx])
            text_idx += len(words[word_idx]["word"])
            word_idx += 1
        else:
            text_idx += 1

    # Append remaining words
    result.extend(words[word_idx:])
    return result


def _smart_split(
    words: list[dict],
    text: str,
    max_chars: int = 25,
    min_chars: int = 3,
    pause_threshold: float = 0.3,
    start_sec: float = 0.0,
    end_sec: float = 0.0,
) -> list[dict]:
    """Split subtitle text based on word-level timestamps.

    Reference: whisperX iterate_subtitles() algorithm.
    Single-pass over words, deciding at each step: continue / new line / new subtitle.

    Priority:
    1. Sentence-ending punctuation (。！？.!?) → new subtitle
    2. Pause ≥ pause_threshold → new subtitle
    3. Comma/enum + line long enough → new line
    4. Exceeds max_chars → new line (with number protection)

    Post-processing:
    5. Merge filler words (呃/嗯/啊) into previous line
    6. Merge fragment lines (≤2 chars) into previous line
    """
    if not words:
        return [{"text": text, "start_sec": start_sec, "end_sec": end_sec}]

    _SENT_END = set("。！？.!?")
    _COMMA = set("，、,;")
    _NUM_CHARS = set("零一二两三四五六七八九十百千万亿")
    _FILLERS = {"呃", "嗯", "啊", "哦", "哈", "呀", "嘛", "吧", "呢", "喂", "哎", "唉"}

    # --- Phase 1: Single-pass word iteration ---
    lines: list[dict] = []
    current_words: list[dict] = []
    current_text = ""

    def _flush(break_type: str = "other"):
        nonlocal current_words, current_text
        if not current_words:
            return
        lines.append({
            "text": current_text.strip(),
            "start_sec": current_words[0]["start_sec"],
            "end_sec": current_words[-1]["end_sec"],
            "break_type": break_type,
        })
        current_words = []
        current_text = ""

    for i, w in enumerate(words):
        word_text = w["word"]

        # 1. Sentence-ending punctuation → flush and skip
        if word_text in _SENT_END:
            _flush("sentence_end")
            continue

        # 2. Pause detection → new subtitle
        if i > 0 and current_text and len(current_text.strip()) >= min_chars:
            gap = w["start_sec"] - words[i - 1]["end_sec"]
            if gap >= pause_threshold:
                _flush("pause")

        # 3. Max chars → new line (with number protection)
        if current_text and len(current_text.strip()) + len(word_text) > max_chars:
            prev_is_num = current_words and current_words[-1]["word"] in _NUM_CHARS
            cur_is_num = word_text in _NUM_CHARS
            if not (prev_is_num and cur_is_num):
                _flush("max_chars")

        # Add word
        current_words.append(w)
        current_text += word_text

        # 4. Comma + line substantial → new line
        if word_text in _COMMA and len(current_text.strip()) >= 10:
            _flush("comma")

    if current_words:
        _flush()

    # --- Phase 2: Post-processing ---
    lines = [l for l in lines if l["text"].strip()]

    merged: list[dict] = []
    for line in lines:
        text = line["text"]
        if text in _FILLERS and merged:
            merged[-1]["text"] += text
            merged[-1]["end_sec"] = line["end_sec"]
            continue
        if len(text) <= 1 and merged:
            merged[-1]["text"] += text
            merged[-1]["end_sec"] = line["end_sec"]
            continue
        merged.append(line)

    # Force-split lines exceeding max_chars at char boundaries
    final: list[dict] = []
    for line in merged:
        if len(line["text"]) <= max_chars:
            final.append(line)
            continue
        remaining = line["text"]
        elapsed = line["start_sec"]
        duration = line["end_sec"] - line["start_sec"]
        total_chars = len(remaining)
        while len(remaining) > max_chars:
            cut = max_chars
            # Don't cut in the middle of a number sequence
            if cut < len(remaining) and remaining[cut - 1] in _NUM_CHARS and remaining[cut] in _NUM_CHARS:
                while cut < len(remaining) and remaining[cut] in _NUM_CHARS:
                    cut += 1
            part = remaining[:cut]
            part_dur = duration * len(part) / total_chars if total_chars > 0 else 0
            final.append({"text": part, "start_sec": round(elapsed, 3), "end_sec": round(elapsed + part_dur, 3)})
            elapsed += part_dur
            remaining = remaining[cut:]
        if remaining:
            final.append({"text": remaining, "start_sec": round(elapsed, 3), "end_sec": line["end_sec"]})

    # Merge fragments created by force-split
    merged_final: list[dict] = []
    for line in final:
        if len(line["text"]) <= 1 and merged_final:
            merged_final[-1]["text"] += line["text"]
            merged_final[-1]["end_sec"] = line["end_sec"]
            continue
        merged_final.append(line)

    for line in merged_final:
        line.pop("break_type", None)

    return merged_final if merged_final else [{"text": text, "start_sec": words[0]["start_sec"], "end_sec": words[-1]["end_sec"]}]


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

    def __init__(self, punctuation: bool = False, language: str = "zh"):
        self.punctuation = punctuation
        self.language = language

    @property
    def extension(self) -> str:
        return "srt"

    def render(self, segments: list[AlignedSegment]) -> str:
        sorted_segs = sorted(segments, key=lambda s: s.start_sec)
        lines: list[str] = []
        index = 0
        for seg in sorted_segs:
            words_with_punct = _inject_punct(seg.words, seg.text)
            sub_lines = _smart_split(words_with_punct, seg.text, max_chars=25, start_sec=seg.start_sec, end_sec=seg.end_sec)
            for sub in sub_lines:
                if not sub["text"].strip():
                    continue
                index += 1
                start = _fmt_srt_time(sub["start_sec"])
                end = _fmt_srt_time(sub["end_sec"])
                text = chinese_to_num(sub["text"])
                if self.punctuation:
                    text = _normalize_punct(text, self.language)
                else:
                    text = _strip_punct(text)
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


def run_final_exports(
    aligned_jsonl: Path,
    output_dir: Path,
    punctuation: bool = False,
    language: str = "zh",
) -> dict:
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

    srt_path.write_text(
        SRTExporter(punctuation=punctuation, language=language).render(segments),
        encoding="utf-8",
    )

    vtt_lines = ["WEBVTT", ""]
    vtt_index = 0
    for seg in sorted(segments, key=lambda s: s.start_sec):
        sub_lines = _smart_split(seg.words, seg.text, max_chars=25, start_sec=seg.start_sec, end_sec=seg.end_sec)
        for sub in sub_lines:
            if not sub["text"].strip():
                continue
            vtt_index += 1
            text = chinese_to_num(sub["text"])
            if punctuation:
                text = _normalize_punct(text, language)
            else:
                text = _strip_punct(text)
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
