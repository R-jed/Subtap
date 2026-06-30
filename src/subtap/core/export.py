"""Subtitle export: aligned.jsonl → SRT / ASS / TXT."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path

from subtap.core.clauses import identify_clause_boundaries, _CONJ_PAIRS
from subtap.core.itn import chinese_to_num
from subtap.core.phrases import mark_phrase_boundaries
from subtap.schemas.models import AlignedSegment, ASRSegment

_PUNCT_MAP = str.maketrans(
    ",.?!;:()",
    "，。？！；：（）",
)

# All punctuation (both half-width and full-width) for stripping
_ALL_PUNCT_RE = re.compile(r"[，。？！、；：“”‘’（）《》,.?!;:\"'()\[\]{}\-—…·]")

# Trailing words that should not appear at line end
_TRAILING_WORDS = {
    # 连词（双字）
    "但是",
    "所以",
    "因为",
    "而且",
    "不过",
    "可是",
    "然后",
    "或者",
    "于是",
    "因此",
    "虽然",
    # 单字连词
    "因",
    "则",
    "但",
    "所",
    "以",
    "才",
    "会",
    "又",
    "也",
    # 语气词
    "呃",
    "呢",
    "啊",
    "呀",
    "吧",
    "嘛",
    "哦",
    "嗯",
    "哈",
    "哎",
    # 代词/主语
    "我们",
    "它们",
    "它能",
    "它还",
    "他还",
    "她还",
    # 指示词
    "这个",
    "那个",
    "这些",
    "那些",
    "那这",
    "那还",
}


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
    """Remove all punctuation, preserving decimal points and ratios in numbers."""
    # Protect decimal points (e.g., 0.6秒)
    protected = re.sub(r"(\d)\.(\d)", r"\1<DECIMAL>\2", text)
    # Protect ratio colons (e.g., 21:9)
    protected = re.sub(r"(\d):(\d)", r"\1<RATIO>\2", protected)
    stripped = _ALL_PUNCT_RE.sub("", protected)
    return stripped.replace("<DECIMAL>", ".").replace("<RATIO>", ":")


def _fmt_srt_time(seconds: float) -> str:
    """Format seconds to SRT timestamp HH:MM:SS,mmm."""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_ass_time(seconds: float) -> str:
    """Format seconds to ASS timestamp H:MM:SS.cc."""
    seconds = max(0.0, seconds)
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


_PUNCT_CHARS = set("，。？！、；：" "''（）《》,.?!;:\"'()[]{}\\-—…·")

# 常见的跨行断词模式（单字+单字/多字组成词）
_SPLIT_WORD_PATTERNS = {
    ("虚", "化"),
    ("二", "八"),
    ("三", "百"),
    ("四", "十"),
    ("五", "千"),
    ("六", "万"),
    ("七", "亿"),
    ("微", "距"),
    ("功", "能"),
    ("像", "素"),
    ("过", "程"),
    ("眼", "镜"),
    ("画", "面"),
    ("屏", "幕"),
    ("时", "间"),
    ("空", "间"),
    ("体", "验"),
    ("系", "统"),
    ("完", "全"),
    ("已", "经"),
    ("可", "以"),
    ("不", "过"),
}


def _has_latin(s: str) -> bool:
    """字符串是否包含拉丁字母"""
    return any("A" <= c <= "Z" or "a" <= c <= "z" for c in s)


def _is_incomplete_word(
    tail: str, next_start: str, cross_sentence: bool = False
) -> bool:
    """检查 tail 是否是不完整词，next_start 能否组成完整词"""
    if not next_start:
        return False
    # 英文词组不拆分：跨句时不合并（避免 "Hello"+"World" 误合并）
    if not cross_sentence and (_has_latin(tail) or _has_latin(next_start[:1])):
        return True
    # 如果 tail + next_start 是常见断词模式
    if (tail, next_start[:1]) in _SPLIT_WORD_PATTERNS:
        return True
    # 如果 tail 是数字且 next_start 也是数字/单位
    if tail.isdigit() and (
        next_start[0].isdigit() or next_start[0] in "零一二两三四五六七八九十百千万亿"
    ):
        return True
    return False


def _fix_split_words(
    lines: list[dict], max_chars: int, cross_sentence: bool = False
) -> list[dict]:
    """修复跨行断词：如果行尾是不完整词，移到下一行"""
    if len(lines) < 2:
        return lines

    _MERGE_GAP = 0.3  # 秒：时间间隔小于此值才合并

    fixed = [{**lines[0]}]
    for i in range(1, len(lines)):
        prev = fixed[-1]
        curr = {**lines[i]}
        prev_text = prev["text"]
        curr_text = curr["text"]

        # 只在时间间隔较小时合并（同一句话内的断词）
        gap = curr.get("start_sec", 0) - prev.get("end_sec", 0)
        if gap > _MERGE_GAP:
            fixed.append(curr)
            continue

        # 尝试从 prev 末尾取 1-2 个字，检查是否能和 curr 开头组成完整词
        for take in (2, 1):
            if len(prev_text) <= take:
                continue
            tail = prev_text[-take:]
            if _is_incomplete_word(
                tail,
                curr_text[:2] if len(curr_text) >= 2 else curr_text,
                cross_sentence=cross_sentence,
            ):
                # 移动 tail 到 curr 开头
                prev["text"] = prev_text[:-take]
                curr["text"] = tail + curr_text
                break

        fixed.append(curr)

    # 过滤空行
    return [ln for ln in fixed if ln["text"].strip()]


def _filter_words_to_text(words: list[dict], text: str) -> list[dict]:
    """Filter aligned words to only include those present in text."""
    filtered = []
    for w in words:
        if w["word"] in text:
            filtered.append(w)
    return filtered if filtered else words


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
    """Split subtitle text using clause boundary detection.

    CORE CONSTRAINT: 绝不丢字。输入的每个字都必须出现在输出中。
    算法只做分割和移动，不做删除。

    Algorithm:
    1. Mark phrase boundaries via mark_phrase_boundaries()
    2. Identify clause boundaries via identify_clause_boundaries()
    3. Accumulate words; split at clause boundaries or max_chars
    """
    if not words:
        return [{"text": text, "start_sec": start_sec, "end_sec": end_sec}]

    _SENT_END = set("。！？.!?")
    _COMMA_PUNCT = set("，、,;")
    _NUM_CHARS = set("零一二两三四五六七八九十百千万亿")

    # --- Step 1: Mark phrase boundaries ---
    marked_words = mark_phrase_boundaries(words)

    # --- Step 2: Identify clause boundaries ---
    boundaries = identify_clause_boundaries(
        words, marked=marked_words, pause_threshold=pause_threshold
    )

    # --- Step 3: Greedy split using clause boundaries ---
    cur_text = ""
    lines: list[dict] = []
    cur_words: list[dict] = []
    _pending_prefix: list[dict] = []

    def _flush_line(
        words_to_flush: list[dict], text_to_flush: str, break_type: str = "other"
    ):
        """Flush a line, stripping trailing words."""
        if not words_to_flush:
            return
        # Strip trailing words (e.g. "但是", "这个") from line end
        for clen in (2, 1):
            if len(text_to_flush) > clen and text_to_flush[-clen:] in _TRAILING_WORDS:
                # Move conjunction to pending prefix
                stripped_words = words_to_flush[-clen:]
                remaining_words = words_to_flush[:-clen]
                remaining_text = text_to_flush[:-clen]
                if remaining_words:
                    lines.append(
                        {
                            "text": remaining_text,
                            "start_sec": remaining_words[0]["start_sec"],
                            "end_sec": remaining_words[-1]["end_sec"],
                            "break_type": break_type,
                        }
                    )
                # Store stripped words as pending prefix for next line
                nonlocal _pending_prefix
                _pending_prefix = stripped_words
                return
        # No trailing conjunction - flush as is
        lines.append(
            {
                "text": text_to_flush,
                "start_sec": words_to_flush[0]["start_sec"],
                "end_sec": words_to_flush[-1]["end_sec"],
                "break_type": break_type,
            }
        )

    i = 0
    while i < len(words):
        w = words[i]
        word_text = w["word"]

        # Apply pending prefix (conjunction stripped from previous line end)
        if _pending_prefix:
            cur_words = _pending_prefix + cur_words
            cur_text = "".join(x["word"] for x in cur_words)
            # Set prefix start time to current word's start
            for pw in _pending_prefix:
                pw["start_sec"] = w["start_sec"]
                pw["end_sec"] = w["start_sec"]
            _pending_prefix = []

        # Sentence-ending punctuation → flush and skip
        if word_text in _SENT_END:
            if cur_words:
                _flush_line(cur_words, cur_text, "sentence_end")
                cur_words = []
                cur_text = ""
            i += 1
            continue

        # Number sequence protection: if entering a number sequence,
        # check if the ENTIRE sequence would exceed max_chars.
        # If so, split before the sequence. If not, skip the sequence.
        if word_text in _NUM_CHARS:
            seq_start = i
            seq_end = i
            while seq_end < len(words) - 1 and words[seq_end + 1]["word"] in _NUM_CHARS:
                seq_end += 1
            seq_len = sum(len(words[j]["word"]) for j in range(seq_start, seq_end + 1))
            if seq_len >= max_chars:
                # Flush current line before the number sequence
                if cur_words:
                    _flush_line(cur_words, cur_text)
                    cur_words = []
                    cur_text = ""
            # Add all words in the number sequence
            for j in range(seq_start, seq_end + 1):
                cur_words.append(words[j])
                cur_text += words[j]["word"]
            # Skip to the end of the sequence
            i = seq_end + 1
            continue

        # Max chars check BEFORE adding (to avoid exceeding limit)
        if cur_text and len(cur_text) + len(word_text) > max_chars:
            # Flush current line before adding new word
            if cur_words:
                _flush_line(cur_words, cur_text)
                cur_words = []
                cur_text = ""

        # Check pause/conjunction boundaries BEFORE adding word
        # so the pause word starts the new line (not ends the old one)
        should_split_before = False
        split_bt = "other"

        if i < len(boundaries) and boundaries[i] is not None:
            b = boundaries[i]
            assert b is not None
            boundary_type, score = b

            # Pause boundary: split BEFORE this word if current line is long enough
            if boundary_type == "pause" and cur_text and len(cur_text) >= min_chars:
                line_starts_with_conj = any(
                    cur_text.startswith(conj) for conj in _CONJ_PAIRS
                )
                if not line_starts_with_conj:
                    should_split_before = True
                    split_bt = "pause"

            # Conjunction boundary: split BEFORE this word if there's a pause
            elif (
                boundary_type == "conjunction"
                and cur_text
                and len(cur_text) >= min_chars
            ):
                if i > 0:
                    gap = w["start_sec"] - words[i - 1]["end_sec"]
                    if gap >= pause_threshold:
                        line_starts_with_conj = any(
                            cur_text.startswith(conj) for conj in _CONJ_PAIRS
                        )
                        if not line_starts_with_conj:
                            should_split_before = True
                            split_bt = "conjunction"

            # Particle boundary: split BEFORE this word if line is long enough
            elif (
                boundary_type == "particle" and cur_text and len(cur_text) >= min_chars
            ):
                should_split_before = True
                split_bt = "particle"

        if should_split_before and cur_words:
            _flush_line(cur_words, cur_text, split_bt)
            cur_words = []
            cur_text = ""

        # Add word to current line
        cur_words.append(w)
        cur_text += word_text

        # Check if we should split AFTER this position
        should_split_after = False
        after_bt = "other"

        # Max chars check (exact match)
        if len(cur_text) >= max_chars:
            should_split_after = True

        # Clause boundary check (sentence_end, comma)
        if i < len(boundaries) and boundaries[i] is not None:
            b = boundaries[i]
            assert b is not None
            boundary_type, score = b
            if boundary_type == "sentence_end":
                should_split_after = True
                after_bt = "sentence_end"
            elif boundary_type == "comma":
                should_split_after = True
                after_bt = "comma"

        # Min chars check: skip soft split only if below min AND below max
        if (
            should_split_after
            and len(cur_text) < min_chars
            and len(cur_text) < max_chars
        ):
            if after_bt not in ("comma", "sentence_end"):
                should_split_after = False

        if should_split_after:
            _flush_line(cur_words, cur_text, after_bt)
            cur_words = []
            cur_text = ""

        i += 1

    # Prepend any pending prefix before the final flush
    if _pending_prefix:
        cur_words = _pending_prefix + cur_words
        cur_text = "".join(x["word"] for x in cur_words)
        _pending_prefix = []

    # Flush remaining words (bypass trailing-word strip to avoid data loss)
    if cur_words:
        lines.append(
            {
                "text": cur_text,
                "start_sec": cur_words[0]["start_sec"],
                "end_sec": cur_words[-1]["end_sec"],
                "break_type": "end",
            }
        )

    # Filter empty lines
    lines = [ln for ln in lines if ln["text"].strip()]

    # Merge very short fragments into adjacent lines
    # - ≤1 char: always merge (e.g. "的", "了")
    # - ≤2 char: merge unless previous line is a hard break
    #   Hard breaks: sentence_end, comma (these mark real boundaries)
    #   Soft breaks: pause, particle, conjunction, other (can merge across)
    _HARD_BREAKS = {"sentence_end", "comma"}
    merged: list[dict] = []
    for line in lines:
        txt = line["text"]
        if merged and len(txt) <= 2:
            prev = merged[-1]
            prev_bt = prev.get("break_type")
            # ≤1 char always merges; ≤2 char merges unless crossing hard break
            can_merge = len(txt) <= 1 or prev_bt not in _HARD_BREAKS
            if can_merge and len(prev["text"]) + len(txt) <= max_chars:
                prev["text"] += txt
                prev["end_sec"] = line["end_sec"]
                continue
        merged.append(line)
    lines = merged

    # Fix split words (跨行断词修复)
    lines = _fix_split_words(lines, max_chars)

    return (
        lines
        if lines
        else [
            {
                "text": text,
                "start_sec": words[0]["start_sec"],
                "end_sec": words[-1]["end_sec"],
            }
        ]
    )


class BaseExporter(ABC):
    """Base class for subtitle exporters."""

    def __init__(
        self,
        punctuation: bool = False,
        language: str = "zh",
        max_chars: int = 25,
        min_chars: int = 10,
    ):
        self.punctuation = punctuation
        self.language = language
        self.max_chars = max_chars
        self.min_chars = min_chars

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
        # Collect all sub_lines from all sentences
        all_subs: list[dict] = []
        for seg in sorted_segs:
            # Use aligned_text (pre-hotword) for word filtering to preserve word-level timing
            # Use text (post-hotword) for display
            word_filter_text = getattr(seg, "aligned_text", None) or seg.text
            words_with_punct = _inject_punct(
                _filter_words_to_text(seg.words, word_filter_text), seg.text
            )
            sub_lines = _smart_split(
                words_with_punct,
                word_filter_text,
                max_chars=self.max_chars,
                min_chars=self.min_chars,
                start_sec=seg.start_sec,
                end_sec=seg.end_sec,
            )
            # Apply hotword replacements to each sub_line (post-split)
            replacements = getattr(seg, "hotword_replacements", None)
            if replacements:
                for sub in sub_lines:
                    for alias, word in replacements.items():
                        sub["text"] = sub["text"].replace(alias, word)
            for sub in sub_lines:
                if sub["text"].strip():
                    all_subs.append(sub)

        # Cross-sentence fragment merge: merge ≤2 char fragments into adjacent lines
        # Only merge if:
        #   1. Previous line is longer than the fragment (avoids merging "A"+"B")
        #   2. Combined length ≤ max_chars
        #   3. Merge doesn't create trailing word at line end
        merged_subs: list[dict] = []
        for sub in all_subs:
            txt = sub["text"].strip()
            visible = _strip_punct(txt).replace(" ", "")
            if merged_subs and len(visible) <= 2:
                prev = merged_subs[-1]
                prev_visible = _strip_punct(prev["text"]).replace(" ", "")
                # Only merge into a longer line, not into another short line
                if (
                    len(prev_visible) > len(visible)
                    and len(prev_visible) + len(visible) <= self.max_chars
                ):
                    # Check: would merge create trailing word at line end?
                    merged_text = prev["text"].rstrip() + txt
                    merged_stripped = _strip_punct(merged_text).replace(" ", "")
                    creates_trailing = False
                    for tlen in (2, 1):
                        if (
                            len(merged_stripped) > tlen
                            and merged_stripped[-tlen:] in _TRAILING_WORDS
                        ):
                            creates_trailing = True
                            break
                    if not creates_trailing:
                        prev["text"] = merged_text
                        prev["end_sec"] = sub["end_sec"]
                        continue
            merged_subs.append(sub)

        # Merge standalone trailing words into the next line
        final_subs: list[dict] = []
        for i, sub in enumerate(merged_subs):
            txt = sub["text"].strip()
            visible = _strip_punct(txt).replace(" ", "")
            # If this is a standalone trailing word and next line exists
            if visible in _TRAILING_WORDS and i + 1 < len(merged_subs):
                nxt = merged_subs[i + 1]
                nxt_visible = _strip_punct(nxt["text"]).replace(" ", "")
                if len(visible) + len(nxt_visible) <= self.max_chars:
                    # Prepend trailing word to next line
                    nxt["text"] = txt + nxt["text"]
                    nxt["start_sec"] = sub["start_sec"]
                    continue
            final_subs.append(sub)
        merged_subs = final_subs

        # Fix cross-sentence word splits (e.g. "Feature" / "Beast")
        merged_subs = _fix_split_words(merged_subs, self.max_chars, cross_sentence=True)

        # Render SRT
        lines: list[str] = []
        for index, sub in enumerate(merged_subs, 1):
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

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
    max_chars: int = 25,
    min_chars: int = 10,
    punctuation: bool = False,
    language: str = "zh",
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

    exporter = exporter_cls(
        punctuation=punctuation,
        language=language,
        max_chars=max_chars,
        min_chars=min_chars,
    )
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


def _with_translated_text(segments: list[AlignedSegment]) -> list[AlignedSegment]:
    result: list[AlignedSegment] = []
    for segment in segments:
        if not segment.translated_text:
            raise ValueError(f"缺少翻译文本：{segment.sentence_id}")
        result.append(
            segment.model_copy(
                update={
                    "text": segment.translated_text,
                    "aligned_text": None,
                    "hotword_replacements": None,
                }
            )
        )
    return result


def _with_bilingual_text(
    segments: list[AlignedSegment],
    order: str,
) -> list[AlignedSegment]:
    result: list[AlignedSegment] = []
    for segment in segments:
        if not segment.translated_text:
            raise ValueError(f"缺少翻译文本：{segment.sentence_id}")
        if order == "source-first":
            text = f"{segment.text}\n{segment.translated_text}"
        elif order == "target-first":
            text = f"{segment.translated_text}\n{segment.text}"
        else:
            raise ValueError(f"未知双语字幕顺序：{order}")
        result.append(
            segment.model_copy(
                update={
                    "text": text,
                    "aligned_text": None,
                    "hotword_replacements": None,
                }
            )
        )
    return result


def run_final_exports(
    aligned_jsonl: Path,
    output_dir: Path,
    punctuation: bool = False,
    language: str = "zh",
    max_chars: int = 25,
    min_chars: int = 10,
    formats: set[str] | None = None,
    stem: str = "final",
    translate_to: str | None = None,
    bilingual: str = "off",
) -> dict:
    """Export aligned subtitles to the stable final.* output contract."""
    if not aligned_jsonl.exists():
        return run_export(aligned_jsonl, output_dir, fmt="srt", stem=stem)

    segments = load_aligned(aligned_jsonl)
    if not segments:
        raise ValueError(f"No aligned segments found in {aligned_jsonl}")

    if formats is None:
        formats = {"srt", "vtt", "json", "tsv"}

    output_dir.mkdir(parents=True, exist_ok=True)
    export_segments = segments
    source_path: Path | None = None
    if translate_to:
        if bilingual == "off":
            export_segments = _with_translated_text(segments)
        else:
            export_segments = _with_bilingual_text(segments, bilingual)
        source_path = output_dir / f"{stem}.source.srt"
        SRTExporter(
            punctuation=punctuation,
            language=language,
            max_chars=max_chars,
            min_chars=min_chars,
        ).export(segments, source_path)

    srt_path = output_dir / f"{stem}.srt"
    vtt_path = output_dir / f"{stem}.vtt"
    json_path = output_dir / f"{stem}.json"
    tsv_path = output_dir / f"{stem}.tsv"

    # Always write SRT
    srt_path.write_text(
        SRTExporter(
            punctuation=punctuation,
            language=language,
            max_chars=max_chars,
            min_chars=min_chars,
        ).render(export_segments),
        encoding="utf-8",
    )

    # VTT (opt-in)
    if "vtt" in formats:
        vtt_lines = ["WEBVTT", ""]
        vtt_index = 0
        for seg in sorted(export_segments, key=lambda s: s.start_sec):
            word_filter_text = getattr(seg, "aligned_text", None) or seg.text
            words_with_punct = _inject_punct(
                _filter_words_to_text(seg.words, word_filter_text), seg.text
            )
            sub_lines = _smart_split(
                words_with_punct,
                word_filter_text,
                max_chars=max_chars,
                min_chars=min_chars,
                start_sec=seg.start_sec,
                end_sec=seg.end_sec,
            )
            # Apply hotword replacements to each sub_line (post-split)
            replacements = getattr(seg, "hotword_replacements", None)
            if replacements:
                for sub in sub_lines:
                    for alias, word in replacements.items():
                        sub["text"] = sub["text"].replace(alias, word)
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

    # JSON (opt-in)
    if "json" in formats:
        final_payload = [_final_json_item(seg) for seg in export_segments]
        json_path.write_text(
            json.dumps(final_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # TSV (opt-in)
    if "tsv" in formats:
        tsv_lines = ["subtitle_id\tstart_sec\tend_sec\ttext"]
        for seg in sorted(export_segments, key=lambda s: s.start_sec):
            text = seg.text.replace("\t", " ").replace("\n", " ")
            tsv_lines.append(
                f"{seg.sentence_id}\t{seg.start_sec}\t{seg.end_sec}\t{text}"
            )
        tsv_path.write_text("\n".join(tsv_lines), encoding="utf-8")

    # Run log (opt-in)
    if "log" in formats:
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

    outputs = [str(srt_path)]
    if source_path:
        outputs.append(str(source_path))
    if "vtt" in formats:
        outputs.append(str(vtt_path))
    if "json" in formats:
        outputs.append(str(json_path))
    if "tsv" in formats:
        outputs.append(str(tsv_path))

    return {
        "output_path": str(srt_path),
        "outputs": outputs,
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
