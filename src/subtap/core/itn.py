"""Chinese ITN (Inverse Text Normalization).

Converts Chinese number words to Arabic digits in text.

Strategy (by magnitude):
- 个/十/百/千: convert fully (六千四百九十九 → 6499)
- 万级: keep unit (一万两千 → 1.2万, 十二万 → 12万)
- 亿级: keep unit (一亿两千万 → 1.2亿)
- 万亿级: keep unit (一万亿 → 1万亿)
- 概数后缀: don't convert (一万多元, 两千余人, 三百左右)
- 成语/复合词: don't convert (百万富翁, 万元户)
- 纯数字序列: convert (二零二五 → 2025)
"""

from __future__ import annotations

import re

_NUM_MAP = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3,
    "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

_UNIT_MAP = {
    "十": 10, "百": 100, "千": 1000,
    "万": 10000, "亿": 100000000,
}

# 概数后缀：数字 + 这些词 = 不转换
_APPROX_SUFFIXES = set("多余左右上下来")

# 成语/复合词保护：这些词中的数字不转换
_IDIOMS = {"百万富翁", "万元户", "万元", "亿元", "十亿", "百亿", "千亿", "万亿"}


def _is_approx_context(text: str, match_start: int, match_end: int) -> bool:
    """Check if the matched number is in an approximate context."""
    # Check character after the match
    if match_end < len(text) and text[match_end] in _APPROX_SUFFIXES:
        return True
    return False


def _is_idiom(text: str, match_start: int, match_end: int) -> bool:
    """Check if the matched number is part of an idiom/compound word."""
    # Check 2-char window before and after for compound word patterns
    window_start = max(0, match_start - 2)
    window_end = min(len(text), match_end + 2)
    window = text[window_start:window_end]
    for idiom in _IDIOMS:
        if idiom in window and match_start >= window_start and match_end <= window_end:
            # Verify the idiom actually overlaps with our match
            idiom_pos = window.find(idiom)
            if idiom_pos >= 0:
                abs_start = window_start + idiom_pos
                abs_end = abs_start + len(idiom)
                if abs_start <= match_start and abs_end >= match_end:
                    return True
    return False


# Match number sequences:
# 1. 2+ pure digits: 二零一五、一二三
# 2. Digit(s) + unit(s): 十二、一万两千三百四十五、十万、三百
# Negative lookahead: 概数后缀 (多/余/左右/上下/来)
_NUM_RE = re.compile(
    r"[零一二两三四五六七八九]{2,}"  # 2+ pure digits
    r"|[零一二两三四五六七八九十百千万亿]*[十百千万亿][零一二两三四五六七八九十百千万亿]*(?![多余左右上下来])"
)


def _parse_total(s: str) -> int:
    """Parse Chinese number string to integer value."""
    total = 0
    current = 0
    current_group = 0
    for ch in s:
        if ch in _NUM_MAP:
            current = _NUM_MAP[ch]
        elif ch in _UNIT_MAP:
            unit = _UNIT_MAP[ch]
            if unit >= 10000:
                if current == 0 and current_group == 0:
                    current = 1  # 裸万/亿
                current_group += current
                total += current_group * unit
                current_group = 0
                current = 0
            else:
                if current == 0:
                    current = 1  # 裸十/百/千
                current_group += current * unit
                current = 0
    current_group += current
    total += current_group
    return total


def _sub_unit_parse(s: str) -> int:
    """Parse sub-unit portion (千/百/十 level) to integer."""
    if not s:
        return 0
    if all(ch in _NUM_MAP for ch in s):
        return int("".join(str(_NUM_MAP[ch]) for ch in s))
    total = 0
    current = 0
    current_group = 0
    for ch in s:
        if ch in _NUM_MAP:
            current = _NUM_MAP[ch]
        elif ch in _UNIT_MAP:
            unit = _UNIT_MAP[ch]
            if current == 0:
                current = 1  # 裸单位
            current_group += current * unit
            current = 0
    current_group += current
    total += current_group
    return total


