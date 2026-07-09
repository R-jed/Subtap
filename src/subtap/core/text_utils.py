"""Shared text utilities for punctuation normalization and CJK handling."""

from __future__ import annotations

import re

_PUNCT_MAP = str.maketrans(
    ",.?!;:()",
    "，。？！；：（）",
)

# All punctuation (both half-width and full-width) for stripping
ALL_PUNCT_RE = re.compile(r"[，。？！、；：“”‘’（）《》,.?!;:\"'()\[\]{}\-—…·]")


def normalize_punct(text: str, language: str = "zh") -> str:
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


def remove_cjk_spaces(text: str) -> str:
    """Remove spaces between CJK/digits and Latin/digits.

    Rules:
    - English letter + space + digit → RS 5 → RS5
    - Digit + space + English letter → 2.5 Pro → 2.5Pro
    - Chinese char + space + digit → 售价 6499 → 售价6499
    - Digit + space + Chinese char → 6499 元 → 6499元
    """
    text = re.sub(r"([A-Za-z])\s+(\d)", r"\1\2", text)
    text = re.sub(r"(\d)\s+([A-Za-z])", r"\1\2", text)
    text = re.sub(r"([一-鿿])\s+(\d)", r"\1\2", text)
    text = re.sub(r"(\d)\s+([一-鿿])", r"\1\2", text)
    return text


def strip_punct(text: str) -> str:
    """Remove all punctuation, preserving decimal points and ratios in numbers."""
    # Protect decimal points (e.g., 0.6秒)
    protected = re.sub(r"(\d)\.(\d)", r"\1<DECIMAL>\2", text)
    # Protect ratio colons (e.g., 21:9)
    protected = re.sub(r"(\d):(\d)", r"\1<RATIO>\2", protected)
    stripped = ALL_PUNCT_RE.sub("", protected)
    return stripped.replace("<DECIMAL>", ".").replace("<RATIO>", ":")
