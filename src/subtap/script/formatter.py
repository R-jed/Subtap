"""Script formatting: remove comments, empty lines, normalize punctuation."""

from __future__ import annotations

import re

# 注释行模式
_COMMENT_PATTERNS = [
    re.compile(r"^\s*#"),  # # 开头
    re.compile(r"^\s*//"),  # // 开头
    re.compile(r"^【.*】\s*$"),  # 【备注】
    re.compile(r"^\[.*\]\s*$"),  # [说明]
]

# 全角标点 → 半角（英文语境用）
_FW_TO_HW = str.maketrans(
    {
        "，": ",",  # ，
        "。": ".",  # 。
        "！": "!",  # ！
        "？": "?",  # ？
        "；": ";",  # ；
        "：": ":",  # ：
        "“": '"',  # “
        "”": '"',  # ”
        "‘": "'",  # ‘
        "’": "'",  # ’
        "（": "(",  # （
        "）": ")",  # ）
        "【": "[",  # 【
        "】": "]",  # 】
    }
)


def _is_comment(line: str) -> bool:
    """Check if line is a comment or note."""
    return any(p.match(line) for p in _COMMENT_PATTERNS)


def format_script(text: str, language: str = "zh") -> list[str]:
    """Format script text: remove comments, empty lines, normalize whitespace.

    Args:
        text: Raw script text.
        language: Target language (zh/ja preserves fullwidth, en converts to halfwidth).

    Returns:
        List of cleaned content lines.
    """
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _is_comment(line):
            continue
        # 合并连续空格
        line = re.sub(r"\s+", " ", line)
        # 英文语境转换标点
        if language == "en":
            line = line.translate(_FW_TO_HW)
        lines.append(line)
    return lines
