"""Word boundaries from macOS Core Foundation linguistic tokenization."""

from __future__ import annotations

import ctypes
import sys
from ctypes import POINTER, Structure, c_bool, c_long, c_uint8, c_ulong, c_void_p
from functools import lru_cache


class _CFRange(Structure):
    _fields_ = [("location", c_long), ("length", c_long)]


if sys.platform != "darwin":
    raise RuntimeError("Subtap 中文断句需要 macOS Core Foundation")

_CF = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
_CF.CFStringCreateWithBytes.argtypes = [
    c_void_p,
    POINTER(c_uint8),
    c_long,
    c_ulong,
    c_bool,
]
_CF.CFStringCreateWithBytes.restype = c_void_p
_CF.CFStringGetLength.argtypes = [c_void_p]
_CF.CFStringGetLength.restype = c_long
_CF.CFLocaleCreate.argtypes = [c_void_p, c_void_p]
_CF.CFLocaleCreate.restype = c_void_p
_CF.CFStringTokenizerCreate.argtypes = [
    c_void_p,
    c_void_p,
    _CFRange,
    c_ulong,
    c_void_p,
]
_CF.CFStringTokenizerCreate.restype = c_void_p
_CF.CFStringTokenizerAdvanceToNextToken.argtypes = [c_void_p]
_CF.CFStringTokenizerAdvanceToNextToken.restype = c_ulong
_CF.CFStringTokenizerGetCurrentTokenRange.argtypes = [c_void_p]
_CF.CFStringTokenizerGetCurrentTokenRange.restype = _CFRange
_CF.CFRelease.argtypes = [c_void_p]

_UTF8_ENCODING = 0x08000100
_WORD_UNIT = 0


def _cf_string(text: str) -> int:
    encoded = text.encode("utf-8")
    buffer = (c_uint8 * len(encoded)).from_buffer_copy(encoded)
    value = _CF.CFStringCreateWithBytes(
        None, buffer, len(encoded), _UTF8_ENCODING, False
    )
    if not value:
        raise RuntimeError("Core Foundation 无法创建分词文本")
    return value


def _utf16_to_python_offsets(text: str) -> list[int]:
    offsets = [0]
    for index, char in enumerate(text):
        units = len(char.encode("utf-16-le")) // 2
        offsets.extend([index + 1] * units)
    return offsets


@lru_cache(maxsize=1024)
def word_end_indices(text: str, locale: str = "zh-Hans") -> frozenset[int]:
    """Return Python string indices immediately after each linguistic word."""
    if not text:
        return frozenset()

    string_ref = _cf_string(text)
    locale_id_ref = _cf_string(locale)
    locale_ref = _CF.CFLocaleCreate(None, locale_id_ref)
    if not locale_ref:
        _CF.CFRelease(locale_id_ref)
        _CF.CFRelease(string_ref)
        raise RuntimeError(f"Core Foundation 无法创建语言区域: {locale}")

    tokenizer_ref = None
    try:
        length = _CF.CFStringGetLength(string_ref)
        tokenizer_ref = _CF.CFStringTokenizerCreate(
            None,
            string_ref,
            _CFRange(0, length),
            _WORD_UNIT,
            locale_ref,
        )
        if not tokenizer_ref:
            raise RuntimeError("Core Foundation 中文分词器创建失败")

        offsets = _utf16_to_python_offsets(text)
        boundaries: set[int] = set()
        while _CF.CFStringTokenizerAdvanceToNextToken(tokenizer_ref):
            token_range = _CF.CFStringTokenizerGetCurrentTokenRange(tokenizer_ref)
            token_end = token_range.location + token_range.length
            if 0 < token_end < len(offsets):
                boundaries.add(offsets[token_end])
        return frozenset(boundaries)
    finally:
        if tokenizer_ref:
            _CF.CFRelease(tokenizer_ref)
        _CF.CFRelease(locale_ref)
        _CF.CFRelease(locale_id_ref)
        _CF.CFRelease(string_ref)
