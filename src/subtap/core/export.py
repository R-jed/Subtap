"""Subtitle export: aligned.jsonl -> SRT / ASS / TXT."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from subtap.core.clauses import identify_clause_boundaries, _CONJ_PAIRS
from subtap.core.itn import chinese_to_num
from subtap.core.phrases import mark_phrase_boundaries
from subtap.core.text_utils import (
    normalize_punct,
    remove_cjk_spaces,
    strip_punct,
)
from subtap.core.word_boundaries import word_end_indices
from subtap.schemas.models import AlignedSegment, ASRSegment

logger = logging.getLogger(__name__)

# Sentence-ending punctuation (shared across split functions)
_SENT_END = frozenset("。！？.!?")

# Number characters for numeral sequence detection
_NUM_CHARS = frozenset("零一二两三四五六七八九十百千万亿")

# Comma / clause punctuation
_COMMA_PUNCT = frozenset("，、,;")

# Punctuation that introduces an explanation or apposition.
_CLAUSE_PUNCT = frozenset("：:—")

# Directional complements stay with the preceding verb in subtitle display.
_DIRECTIONAL_COMPLEMENTS = (
    "下来",
    "下去",
    "上来",
    "上去",
    "起来",
    "出来",
    "出去",
    "进来",
    "进去",
    "回来",
    "回去",
    "过来",
    "过去",
)

# One-character modifiers attach to the predicate that follows.
_PREFIX_MODIFIERS = frozenset("不没很更最太真挺蛮已曾还再又才都就也能会可要该将正")

# One-character locative suffixes stay with the noun before them.
_LOCATIVE_SUFFIXES = frozenset("上下内外中前后里")
_SPATIAL_SUFFIXES = frozenset("上下内外中里")

_PRONOUNS = ("我们", "你们", "他们", "她们", "它们", "我", "你", "他", "她", "它")
_OBJECT_INTRODUCERS = frozenset("比把被给对向跟和为从替让")

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


_PUNCT_CHARS = set("，。？！、；：''（）《》,.?!;:\"'()[]{}\\-—…·")

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


@dataclass
class IncompleteWordQuery:
    """Encapsulates parameters for incomplete-word detection."""

    tail: str
    next_start: str
    cross_sentence: bool = False
    prev_char: str = ""

    def is_incomplete(self) -> bool:
        """检查 tail 是否是不完整词，next_start 能否组成完整词"""
        if not self.next_start:
            return False
        # 标点结尾的 tail 不是断词（如 "e，" 是单词末尾+标点，不是断词）
        if self.tail and self.tail[-1] in _PUNCT_CHARS:
            return False
        # 英文单词保护：tail 含拉丁字母且 next_start 也含拉丁字母
        if (
            not self.cross_sentence
            and _has_latin(self.tail)
            and _has_latin(self.next_start[:1])
        ):
            if self.prev_char and _has_latin(self.prev_char):
                return False
            return True
        # 常见断词模式
        if (self.tail, self.next_start[:1]) in _SPLIT_WORD_PATTERNS:
            return True
        # 数字序列
        if self.tail.isdigit() and (
            self.next_start[0].isdigit() or self.next_start[0] in _NUM_CHARS
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
            # tail 前面的字符，用于判断 tail 是否在单词开头
            prev_char = prev_text[-(take + 1)] if len(prev_text) > take else ""
            if IncompleteWordQuery(
                tail=tail,
                next_start=curr_text[:2] if len(curr_text) >= 2 else curr_text,
                cross_sentence=cross_sentence,
                prev_char=prev_char,
            ).is_incomplete():
                if _content_len(tail + curr_text) > max_chars:
                    continue
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


def _normalize_display_spacing(text: str) -> str:
    """Ignore decorative CJK spacing but preserve Latin word separators."""
    chars: list[str] = []
    for index, char in enumerate(text):
        if not char.isspace():
            chars.append(char)
            continue
        previous = next(
            (
                candidate
                for candidate in reversed(text[:index])
                if not candidate.isspace()
            ),
            "",
        )
        following = next(
            (candidate for candidate in text[index + 1 :] if not candidate.isspace()),
            "",
        )
        if (
            previous.isascii()
            and previous.isalnum()
            and following.isascii()
            and following.isalnum()
            and (not chars or chars[-1] != " ")
        ):
            chars.append(" ")
    return "".join(chars)


def _reconstruct_display_text(words: list[dict], source_text: str) -> str:
    """Rebuild text while preserving only separators present in the source."""
    parts: list[str] = []
    cursor = 0
    for item in words:
        word = item["word"]
        position = source_text.find(word, cursor)
        if position >= 0:
            parts.append(
                "".join(char for char in source_text[cursor:position] if char.isspace())
            )
            cursor = position + len(word)
        parts.append(word)
    return "".join(parts)


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

    # Completeness check: warn if text characters were lost.
    reconstructed = _reconstruct_display_text(result, text)
    comparable_text = _normalize_display_spacing(text)
    comparable_reconstructed = _normalize_display_spacing(reconstructed)
    if comparable_reconstructed != comparable_text:
        logger.warning(
            "_inject_punct: 完整性校验失败，原始 %d 字符 vs 重建 %d 字符。"
            "原始='%s' 重建='%s'",
            len(text),
            len(reconstructed),
            text,
            reconstructed,
        )

    return result


def _flush_split_line(
    lines: list[dict],
    words_to_flush: list[dict],
    text_to_flush: str,
    break_type: str = "other",
) -> list[dict] | None:
    """Flush a line, stripping trailing words. Returns stripped words for pending prefix."""
    if not words_to_flush:
        return None
    for clen in (2, 1):
        if len(text_to_flush) > clen and text_to_flush[-clen:] in _TRAILING_WORDS:
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
            return stripped_words
    lines.append(
        {
            "text": text_to_flush,
            "start_sec": words_to_flush[0]["start_sec"],
            "end_sec": words_to_flush[-1]["end_sec"],
            "break_type": break_type,
        }
    )
    return None


def _greedy_split(
    words: list[dict],
    text: str,
    boundaries: Sequence[tuple[str, float | int] | None],
    max_chars: int,
    min_chars: int,
    pause_threshold: float,
) -> list[dict]:
    """Greedy accumulation split using clause boundaries."""
    lines: list[dict] = []
    cur_text = ""
    cur_words: list[dict] = []
    pending_prefix: list[dict] = []

    i = 0
    while i < len(words):
        w = words[i]
        word_text = w["word"]

        if pending_prefix:
            cur_words = pending_prefix + cur_words
            cur_text = "".join(x["word"] for x in cur_words)
            for pw in pending_prefix:
                pw["start_sec"] = w["start_sec"]
                pw["end_sec"] = w["start_sec"]
            pending_prefix = []

        if word_text in _SENT_END:
            if cur_words:
                stripped = _flush_split_line(lines, cur_words, cur_text, "sentence_end")
                if stripped:
                    pending_prefix = stripped
                cur_words = []
                cur_text = ""
            i += 1
            continue

        if word_text in _NUM_CHARS:
            seq_start = i
            seq_end = i
            while seq_end < len(words) - 1 and words[seq_end + 1]["word"] in _NUM_CHARS:
                seq_end += 1
            seq_len = sum(len(words[j]["word"]) for j in range(seq_start, seq_end + 1))
            if seq_len >= max_chars and cur_words:
                stripped = _flush_split_line(lines, cur_words, cur_text)
                if stripped:
                    pending_prefix = stripped
                cur_words = []
                cur_text = ""
            for j in range(seq_start, seq_end + 1):
                cur_words.append(words[j])
                cur_text += words[j]["word"]
            i = seq_end + 1
            continue

        if cur_text and len(cur_text) + len(word_text) > max_chars:
            if cur_words:
                stripped = _flush_split_line(lines, cur_words, cur_text)
                if stripped:
                    pending_prefix = stripped
                cur_words = []
                cur_text = ""

        should_split_before = False
        split_bt = "other"
        if i < len(boundaries) and boundaries[i] is not None:
            b = boundaries[i]
            assert b is not None
            boundary_type, score = b
            if boundary_type == "pause" and cur_text and len(cur_text) >= min_chars:
                if not any(cur_text.startswith(c) for c in _CONJ_PAIRS):
                    should_split_before = True
                    split_bt = "pause"
            elif (
                boundary_type == "conjunction"
                and cur_text
                and len(cur_text) >= min_chars
            ):
                if i > 0:
                    gap = w["start_sec"] - words[i - 1]["end_sec"]
                    if gap >= pause_threshold and not any(
                        cur_text.startswith(c) for c in _CONJ_PAIRS
                    ):
                        should_split_before = True
                        split_bt = "conjunction"
            elif (
                boundary_type == "particle" and cur_text and len(cur_text) >= min_chars
            ):
                should_split_before = True
                split_bt = "particle"

        if should_split_before and cur_words:
            stripped = _flush_split_line(lines, cur_words, cur_text, split_bt)
            if stripped:
                pending_prefix = stripped
            cur_words = []
            cur_text = ""

        if cur_text and _has_latin(cur_text[-1:]) and _has_latin(word_text[:1]):
            cur_text += " "
        cur_words.append(w)
        cur_text += word_text

        should_split_after = False
        after_bt = "other"
        if len(cur_text) >= max_chars:
            should_split_after = True
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
        if (
            should_split_after
            and len(cur_text) < min_chars
            and len(cur_text) < max_chars
        ):
            if after_bt not in ("comma", "sentence_end"):
                should_split_after = False
        if should_split_after:
            stripped = _flush_split_line(lines, cur_words, cur_text, after_bt)
            if stripped:
                pending_prefix = stripped
            cur_words = []
            cur_text = ""

        i += 1

    if pending_prefix:
        cur_words = pending_prefix + cur_words
        cur_text = "".join(x["word"] for x in cur_words)

    if cur_words:
        lines.append(
            {
                "text": cur_text,
                "start_sec": cur_words[0]["start_sec"],
                "end_sec": cur_words[-1]["end_sec"],
                "break_type": "end",
            }
        )

    return [ln for ln in lines if ln["text"].strip()]


def _smart_split(
    words: list[dict],
    text: str,
    max_chars: int = 25,
    min_chars: int = 10,
    pause_threshold: float = 0.2,
    start_sec: float = 0.0,
    end_sec: float = 0.0,
) -> list[dict]:
    """Split subtitle text using clause boundary detection.

    CORE CONSTRAINT: 绝不丢字。输入的每个字都必须出现在输出中。
    算法只做分割和移动，不做删除。
    """
    if not words:
        return [{"text": text, "start_sec": start_sec, "end_sec": end_sec}]

    marked_words = mark_phrase_boundaries(words)
    boundaries = identify_clause_boundaries(
        words, marked=marked_words, pause_threshold=pause_threshold
    )

    lines = _greedy_split(
        words, text, boundaries, max_chars, min_chars, pause_threshold
    )

    # Merge very short fragments (≤1 char always, ≤2 char unless hard break)
    _HARD_BREAKS = {"sentence_end", "comma"}
    merged: list[dict] = []
    for line in lines:
        txt = line["text"]
        if merged and len(txt) <= 2:
            prev = merged[-1]
            prev_bt = prev.get("break_type")
            can_merge = len(txt) <= 1 or prev_bt not in _HARD_BREAKS
            if can_merge and len(prev["text"]) + len(txt) <= max_chars:
                prev["text"] += txt
                prev["end_sec"] = line["end_sec"]
                continue
        merged.append(line)
    lines = merged
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


def _smart_split_v2(
    words: list[dict],
    text: str,
    max_chars: int = 25,
    min_chars: int = 10,
    pause_threshold: float = 0.2,
    start_sec: float = 0.0,
    end_sec: float = 0.0,
) -> list[dict]:
    """Split subtitle text using split-point enumeration + scoring.

    Subtitle Edit style: enumerate all legal split points, score each
    combination, pick the best. Replaces greedy accumulation with
    look-ahead optimization.

    CORE CONSTRAINT: 绝不丢字。输入的每个字都必须出现在输出中。

    Algorithm:
    1. Map source display text to alignment timing without inventing spaces
    2. Enumerate punctuation, pause, and linguistic word boundaries
    3. Dynamic programming: find optimal split minimizing cost function
    4. Post-merge: absorb short fragments into adjacent lines
    """
    if not words:
        return [{"text": text, "start_sec": start_sec, "end_sec": end_sec}]

    # --- Step 1: Preserve source display text and attach alignment timing ---
    # Aligner tokens are not word boundaries: Chinese is often one character per
    # token, while a Latin word can arrive as several tokens. Map source text to
    # timing tokens without inventing spaces or split points.
    display_chars = list(_normalize_display_spacing(text))
    display_char_map: list[tuple[str, int, bool] | None] = [None] * len(display_chars)
    cursor = 0
    previous_word_index = 0
    display_text = "".join(display_chars)
    for word_index, item in enumerate(words):
        word = item["word"]
        position = display_text.find(word, cursor)
        if position < 0:
            raise ValueError(
                f"字幕文本无法映射对齐词: word={word!r}, text={display_text!r}"
            )
        for index in range(cursor, position):
            if not display_chars[index].isspace():
                raise ValueError(
                    "字幕文本与对齐词不一致: "
                    f"未映射内容={display_text[cursor:position]!r}"
                )
            display_char_map[index] = (
                display_chars[index],
                previous_word_index,
                False,
            )
        for index in range(position, position + len(word)):
            display_char_map[index] = (
                display_chars[index],
                word_index,
                _has_latin(word),
            )
        cursor = position + len(word)
        previous_word_index = word_index

    for index in range(cursor, len(display_chars)):
        if not display_chars[index].isspace():
            raise ValueError(f"字幕文本存在未对齐尾部: {display_text[cursor:]!r}")
        display_char_map[index] = (
            display_chars[index],
            previous_word_index,
            False,
        )

    if any(item is None for item in display_char_map):
        raise ValueError("字幕文本与对齐时间映射不完整")
    mapped_chars = [item for item in display_char_map if item is not None]

    n = len(display_chars)

    if n == 0:
        return [{"text": text, "start_sec": start_sec, "end_sec": end_sec}]

    # --- Step 2: Enumerate legal split points ---
    linguistic_word_ends = word_end_indices(display_text)
    marked_words = mark_phrase_boundaries(words)

    def _inside_protected_phrase(index: int) -> bool:
        """Return whether splitting after index would break one phrase."""
        left_word = mapped_chars[index][1]
        right_word = mapped_chars[index + 1][1]
        while left_word >= 0 and words[left_word]["word"] in _PUNCT_CHARS:
            left_word -= 1
        while right_word < len(words) and words[right_word]["word"] in _PUNCT_CHARS:
            right_word += 1
        if left_word < 0 or right_word >= len(marked_words):
            return False
        left_role = marked_words[left_word].get("phrase_role")
        right_role = marked_words[right_word].get("phrase_role")
        return left_role in {"phrase_start", "phrase_mid"} and right_role in {
            "phrase_mid",
            "phrase_end",
        }

    # Build pause boundary set: positions where time gap >= pause_threshold
    pause_boundaries: set[int] = set()
    for wi in range(1, len(words)):
        gap = words[wi]["start_sec"] - words[wi - 1]["end_sec"]
        if gap >= pause_threshold:
            # Find the last display_char position belonging to word wi-1
            for j in range(n - 1, -1, -1):
                if j < len(mapped_chars) and mapped_chars[j][1] == wi - 1:
                    pause_boundaries.add(j)
                    break

    # split_after[i] = True if we can split AFTER position i
    split_after = [False] * n
    protected_boundaries: set[int] = set()
    for i in range(n - 1):
        ch = display_chars[i]
        next_ch = display_chars[i + 1]
        if _inside_protected_phrase(i):
            protected_boundaries.add(i)

        # Sentence-ending punctuation: always split after
        if ch in _SENT_END:
            split_after[i] = True
            continue

        # Comma punctuation: split after if enough content before
        if ch in _COMMA_PUNCT:
            split_after[i] = True
            continue

        # A colon or the final dash in an em-dash run is a semantic boundary.
        if ch in _CLAUSE_PUNCT and (ch != "—" or next_ch != "—"):
            split_after[i] = True
            continue

        # Space: split after (word boundary)
        if ch == " ":
            latin_start = i
            while latin_start > 0 and (
                display_chars[latin_start - 1] == " "
                or (
                    display_chars[latin_start - 1].isascii()
                    and display_chars[latin_start - 1].isalnum()
                )
            ):
                latin_start -= 1
            latin_end = i + 1
            while latin_end < n and (
                display_chars[latin_end] == " "
                or (
                    display_chars[latin_end].isascii()
                    and display_chars[latin_end].isalnum()
                )
            ):
                latin_end += 1
            latin_len = sum(
                char != " " for char in display_chars[latin_start:latin_end]
            )
            split_after[i] = latin_len > max_chars
            continue

        # Chinese/Latin transitions are useful boundaries around embedded
        # product names and technical terms.
        if (
            ch != " "
            and next_ch != " "
            and ch not in _PUNCT_CHARS
            and next_ch not in _PUNCT_CHARS
            and (
                (_has_latin(ch) and not _has_latin(next_ch))
                or (not _has_latin(ch) and _has_latin(next_ch))
            )
        ):
            split_after[i] = True
            continue

        # Keep a complete numeral together so per-cue ITN cannot reinterpret
        # fragments such as "两千" + "四百万" as unrelated numbers.
        if (ch.isdigit() or ch in _NUM_CHARS) and (
            next_ch.isdigit() or next_ch in _NUM_CHARS
        ):
            continue

        # Pause boundary: split after if time gap is large enough
        if i in pause_boundaries:
            split_after[i] = True
            continue

        # CJK character boundary: only split at a linguistic word boundary.
        if (
            not _has_latin(ch)
            and ch not in _PUNCT_CHARS
            and not _has_latin(next_ch)
            and next_ch not in _PUNCT_CHARS
            and next_ch != " "
        ):
            if i + 1 in linguistic_word_ends:
                split_after[i] = True

    # Guarantee a legal path under the configured width. Natural boundaries
    # remain preferred; an overlong indivisible token is cut only when no such
    # boundary exists within one line.
    forced_start = 0
    for i in range(n - 1):
        if split_after[i]:
            forced_start = i + 1
            continue
        candidate = "".join(display_chars[forced_start : i + 2])
        if _content_len(candidate) <= max_chars:
            continue
        forced_boundary = i
        if display_chars[i + 1] in _PUNCT_CHARS and i > forced_start:
            forced_boundary = i - 1
        split_after[forced_boundary] = True
        forced_start = forced_boundary + 1

    # --- Step 3: Dynamic programming for optimal split ---
    # dp[i] = min cost to split display_chars[0:i+1]
    # parent[i] = best split position before i
    INF = float("inf")
    dp = [INF] * (n + 1)
    parent = [-1] * (n + 1)
    dp[0] = 0

    for end in range(1, n + 1):
        for start in range(max(0, end - max_chars * 2), end):
            if start > 0 and not split_after[start - 1]:
                continue
            seg_len = end - start
            if seg_len > max_chars * 2:
                continue

            # Build segment text
            seg_text = "".join(display_chars[start:end])
            visible_len = _content_len(seg_text)
            if visible_len > max_chars:
                continue

            # Cost function
            cost = dp[start] + _split_cost(
                seg_text,
                seg_len,
                max_chars,
                min_chars,
                start,
                end,
                n,
                display_chars,
                mapped_chars,
                protected_boundaries,
                pause_boundaries,
            )

            if cost < dp[end]:
                dp[end] = cost
                parent[end] = start

    # --- Step 4: Reconstruct split positions ---
    splits: list[int] = []
    pos = n
    while pos > 0:
        prev = parent[pos]
        if prev < 0:
            break
        splits.append(prev)
        pos = prev
    splits.reverse()
    splits.append(n)

    # --- Step 5: Build output lines ---
    def _interpolated_token_boundary(boundary: int) -> float | None:
        if boundary <= 0 or boundary >= n:
            return None
        word_index = mapped_chars[boundary - 1][1]
        if mapped_chars[boundary][1] != word_index or word_index >= len(words):
            return None
        token_positions = [
            index
            for index, mapped in enumerate(mapped_chars)
            if mapped[1] == word_index and not display_chars[index].isspace()
        ]
        if not token_positions:
            return None
        consumed = sum(index < boundary for index in token_positions)
        fraction = consumed / len(token_positions)
        word = words[word_index]
        return word["start_sec"] + (word["end_sec"] - word["start_sec"]) * fraction

    lines: list[dict] = []
    for i in range(len(splits)):
        seg_start = splits[i - 1] if i > 0 else 0
        seg_end = splits[i]
        seg_text = "".join(display_chars[seg_start:seg_end]).strip()

        # Find word indices in this segment
        word_indices = set()
        for j in range(seg_start, seg_end):
            if j < len(mapped_chars):
                word_indices.add(mapped_chars[j][1])

        if not word_indices:
            continue

        # Timestamps from words
        seg_words = [words[wi] for wi in sorted(word_indices) if wi < len(words)]
        if seg_words:
            line_start = seg_words[0]["start_sec"]
            line_end = seg_words[-1]["end_sec"]
            interpolated_start = _interpolated_token_boundary(seg_start)
            interpolated_end = _interpolated_token_boundary(seg_end)
            if interpolated_start is not None:
                line_start = interpolated_start
            if interpolated_end is not None:
                line_end = interpolated_end
        else:
            line_start = start_sec
            line_end = end_sec

        lines.append(
            {
                "text": seg_text,
                "start_sec": line_start,
                "end_sec": line_end,
            }
        )

    # --- Step 6: Post-merge short fragments ---
    lines = _merge_short_fragments(lines, min_chars, max_chars)

    return (
        lines if lines else [{"text": text, "start_sec": start_sec, "end_sec": end_sec}]
    )


def _split_cost(
    seg_text: str,
    seg_len: int,
    max_chars: int,
    min_chars: int,
    start: int,
    end: int,
    total_len: int,
    display_chars: list[str],
    display_char_map: list[tuple[str, int, bool]] | None = None,
    protected_boundaries: set[int] | None = None,
    pause_boundaries: set[int] | None = None,
) -> float:
    """Cost function for a single segment. Lower is better."""
    cost = 0.0

    # Score the text users will actually see. Chinese numerals often shrink
    # substantially during ITN (e.g. 两千五百七十四 -> 2574).
    visible_len = _content_len(seg_text)

    # Penalty for exceeding max_chars
    if visible_len > max_chars:
        cost += (visible_len - max_chars) * 20.0

    # A short orphan line creates more editing work than a slightly earlier,
    # balanced break in the same sentence.
    starts_new_sentence = start > 0 and display_chars[start - 1] in _SENT_END
    starts_after_pause = (
        start > 0 and pause_boundaries and start - 1 in pause_boundaries
    )
    starts_after_comma = start > 0 and display_chars[start - 1] in _COMMA_PUNCT
    complete_short_comma_clause = starts_after_comma and visible_len >= max(
        6, min_chars - 4
    )
    ends_sentence = bool(seg_text) and seg_text[-1] in _SENT_END
    complete_standalone_sentence = ends_sentence and (start == 0 or starts_new_sentence)
    if (
        visible_len < min_chars
        and (start > 0 or end < total_len)
        and not (
            starts_new_sentence
            or starts_after_pause
            or complete_short_comma_clause
            or complete_standalone_sentence
        )
    ):
        cost += (min_chars - visible_len) * 8.0

    # Bonus for ending at sentence-ending punctuation (strong)
    if seg_text and seg_text[-1] in "。！？.!?":
        cost -= 8.0
    # Bonus for ending at comma
    elif seg_text and seg_text[-1] in "，,;":
        cost -= 4.0
    elif seg_text and seg_text[-1] == "、":
        cost += 2.0
    elif seg_text and seg_text[-1] in _CLAUSE_PUNCT:
        cost -= 3.0

    # Penalty for ending mid-word (last char is Latin, next is Latin)
    if end < total_len and seg_text:
        last_ch = seg_text[-1]
        next_ch = display_chars[end] if end < len(display_chars) else ""
        if (
            _has_latin(last_ch)
            and _has_latin(next_ch)
            and last_ch != " "
            and next_ch != " "
        ):
            cost += 20.0  # Heavy penalty for mid-word split

    # Structural particles belong with the following head word.
    if seg_text and seg_text[-1] in "的得地":
        cost += 8.0
    if seg_text and seg_text[-1] in _PREFIX_MODIFIERS:
        cost += 8.0
    if seg_text and seg_text[-1] in _SPATIAL_SUFFIXES:
        cost -= 4.0
    if any(seg_text.endswith(word) for word in _DIRECTIONAL_COMPLEMENTS):
        cost -= 8.0
    if any(seg_text.rstrip().endswith(word) for word in _TRAILING_WORDS):
        cost += 20.0

    if end < total_len:
        following = "".join(display_chars[end : end + 2])
        if following in _DIRECTIONAL_COMPLEMENTS:
            cost += 8.0
        following_text = "".join(display_chars[end : end + 3])
        previous_char = display_chars[end - 1] if end > 0 else ""
        if previous_char not in _OBJECT_INTRODUCERS and any(
            following_text.startswith(pronoun) for pronoun in _PRONOUNS
        ):
            cost -= 10.0
        if display_chars[end] in "的得地":
            cost += 8.0
        if display_chars[end] in _LOCATIVE_SUFFIXES:
            cost += 8.0

        # Spaces are legal boundaries, but prefer keeping adjacent Latin words
        # together when the configured width allows it.
        if seg_text.endswith(" "):
            previous_visible = next(
                (char for char in reversed(seg_text[:-1]) if char != " "), ""
            )
            next_visible = display_chars[end]
            if (
                previous_visible.isascii()
                and previous_visible.isalnum()
                and next_visible.isascii()
                and next_visible.isalnum()
            ):
                cost += 6.0

    # Penalty for splitting within the same word (CJK compound words)
    if display_char_map and end < len(display_char_map) and end > 0:
        last_wi = display_char_map[end - 1][1]
        next_wi = display_char_map[end][1]
        if last_wi == next_wi:
            cost += 15.0  # Heavy penalty for splitting within same word

    # Prefer phrase integrity, but keep the boundary legal so a long phrase can
    # still obey the configured subtitle width.
    if end < total_len and protected_boundaries and end - 1 in protected_boundaries:
        cost += 12.0

    # Balance penalty: mild, prefers lines closer to target length
    target = (max_chars + min_chars) / 2
    cost += abs(visible_len - target) * 0.2

    return cost


def _merge_short_fragments(
    lines: list[dict], min_chars: int, max_chars: int
) -> list[dict]:
    """Merge lines shorter than min_chars into adjacent lines.

    Never merge lines ending with sentence-ending punctuation (。！？.!?)
    since those are intentional semantic boundaries.
    """
    if len(lines) <= 1:
        return lines

    # Forward pass: merge short lines into next line
    merged: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        text = line["text"]
        visible_len = _content_len(text)

        # Don't merge lines ending with sentence-ending punctuation
        ends_with_sent = text.rstrip() and text.rstrip()[-1] in _SENT_END

        if visible_len < min_chars and not ends_with_sent and i + 1 < len(lines):
            # Try merging with next line
            next_line = lines[i + 1]
            combined_len = visible_len + _content_len(next_line["text"])
            if combined_len <= max_chars:
                # Merge into next line
                lines[i + 1] = {
                    "text": text + next_line["text"],
                    "start_sec": line["start_sec"],
                    "end_sec": next_line["end_sec"],
                }
                i += 1
                continue
            elif merged:
                # Try merging with previous line
                prev = merged[-1]
                prev_text = prev["text"]
                prev_ends_sent = (
                    prev_text.rstrip() and prev_text.rstrip()[-1] in _SENT_END
                )
                prev_len = _content_len(prev_text)
                if prev_len + visible_len <= max_chars and not prev_ends_sent:
                    merged[-1] = {
                        "text": prev_text + text,
                        "start_sec": prev["start_sec"],
                        "end_sec": line["end_sec"],
                    }
                    i += 1
                    continue

        merged.append(line)
        i += 1

    return merged


def _content_len(text: str) -> int:
    """Length of semantic content after the export-time transformations."""
    return len(chinese_to_num(text).replace(" ", ""))


def _reconcile_tiny_overlaps(
    lines: list[dict], tolerance_sec: float = 0.1
) -> list[dict]:
    """Share a boundary for harmless aligner jitter; reject real overlaps."""
    reconciled = [{**line} for line in lines]
    for previous, current in zip(reconciled, reconciled[1:]):
        overlap = previous["end_sec"] - current["start_sec"]
        if overlap <= 0:
            continue
        if overlap > tolerance_sec:
            raise ValueError(
                f"SRT 交付检查失败：字幕时间轴重叠 {overlap:.3f}s，超过可校正范围"
            )
        boundary = (previous["end_sec"] + current["start_sec"]) / 2
        if boundary <= previous["start_sec"] or boundary >= current["end_sec"]:
            raise ValueError("字幕时间轴重叠导致非正时长")
        logger.debug("校正相邻字幕 %.3fs 的对齐器边界抖动", overlap)
        previous["end_sec"] = boundary
        current["start_sec"] = boundary
    return reconciled


def _process_segment(
    seg: AlignedSegment,
    max_chars: int = 25,
    min_chars: int = 10,
) -> list[dict]:
    """Common pipeline: segment -> list of subtitle dicts (text + timestamps).

    Encapsulates: _filter_words_to_text -> _inject_punct -> _smart_split_v2
    -> hotword replacements. Returns raw sub_lines (no text processing).
    Callers apply chinese_to_num / normalize / strip / remove_cjk_spaces
    after any post-processing (e.g. _post_process_fragments).
    """
    word_filter_text = getattr(seg, "aligned_text", None) or seg.text
    words_with_punct = _inject_punct(
        _filter_words_to_text(seg.words, word_filter_text), word_filter_text
    )
    sub_lines = _smart_split_v2(
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
    return sub_lines


def _post_process_fragments(
    lines: list[dict],
    max_chars: int,
    min_chars: int = 10,
    pause_threshold: float = 0.2,
) -> list[dict]:
    """Three-layer post-processing in a single pass.

    Merges: cross-sentence fragment merge, standalone trailing word merge,
    and _fix_split_words. Called after _process_segment for SRT rendering.
    """
    # Layer 1: Cross-sentence fragment merge
    merged_subs: list[dict] = []
    for sub in lines:
        txt = sub["text"].strip()
        visible_len = _content_len(txt)
        if merged_subs and visible_len <= min_chars - 1:
            prev = merged_subs[-1]
            prev_len = _content_len(prev["text"])
            prev_text = prev["text"].rstrip()
            current_ends_sentence = bool(txt) and txt[-1] in _SENT_END
            has_real_pause = (
                sub["start_sec"] - prev["end_sec"] >= pause_threshold - 1e-6
            )
            preserve_semantic_boundary = bool(prev_text) and (
                prev_text[-1] in _SENT_END
                or has_real_pause
                or (prev_text[-1] in _COMMA_PUNCT and current_ends_sentence)
            )
            if (
                not preserve_semantic_boundary
                and prev_len > visible_len
                and prev_len + visible_len <= max_chars
            ):
                merged_text = prev["text"].rstrip() + txt
                merged_stripped = strip_punct(merged_text).replace(" ", "")
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

    # Layer 2: Merge standalone trailing words into the next line
    final_subs: list[dict] = []
    for i, sub in enumerate(merged_subs):
        txt = sub["text"].strip()
        visible_text = strip_punct(txt).replace(" ", "")
        visible_len = _content_len(txt)
        if (
            visible_text in _TRAILING_WORDS
            and (not txt or txt[-1] not in _SENT_END)
            and i + 1 < len(merged_subs)
            and merged_subs[i + 1]["start_sec"] - sub["end_sec"]
            < pause_threshold - 1e-6
        ):
            nxt = merged_subs[i + 1]
            nxt_len = _content_len(nxt["text"])
            if visible_len + nxt_len <= max_chars:
                nxt["text"] = txt + nxt["text"]
                nxt["start_sec"] = sub["start_sec"]
                continue
        final_subs.append(sub)

    # Layer 3: Fix cross-sentence word splits
    return _fix_split_words(final_subs, max_chars, cross_sentence=True)


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

    def export(self, segments: list[AlignedSegment], output_path: Path) -> Path:
        """Write SRT subtitle file and reject broken timing."""
        from subtap.core.subtitle_quality import validate_srt_delivery

        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = self.render(segments)
        report = validate_srt_delivery(content)
        if not report.ok:
            raise ValueError(f"SRT 交付检查失败：{report}")
        output_path.write_text(content, encoding="utf-8")
        return output_path

    def render(self, segments: list[AlignedSegment]) -> str:
        sorted_segs = sorted(segments, key=lambda s: s.start_sec)
        raw_subs: list[dict] = []
        for seg in sorted_segs:
            raw_subs.extend(
                _process_segment(
                    seg, max_chars=self.max_chars, min_chars=self.min_chars
                )
            )
        all_subs = [
            sub
            for sub in _post_process_fragments(raw_subs, self.max_chars, self.min_chars)
            if sub["text"].strip()
        ]
        all_subs = _reconcile_tiny_overlaps(all_subs)

        # Text processing + render SRT
        lines: list[str] = []
        for index, sub in enumerate(all_subs, 1):
            start = _fmt_srt_time(sub["start_sec"])
            end = _fmt_srt_time(sub["end_sec"])
            text = chinese_to_num(sub["text"])
            if self.punctuation:
                text = normalize_punct(text, self.language)
            else:
                text = strip_punct(text)
            text = remove_cjk_spaces(text)
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
        # TXTExporter 不需要 punctuation/language/max_chars/min_chars 等配置
        # 接受 kwargs 是为了与 run_export() 的统一调用接口保持一致
        pass

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
    if not aligned_jsonl.exists():
        raise FileNotFoundError(f"aligned.jsonl 文件不存在: {aligned_jsonl}")

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
        "text": remove_cjk_spaces(seg.text),
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
                    "words": [],
                }
            )
        )
    return result


def _without_alignment_metadata(segments: list[AlignedSegment]) -> list[AlignedSegment]:
    return [
        segment.model_copy(
            update={
                "aligned_text": None,
                "hotword_replacements": None,
                "words": [],
            }
        )
        for segment in segments
    ]


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
                    "words": [],
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
        raise FileNotFoundError(f"aligned.jsonl 文件不存在: {aligned_jsonl}")

    segments = load_aligned(aligned_jsonl)
    if not segments:
        raise ValueError(f"No aligned segments found in {aligned_jsonl}")

    if formats is None:
        formats = {"srt", "vtt", "json", "tsv"}

    output_dir.mkdir(parents=True, exist_ok=True)
    srt_exporter = SRTExporter(
        punctuation=punctuation,
        language=language,
        max_chars=max_chars,
        min_chars=min_chars,
    )
    export_segments = segments
    source_path: Path | None = None
    if translate_to:
        if bilingual == "off":
            export_segments = _with_translated_text(segments)
        else:
            export_segments = _with_bilingual_text(segments, bilingual)
        source_path = output_dir / f"{stem}.source.srt"
        srt_exporter.export(_without_alignment_metadata(segments), source_path)
    srt_path = output_dir / f"{stem}.srt"
    vtt_path = output_dir / f"{stem}.vtt"
    json_path = output_dir / f"{stem}.json"
    tsv_path = output_dir / f"{stem}.tsv"

    # Always write SRT through the delivery quality gate.
    srt_exporter.export(export_segments, srt_path)

    # VTT (opt-in)
    if "vtt" in formats:
        vtt_lines = ["WEBVTT", ""]
        vtt_index = 0
        for seg in sorted(export_segments, key=lambda s: s.start_sec):
            sub_lines = _process_segment(seg, max_chars=max_chars, min_chars=min_chars)
            for sub in sub_lines:
                if not sub["text"].strip():
                    continue
                vtt_index += 1
                text = chinese_to_num(sub["text"])
                if punctuation:
                    text = normalize_punct(text, language)
                else:
                    text = strip_punct(text)
                text = remove_cjk_spaces(text)
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
            text = remove_cjk_spaces(seg.text).replace("\t", " ").replace("\n", " ")
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
