"""Chinese ITN (Inverse Text Normalization).

Converts Chinese number words to Arabic digits in text.
Adapted from Qwen3-ASR-GGUF's chinese_itn.py (simplified).
"""

from __future__ import annotations

import re

_NUM_MAP = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

_UNIT_MAP = {
    "十": 10,
    "百": 100,
    "千": 1000,
    "万": 10000,
    "亿": 100000000,
}

# Match meaningful number sequences only:
# 1. 2+ pure digits: 二零一五、一二三
# 2. Any sequence containing at least one unit (十百千万亿): 一万两千三百四十五、十万、三百
# Negative lookahead: skip when followed by 概数后缀 (多/余/左右/上下)
_NUM_RE = re.compile(
    r"[零一二两三四五六七八九]{2,}"  # 2+ pure digits
    r"|[零一二两三四五六七八九十百千万亿]+[十百千万亿][零一二两三四五六七八九十百千万亿]*(?![多余])"  # contains unit (at least 1 char before unit)
)


def _parse_total(s: str) -> int:
    """Parse full Chinese number string to integer value (万/亿 included)."""
    total = 0
    current = 0
    current_group = 0
    for ch in s:
        if ch in _NUM_MAP:
            current = _NUM_MAP[ch]
        elif ch in _UNIT_MAP:
            unit = _UNIT_MAP[ch]
            if unit >= 10000:
                if current == 0:
                    current = 1  # 裸单位 "万" → "一万"
                current_group += current
                total += current_group * unit
                current_group = 0
                current = 0
            else:
                if current == 0 and unit == 10:
                    current = 1
                current_group += current * unit
                current = 0
    current_group += current
    total += current_group
    return total


def _convert_number_str(s: str) -> str:
    """Convert a Chinese number string to Arabic digits.

    Strategy for readability in subtitles:
    - 万/亿 level: keep Chinese unit, convert digits above it
      "两千四百万" → "2400万", "一亿两千万" → "1.2亿"
    - 千/百/十 level: convert fully
      "六千四百九十九" → "6499"
    - Pure digits: convert directly
      "二零一五" → "2015"
    """
    if not s:
        return s

    # Pure digit sequence (零-九 only, no units)
    if all(ch in _NUM_MAP for ch in s):
        return "".join(str(_NUM_MAP[ch]) for ch in s)

    # Check if 万 or 亿 is present — if so, use "数字+单位" format
    has_wan = "万" in s
    has_yi = "亿" in s

    if has_yi or has_wan:
        # Calculate total value first — if small enough, convert fully
        total = _parse_total(s)
        if has_wan and not has_yi and total < 20000:
            # Small number with 万 (e.g. "一万两千九百九十九" = 12999)
            return str(total)
        return _convert_keep_unit(s)

    # Compound number without 万/亿: convert fully (千/百/十)
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


def _convert_keep_unit(s: str) -> str:
    """Convert number with 万/亿, keeping the unit for readability.

    Strategy: parse digits before 万/亿 independently, combine with decimal.

    Examples:
        "两千四百万" → "2400万"
        "两千五百七十四万" → "2574万"
        "一亿两千万" → "1.2亿"
        "一亿" → "1亿"
        "三万五千" → "3.5万"
    """
    # Split into 亿-part and 万-part
    yi_str = ""
    wan_str = ""
    suffix = ""

    if "亿" in s:
        idx = s.index("亿")
        yi_str = s[:idx]
        rest = s[idx + 1:]
        if "万" in rest:
            widx = rest.index("万")
            wan_str = rest[:widx]
            suffix = rest[widx + 1:]
        else:
            suffix = rest
    elif "万" in s:
        idx = s.index("万")
        wan_str = s[:idx]
        suffix = s[idx + 1:]

    yi_val = _sub_unit_parse(yi_str) if yi_str else 0
    wan_val = _sub_unit_parse(wan_str) if wan_str else 0

    # Build output: prefer "X.Y亿" or "X.Y万" for compact display
    if yi_val > 0 and wan_val > 0:
        # 亿+万 combo: "一亿两千万" → "1.2亿"
        val = yi_val + wan_val / 10000
        val_str = f"{val:.4f}".rstrip("0").rstrip(".")
        return f"{val_str}亿{suffix}"
    elif yi_val > 0:
        return f"{yi_val}亿{suffix}"
    elif wan_val > 0:
        # Check if there's a sub-万 remainder (e.g. "五千" after "万")
        if suffix and any(ch in _NUM_MAP or ch in _UNIT_MAP for ch in suffix[:1]):
            # "三万五千" → parse "五千" as 5000, fraction = 0.5
            rest_val = _sub_unit_parse(suffix)
            if rest_val > 0:
                val = wan_val + rest_val / 10000
                val_str = f"{val:.4f}".rstrip("0").rstrip(".")
                return f"{val_str}万"
        return f"{wan_val}万{suffix}"

    return s


def _sub_unit_parse(s: str) -> int:
    """Parse Chinese number (千/百/十 level) to integer."""
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
                current = 1  # 裸单位 "十/百/千" → 1
            current_group += current * unit
            current = 0
    current_group += current
    total += current_group
    return total


def chinese_to_num(text: str) -> str:
    """Convert Chinese number words to Arabic digits in text.

    Examples:
        "二零一五" → "2015"
        "一万两千三百四十五" → "12345"
        "三点一四" → "3.14"
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

    # Handle standalone number sequences
    text = _NUM_RE.sub(lambda m: _convert_number_str(m.group()), text)

    return text
