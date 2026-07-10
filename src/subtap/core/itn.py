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

# 单位缩写映射：中文单位 → 缩写（仅度量衡单位，货币/量词保持中文）
_UNIT_ABBREV = {
    "毫米": "mm",
    "厘米": "cm",
    "千米": "km",
    "米": "m",
    "千克": "kg",
    "克": "g",
}

# 阿拉伯数字+中文单位 → 缩写单位（最长匹配优先）
_UNIT_NORM_RE = re.compile(r"(\d+)(毫米|厘米|千米|米|千克|克)")

# 成语/复合词保护：这些词中的数字不转换
_IDIOMS = {"百万富翁", "万元户", "万元", "亿元", "十亿", "百亿", "千亿", "万亿"}

# 概数前缀
_APPROX_PREFIXES = ("上", "下", "近", "约", "大概", "差不多", "超过", "不到", "将近")

# 概数量词
_APPROX_UNITS = "[个只张条块元万千百十秒分米克斤两]"

# 阿拉伯数字 → 中文数字映射（用于概数转换）
_ARABIC_TO_CHINESE = {
    0: "零",
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
}

# 大单位映射
_MAGNITUDE_UNITS = [
    (100000000, "亿"),
    (10000, "万"),
    (1000, "千"),
    (100, "百"),
    (10, "十"),
]


def _arabic_to_chinese(n: int) -> str:
    """将阿拉伯数字转为中文数字（简洁形式）。

    Examples:
        1000 → 千, 100 → 百, 3000 → 三千, 5 → 五
    """
    if n == 0:
        return "零"
    parts = []
    for mag, unit in _MAGNITUDE_UNITS:
        if n >= mag:
            count = n // mag
            n = n % mag
            if mag >= 10000:
                # 万/亿级别用递归
                parts.append(_arabic_to_chinese(count) + unit)
            elif count == 1 and mag >= 10:
                parts.append(unit)  # 裸单位：千、百、十
            else:
                parts.append(_ARABIC_TO_CHINESE[count] + unit)
    if n > 0:
        parts.append(_ARABIC_TO_CHINESE[n])
    return "".join(parts)


# 概数模式：前缀 + 数字（阿拉伯或中文） + 量词
# 在 _NUM_RE 之后使用，此时中文数字已转为阿拉伯数字
_APPROX_RE = re.compile(
    r"("
    + "|".join(_APPROX_PREFIXES)
    + r")([\d零一二两三四五六七八九十百千万亿]+)("
    + _APPROX_UNITS
    + r")"
)

# 小数点缺失模式：0开头的数字 + 时间/度量单位
_DECIMAL_DOT_RE = re.compile(r"(?<!\d)0(\d+)(秒|分|米|克|斤|两|元|块|度)")

# 比例号模式：数字 + 比 + 数字（如 三十二比九 → 32:9）
_RATIO_RE = re.compile(
    r"(\d+|[一二两三四五六七八九十百千万亿]+)比(\d+|[一二两三四五六七八九十百千万亿]+)"
)


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
# No negative lookahead — numbers are always converted even before approximate suffixes
# (一千多 → 1000多, 三百左右 → 300左右)
_NUM_RE = re.compile(
    r"[零一二两三四五六七八九]{2,}"  # 2+ pure digits
    r"|[零一二两三四五六七八九十百千万亿]*[十百千万亿][零一二两三四五六七八九十百千万亿]*"
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
        rest = s[idx + 1 :]

        # Check for 万 in remainder (亿+万 combo, e.g. "一亿两千万")
        if "万" in rest:
            widx = rest.index("万")
            wan_str = rest[:widx]
            suffix = rest[widx + 1 :]
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
            ratio = float(yi_val) + float(wan_val) / 10000
            val_str = f"{ratio:.4f}".rstrip("0").rstrip(".")
            return f"{val_str}亿{suffix}"
        else:
            return f"{yi_val}亿{suffix}"

    # Only 万
    if "万" in s:
        idx = s.index("万")
        wan_str = s[:idx]
        suffix = s[idx + 1 :]

        wan_val = _sub_unit_parse(wan_str) if wan_str else 1

        # Check if suffix starts with a number (e.g., "五千" after "三万五千")
        if suffix and suffix[0] in _NUM_MAP:
            rest_val = _sub_unit_parse(suffix)
            if rest_val > 0:
                # Clean multiple of 1000 → keep 万 unit (一万五千 → 1.5万)
                # Otherwise → full number (一万两千三百四十五 → 12345)
                if rest_val % 1000 == 0:
                    ratio = float(wan_val) + float(rest_val) / 10000
                    val_str = f"{ratio:.4f}".rstrip("0").rstrip(".")
                    return f"{val_str}万"
                else:
                    total = wan_val * 10000 + rest_val
                    return str(total)
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

    # 万/亿 level: always keep unit for readability (一万两千 → 1.2万)
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

    # Handle 百分之X → X%（必须在主数字转换之前）
    text = re.sub(
        r"百分之([零一二两三四五六七八九十百千万亿]+)",
        lambda m: str(_parse_total(m.group(1))) + "%",
        text,
    )

    # Handle 月/日: 八月 → 8月, 六日 → 6日, 十二月 → 12月
    text = re.sub(
        r"([零一二两三四五六七八九十]+)(月|日|号)",
        lambda m: str(_parse_total(m.group(1))) + m.group(2),
        text,
    )

    # Handle 小数点缺失: 06秒 → 0.6秒
    # 比例号：X比Y → X:Y
    def _cn_to_arabic(s):
        """中文数字/阿拉伯数字混合 → 纯阿拉伯"""
        if s.isdigit():
            return s
        # 检查是否全是中文数字字符
        cn_chars = set("零一二两三四五六七八九十百千万亿")
        if all(c in cn_chars for c in s):
            return str(_parse_total(s))
        # 混合情况：逐字转换
        result = []
        for ch in s:
            if ch in _NUM_MAP:
                result.append(str(_NUM_MAP[ch]))
            else:
                result.append(ch)
        return "".join(result) if result else s

    def _ratio_repl(m):
        left = _cn_to_arabic(m.group(1))
        right = _cn_to_arabic(m.group(2))
        return f"{left}:{right}"

    text = _RATIO_RE.sub(_ratio_repl, text)

    text = _DECIMAL_DOT_RE.sub(
        lambda m: "0." + m.group(1) + m.group(2),
        text,
    )

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
        # Skip bare units followed by non-digit (万元, 亿元)
        if matched in ("万", "亿") and end < len(text) and text[end] not in _NUM_MAP:
            return matched
        # Skip idioms (百万富翁, 万元户)
        if _is_idiom(text, start, end):
            return matched
        return _convert_number_str(matched)

    text = _NUM_RE.sub(_replace, text)

    # Handle 概数前缀 + 数字: 上1000张 → 上千张
    def _approx_repl(m):
        num_str = m.group(2)
        # 中文数字 → 阿拉伯数字 → 中文简写
        if num_str.isdigit():
            n = int(num_str)
        else:
            n = _parse_total(num_str)
        return m.group(1) + _arabic_to_chinese(n) + m.group(3)

    text = _APPROX_RE.sub(_approx_repl, text)

    # Handle 数字+单位 → 数字+缩写单位（毫米→mm, 厘米→cm 等）
    text = _UNIT_NORM_RE.sub(
        lambda m: m.group(1) + _UNIT_ABBREV[m.group(2)], text
    )

    return text
