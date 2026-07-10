import re

from .base import SegmentationBenchmark, SegmentationResult

# 句末标点
_SENT_END_RE = re.compile(r"[。！？.!?]+")

# 逗号/停顿标点
_COMMA_RE = re.compile(r"[，、,;；]+")


class _Seg:
    """Wrapper: 保留 Tier 1 句末标点段的边界信息"""

    __slots__ = ("text", "boundary")

    def __init__(self, text: str, boundary: bool = False):
        self.text = text
        self.boundary = boundary  # True = Tier 1 拆分点，不参与合并


class RegroupSegmentation(SegmentationBenchmark):
    """stable-ts 风格可配置管线"""

    def __init__(self, max_chars: int = 60, min_chars: int = 10):
        self.max_chars = max_chars
        self.min_chars = min_chars

    def name(self) -> str:
        return "regroup"

    def segment(self, text: str) -> SegmentationResult:
        # Tier 1: 句末标点拆分
        parts = self._split_at_pattern(text, _SENT_END_RE)

        # Tier 2: 逗号拆分（仅超长段）
        expanded: list[_Seg] = []
        for seg in parts:
            segment_text = seg.text.strip()
            if not segment_text:
                continue
            if len(segment_text) > self.max_chars:
                for s in self._split_at_comma(segment_text):
                    expanded.append(_Seg(s))
            else:
                expanded.append(_Seg(segment_text, boundary=seg.boundary))

        # Tier 3: 长度硬切
        result: list[_Seg] = []
        for seg in expanded:
            if len(seg.text) > self.max_chars:
                for s in self._split_at_length(seg.text):
                    result.append(_Seg(s))
            else:
                result.append(seg)

        # 合并短句
        result = self._merge_short(result)

        return SegmentationResult(
            sentences=[s.text for s in result],
            metadata={"max_chars": self.max_chars, "min_chars": self.min_chars},
        )

    def _split_at_pattern(self, text: str, pattern: re.Pattern) -> list[_Seg]:
        """拆分并标记 Tier 1 边界：以标点结尾的段为边界段"""
        segments = []
        last_end = 0
        for match in pattern.finditer(text):
            end = match.end()
            segment = text[last_end:end]
            if segment.strip():
                segments.append(_Seg(segment, boundary=True))
            last_end = end
        remaining = text[last_end:]
        if remaining.strip():
            segments.append(_Seg(remaining, boundary=False))
        return segments

    def _split_at_comma(self, text: str) -> list[str]:
        segments = []
        current = ""
        parts = _COMMA_RE.split(text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if current and len(current) + len(part) + 1 > self.max_chars:
                segments.append(current.strip())
                current = part
            else:
                current = current + "，" + part if current else part
        if current.strip():
            segments.append(current.strip())
        return segments

    def _split_at_length(self, text: str) -> list[str]:
        segments = []
        for i in range(0, len(text), self.max_chars):
            segments.append(text[i : i + self.max_chars])
        return segments

    def _merge_short(self, sentences: list[_Seg]) -> list[_Seg]:
        if not sentences:
            return []
        merged: list[_Seg] = []
        buffer: _Seg | None = None
        for seg in sentences:
            if seg.boundary:
                # Tier 1 边界段：先 flush buffer，再直接入列（不合并）
                if buffer is not None:
                    merged.append(buffer)
                    buffer = None
                merged.append(seg)
            else:
                # Tier 2/3 段：短句合并
                if buffer is not None:
                    if (
                        self._content_length(buffer.text) < self.min_chars
                        and len(buffer.text) + len(seg.text) <= self.max_chars
                    ):
                        buffer = _Seg(buffer.text + seg.text)
                    else:
                        merged.append(buffer)
                        buffer = seg
                else:
                    buffer = seg
        # flush remaining buffer
        if buffer is not None:
            if (
                merged
                and self._content_length(buffer.text) < self.min_chars
                and len(merged[-1].text) + len(buffer.text) <= self.max_chars
            ):
                merged[-1] = _Seg(merged[-1].text + buffer.text)
            else:
                merged.append(buffer)
        return merged

    @staticmethod
    def _content_length(text: str) -> int:
        """去掉尾部句末标点后的内容长度"""
        return len(_SENT_END_RE.sub("", text))