def _convert_keep_unit(s: str) -> str:
    """Convert number with 万/亿, keeping the unit for readability.

    Handles compound levels: 万亿, 亿+万, 亿 alone, 万 alone.
    """
    # Split by 亿 first (highest level)
    if "亿" in s:
        idx = s.index("亿")
        yi_str = s[:idx]
        rest = s[idx + 1:]

        # Check for 万 in remainder (亿+万 combo, e.g. "一亿两千万")
        if "万" in rest:
            widx = rest.index("万")
            wan_str = rest[:widx]
            suffix = rest[widx + 1:]
        else:
            wan_str = ""
            suffix = rest

        # 万亿 compound: "一万亿" → "1万亿", "十万亿" → "10万亿"
        if "万" in yi_str:
            widx = yi_str.index("万")
            yi_wan_str = yi_str[:widx]  # digits before 万
            yi_wan_val = _sub_unit_parse(yi_wan_str) if yi_wan_str else 1
            if wan_val := _sub_unit_parse(wan_str) if wan_str else 0:
                # 万亿+万 combo: rare, treat as 亿+万
                val = yi_wan_val * 10000 + wan_val
                return f"{val}亿{suffix}"
            return f"{yi_wan_val}万亿{suffix}"

        yi_val = _sub_unit_parse(yi_str) if yi_str else 1
        wan_val = _sub_unit_parse(wan_str) if wan_str else 0

        if wan_val > 0:
            # 亿+万 combo: "一亿两千万" → "1.2亿"
            val = yi_val + wan_val / 10000
            val_str = f"{val:.4f}".rstrip("0").rstrip(".")
            return f"{val_str}亿{suffix}"
        else:
            return f"{yi_val}亿{suffix}"

    # Only 万
    if "万" in s:
        idx = s.index("万")
        wan_str = s[:idx]
        suffix = s[idx + 1:]

        wan_val = _sub_unit_parse(wan_str) if wan_str else 1

        # Check if suffix starts with a number (e.g., "五千" after "三万五千")
        if suffix and suffix[0] in _NUM_MAP:
            rest_val = _sub_unit_parse(suffix)
            if rest_val > 0:
                val = wan_val + rest_val / 10000
                val_str = f"{val:.4f}".rstrip("0").rstrip(".")
                return f"{val_str}万"
        return f"{wan_val}万{suffix}"

    return s


def _convert_number_str(s: str) -> str:
    """Convert a Chinese number string to Arabic digits.

    Strategy:
    - Pure digits: convert directly (二零一五 → 2025)
    - 万/亿 level: keep unit (一亿两千万 → 1.2亿)
    - 千/百/十 level: convert fully (六千四百九十九 → 6499)
    """
    if not s:
        return s

    # Pure digit sequence (零-九 only, no units)
    if all(ch in _NUM_MAP for ch in s):
        return "".join(str(_NUM_MAP[ch]) for ch in s)

    # 万/亿 level: keep unit
    if "万" in s or "亿" in s:
        return _convert_keep_unit(s)

    # 千/百/十 level: convert fully
    total = 0
    current = 0
    current_group = 0
    for ch in s:
        if ch in _NUM_MAP:
            current = _NUM_MAP[ch]
        elif ch in _UNIT_MAP:
            unit = _UNIT_MAP[ch]
            if current == 0:
                current = 1  # 裸单位 "十/百/千" → 1
            current_group += current * unit
            current = 0
    current_group += current
    total += current_group
    return str(total) if total > 0 else s


def chinese_to_num(text: str) -> str:
    """Convert Chinese number words to Arabic digits in text.

    Examples:
        "二零一五" → "2015"
        "一万两千三百四十五" → "1.2345万"
        "三点一四" → "3.14"
        "十二" → "12"
        "百万富翁" → "百万富翁" (protected)
        "一万多元" → "一万多元" (approximate)
    """
    if not text:
        return text

    # Handle 小数点: 三点一四 → 3.14
    text = re.sub(
        r"([零一二两三四五六七八九十百千万亿]+)点([零一二两三四五六七八九]+)",
        lambda m: _convert_number_str(m.group(1))
        + "."
        + _convert_number_str(m.group(2)),
        text,
    )

    # Handle number sequences with context protection
    def _replace(match):
        matched = match.group()
        start, end = match.start(), match.end()
        # Skip if in approximate context (一万多元, 三百左右)
        if _is_approx_context(text, start, end):
            return matched
        # Skip bare units followed by non-digit (万元, 亿元)
        if matched in ("万", "亿") and end < len(text) and text[end] not in _NUM_MAP:
            return matched
        # Skip idioms (百万富翁, 万元户)
        if _is_idiom(text, start, end):
            return matched
        return _convert_number_str(matched)

    text = _NUM_RE.sub(_replace, text)

    return text
