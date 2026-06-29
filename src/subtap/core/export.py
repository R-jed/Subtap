"""Subtitle export: aligned.jsonl → SRT / ASS / TXT."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path

from subtap.core.itn import chinese_to_num
from subtap.core.phrases import mark_phrase_boundaries
from subtap.schemas.models import AlignedSegment, ASRSegment


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


_PUNCT_CHARS = set("，。？！、；：""''（）《》,.?!;:\"'()[]{}\\-—…·")


def _inject_punct(words: list[dict], text: str) -> list[dict]:
    """Inject punctuation from original text into word list.

    The forced aligner strips punctuation from word-level output.
    This function restores punctuation as pseudo-words with interpolated timestamps,
    so _smart_split can use them for sentence/comma breaks.

    Uses semantic matching: for each word, find its position in the original text
    via str.find(), then insert any punctuation found in the gap before that word.
    This handles cases where the word list is missing characters that exist in the
    text (common with forced aligners), preventing punctuation from being placed
    at wrong positions.
    """
    if not words or not text:
        return words

    result: list[dict] = []
    text_pos = 0  # current position in original text

    def _interpolate(prev_end: float, next_start: float) -> float:
        return round((prev_end + next_start) / 2, 3)

    for w in words:
        word = w["word"]
        # Find where this word appears in the text, starting from current position
        pos = text.find(word, text_pos)

        if pos >= 0:
            # Scan the gap [text_pos, pos) for punctuation
            prev_end = result[-1]["end_sec"] if result else words[0]["start_sec"]
            next_start = w["start_sec"]
            for ch in text[text_pos:pos]:
                if ch in _PUNCT_CHARS:
                    t = _interpolate(prev_end, next_start)
                    result.append({"word": ch, "start_sec": t, "end_sec": t})
                    prev_end = t
            # Add the word
            result.append(w)
            text_pos = pos + len(word)
        else:
            # Word not found in text (shouldn't happen normally), add as-is
            result.append(w)

    # Scan trailing punctuation after the last matched word
    if text_pos < len(text):
        prev_end = result[-1]["end_sec"] if result else 0.0
        next_start = words[-1]["end_sec"] if words else prev_end
        for ch in text[text_pos:]:
            if ch in _PUNCT_CHARS:
                t = _interpolate(prev_end, next_start)
                result.append({"word": ch, "start_sec": t, "end_sec": t})
                prev_end = t

    return result


def _smart_split(
    words: list[dict],
    text: str,
    max_chars: int = 25,
    min_chars: int = 8,
    pause_threshold: float = 0.2,
    start_sec: float = 0.0,
    end_sec: float = 0.0,
) -> list[dict]:
    """Split subtitle text using phrase-boundary scoring + greedy selection.

    Algorithm:
    1. Mark phrase boundaries via mark_phrase_boundaries()
    2. Accumulate words; split on sentence-end, punctuation, pause, or max_chars
    3. At max_chars triggers, score candidate break positions and select the best
    4. Merge very short fragments (<=2 chars) into adjacent lines

    Scoring rules (for max_chars triggers):
    - phrase_mid: -1000 (forbidden, inside protected phrase)
    - pause: +5
    - phrase_end (boundary after protected phrase): +8
    - comma/enum: +9
    - particle (语气词后): +10
    - forced (超 max_chars): +100
    """
    if not words:
        return [{"text": text, "start_sec": start_sec, "end_sec": end_sec}]

    _SENT_END = set("。！？.!?")
    _COMMA_PUNCT = set("，、,;")
    _NUM_CHARS = set("零一二两三四五六七八九十百千万亿")

    # --- Step 1: Mark phrase boundaries ---
    marked_words = mark_phrase_boundaries(words)
    _phrase_roles: dict[int, str | None] = {
        i: w.get("phrase_role") for i, w in enumerate(marked_words)
    }

    # --- Step 2: Greedy split with scoring ---
    lines: list[dict] = []

    def _flush(cur_words: list[dict], cur_text: str, ends_punct: bool):
        if not cur_words:
            return
        lines.append({
            "text": cur_text,
            "start_sec": cur_words[0]["start_sec"],
            "end_sec": cur_words[-1]["end_sec"],
            "ends_punct": ends_punct,
        })

    def _find_best_break(cur_words: list[dict]) -> int:
        """Find the best break position using phrase-role scoring.

        Returns the position after which to break (0-indexed in cur_words).
        Handles number-sequence protection: skips positions inside number
        sequences and falls back to the start of the sequence.
        """
        best = -1
        best_score = -9999
        accum = 0
        n = len(cur_words)
        pos = 0

        while pos < n - 1:
            w_len = len(cur_words[pos]["word"])

            # Number sequence protection: if entering a number sequence,
            # check if the ENTIRE sequence would exceed max_chars.
            # If so, split before the sequence. If not, skip the sequence.
            if cur_words[pos]["word"] in _NUM_CHARS:
                seq_start = pos
                seq_end = pos
                while seq_end < n - 1 and cur_words[seq_end + 1]["word"] in _NUM_CHARS:
                    seq_end += 1
                seq_len = sum(len(cur_words[j]["word"]) for j in range(seq_start, seq_end + 1))
                if seq_len >= max_chars:
                    best = max(seq_start - 1, 0)
                    pos = seq_end + 1
                else:
                    for j in range(seq_start, seq_end + 1):
                        accum += len(cur_words[j]["word"])
                    pos = seq_end + 1
                continue

            accum += w_len

            # Score this position
            score = 0
            role = _phrase_roles.get(pos)
            if role == "phrase_mid":
                score = -1000
            elif role == "particle":
                score = 10
            elif role == "phrase_end":
                score = 8

            if cur_words[pos]["word"] in "，、,;":
                score += 9

            if pos + 1 < n:
                gap = cur_words[pos + 1]["start_sec"] - cur_words[pos]["end_sec"]
                if gap >= pause_threshold:
                    score = max(score, 5)

            if accum >= max_chars:
                score = max(score, 100)

            if score > best_score:
                best_score = score
                best = pos

            pos += 1

        if best < 0:
            best = min(max_chars, n - 1)

        return best

    cur_words: list[dict] = []
    cur_text = ""

    for i, w in enumerate(words):
        word_text = w["word"]

        # Sentence-ending punctuation → flush and skip
        if word_text in _SENT_END:
            _flush(cur_words, cur_text, True)
            cur_words = []
            cur_text = ""
            continue

        # Max chars check BEFORE adding (to detect number sequences early)
        if cur_text and len(cur_text) + len(word_text) > max_chars:
            # Look ahead: if next word starts a number sequence, split before it
            if word_text in _NUM_CHARS:
                # Find start of this number sequence in cur_words
                seq_start = len(cur_words) - 1
                while seq_start > 0 and cur_words[seq_start - 1]["word"] in _NUM_CHARS:
                    seq_start -= 1
                bp = seq_start - 1
                if 0 <= bp < len(cur_words) - 1:
                    right = cur_words[bp + 1:]
                    left = cur_words[:bp + 1]
                    _flush(left, "".join(x["word"] for x in left), False)
                    cur_words = right
                    cur_text = "".join(x["word"] for x in right)
                # Now add the current word
                cur_words.append(w)
                cur_text += word_text
            else:
                bp = _find_best_break(cur_words)
                if 0 <= bp < len(cur_words) - 1:
                    right = cur_words[bp + 1:]
                    left = cur_words[:bp + 1]
                    _flush(left, "".join(x["word"] for x in left), False)
                    cur_words = right
                    cur_text = "".join(x["word"] for x in right)
                # Now add the current word
                cur_words.append(w)
                cur_text += word_text
        else:
            cur_words.append(w)
            cur_text += word_text

        # Comma/semicolon-based split (sentence-end already handled above)
        if word_text in _COMMA_PUNCT and len(cur_text) >= min_chars:
            _flush(cur_words, cur_text, True)
            cur_words = []
            cur_text = ""
            continue

        # Pause-based split
        if i > 0 and len(cur_text) >= min_chars:
            gap = w["start_sec"] - words[i - 1]["end_sec"]
            if gap >= pause_threshold:
                bp = _find_best_break(cur_words)
                if 0 <= bp < len(cur_words) - 1:
                    right = cur_words[bp + 1:]
                    left = cur_words[:bp + 1]
                    _flush(left, "".join(x["word"] for x in left), False)
                    cur_words = right
                    cur_text = "".join(x["word"] for x in right)

    _flush(cur_words, cur_text, False)

    # Filter empty lines
    lines = [ln for ln in lines if ln["text"].strip()]

    # --- Step 3: Merge very short fragments ---
    # Merge <=1 char fragments into previous line to avoid standalone single-char lines.
    # Don't merge >=2 char fragments to preserve sentence boundaries.
    merged: list[dict] = []
    for line in lines:
        txt = line["text"]
        if (merged
                and len(txt) <= 1
                and len(merged[-1]["text"]) + len(txt) <= max_chars):
            merged[-1]["text"] += txt
            merged[-1]["end_sec"] = line["end_sec"]
            continue
        merged.append(line)
    lines = merged

    # Clean up internal flag
    for line in lines:
        line.pop("ends_punct", None)

    return lines if lines else [{"text": text, "start_sec": words[0]["start_sec"], "end_sec": words[-1]["end_sec"]}]


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
        words_with_punct = _inject_punct(seg.words, seg.text)
        sub_lines = _smart_split(words_with_punct, seg.text, max_chars=25, start_sec=seg.start_sec, end_sec=seg.end_sec)
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
