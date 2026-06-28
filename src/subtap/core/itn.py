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
    r"|[零一二两三四五六七八九十百千万亿]*[十百千万亿][零一二两三四五六七八九十百千万亿]*(?![多余])"  # contains unit, not followed by 多/余
)


def _convert_number_str(s: str) -> str:
    """Convert a Chinese number string to Arabic digits.

    Handles: 零-九, 十-亿 compound numbers.
    """
    if not s:
        return s

    # Pure digit sequence (零-九 only, no units)
    if all(ch in _NUM_MAP for ch in s):
        return "".join(str(_NUM_MAP[ch]) for ch in s)

    # Compound number with units
    total = 0
    current = 0
    current_group = 0

    for ch in s:
        if ch in _NUM_MAP:
            current = _NUM_MAP[ch]
        elif ch in _UNIT_MAP:
            unit = _UNIT_MAP[ch]
            if unit >= 10000:
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
    return str(total) if total > 0 else s


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
