"""Stable-ts style segmentation algorithm.

复用 stable-ts 的断句算法逻辑，不依赖 stable-ts 包。
算法参考：https://github.com/jianfch/stable-ts
"""

import re

from .base import SegmentationBenchmark, SegmentationResult


class StableTsSegmentation(SegmentationBenchmark):
    """stable-ts 风格断句算法

    核心逻辑：
    1. 按句末标点切分（。！？.!?）
    2. 按逗号切分（仅超长段）
    3. 按最大字符数强制切分
    4. 合并过短段落
    """

    def __init__(
        self,
        max_chars: int = 70,
        min_chars: int = 20,
        split_by_comma: bool = True,
    ):
        self.max_chars = max_chars
        self.min_chars = min_chars
        self.split_by_comma = split_by_comma

    def name(self) -> str:
        return "stable_ts"

    def segment(self, text: str) -> SegmentationResult:
        if not text.strip():
            return SegmentationResult(sentences=[""], metadata={})

        # Step 1: 按句末标点切分
        segments = self._split_by_sentence_end(text)

        # Step 2: 按逗号切分（仅超长段）
        if self.split_by_comma:
            expanded = []
            for seg in segments:
                if len(seg) > self.max_chars:
                    expanded.extend(self._split_by_comma(seg))
                else:
                    expanded.append(seg)
            segments = expanded

        # Step 3: 按最大字符数强制切分
        result = []
        for seg in segments:
            if len(seg) > self.max_chars:
                result.extend(self._split_by_length(seg))
            else:
                result.append(seg)

        # Step 4: 合并过短段落
        result = self._merge_short(result)

        return SegmentationResult(
            sentences=result,
            metadata={
                "max_chars": self.max_chars,
                "min_chars": self.min_chars,
                "split_by_comma": self.split_by_comma,
            },
        )

    def _split_by_sentence_end(self, text: str) -> list[str]:
        """按句末标点切分"""
        pattern = re.compile(r"([。！？.!?]+)")
        segments = []
        last_end = 0

        for match in pattern.finditer(text):
            end = match.end()
            segment = text[last_end:end]
            if segment.strip():
                segments.append(segment)
            last_end = end

        remaining = text[last_end:]
        if remaining.strip():
            segments.append(remaining)

        return segments if segments else [text]

    def _split_by_comma(self, text: str) -> list[str]:
        """按逗号切分"""
        pattern = re.compile(r"[，,;；]+")
        parts = pattern.split(text)

        segments = []
        for part in parts:
            if part.strip():
                segments.append(part)

        return segments if segments else [text]

    def _split_by_length(self, text: str) -> list[str]:
        """按最大字符数强制切分"""
        segments = []
        for i in range(0, len(text), self.max_chars):
            segments.append(text[i : i + self.max_chars])
        return segments

    def _merge_short(self, segments: list[str]) -> list[str]:
        """合并过短段落，但保护切分边界"""
        if not segments:
            return []

        _SENT_END_CHARS = set("。！？.!?")

        # 如果所有段落都已经很短，不合并
        if all(len(s) < self.min_chars for s in segments):
            return segments

        merged = []
        buffer = ""

        for seg in segments:
            if buffer:
                # 如果 buffer 以句末标点结尾，不合并，直接输出
                if buffer and buffer[-1] in _SENT_END_CHARS:
                    merged.append(buffer)
                    buffer = seg
                # 如果 buffer 够长，输出并开始新段
                elif len(buffer) >= self.min_chars:
                    merged.append(buffer)
                    buffer = seg
                # 否则合并
                else:
                    buffer += seg
            else:
                buffer = seg

        if buffer:
            # 如果最后一个 buffer 以句末标点结尾，不合并
            if buffer[-1] in _SENT_END_CHARS:
                merged.append(buffer)
            elif merged and len(buffer) < self.min_chars:
                merged[-1] += buffer
            else:
                merged.append(buffer)

        return merged
