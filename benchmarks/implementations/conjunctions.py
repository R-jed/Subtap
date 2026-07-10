import json
import re
from pathlib import Path

from .base import SegmentationBenchmark, SegmentationResult

# 连词表路径
_CONJUNCTIONS_PATH = Path(__file__).parent.parent / "data" / "conjunctions_zh.json"


class ConjunctionSegmentation(SegmentationBenchmark):
    """WhisperX 多语言连词表兜底"""

    def __init__(self, max_chars: int = 60):
        self.max_chars = max_chars
        self._conjunctions = self._load_conjunctions()

    def _load_conjunctions(self) -> list[str]:
        if _CONJUNCTIONS_PATH.exists():
            with open(_CONJUNCTIONS_PATH, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("conjunctions", [])
        return []

    def name(self) -> str:
        return "conjunctions"

    def segment(self, text: str) -> SegmentationResult:
        if not text.strip():
            return SegmentationResult(sentences=[""], metadata={})

        # 按连词切分
        segments = self._split_at_conjunctions(text)

        # 合并过短的段落
        result = self._merge_short(segments)

        return SegmentationResult(
            sentences=result,
            metadata={"conjunction_count": len(self._conjunctions)},
        )

    def _split_at_conjunctions(self, text: str) -> list[str]:
        if not self._conjunctions:
            return [text]

        # 构建连词正则（按长度降序，避免短连词优先匹配）
        sorted_conjs = sorted(self._conjunctions, key=len, reverse=True)
        pattern = re.compile(
            "(" + "|".join(re.escape(c) for c in sorted_conjs) + ")"
        )

        segments = []
        last_end = 0

        for match in pattern.finditer(text):
            # 在连词前切分
            split_pos = match.start()
            if split_pos > last_end:
                segment = text[last_end:split_pos]
                if segment.strip():
                    segments.append(segment)
            last_end = split_pos

        # 剩余部分
        remaining = text[last_end:]
        if remaining.strip():
            segments.append(remaining)

        return segments if segments else [text]

    def _merge_short(self, segments: list[str]) -> list[str]:
        if not segments:
            return []

        # 如果所有片段拼接后不超过 max_chars，不做合并
        total = sum(len(s) for s in segments)
        if total <= self.max_chars:
            return segments

        merged: list[str] = [segments[0]]

        for seg in segments[1:]:
            # 当前段过短时合并到前一段
            if len(merged[-1]) < self.max_chars // 2:
                merged[-1] += seg
            else:
                merged.append(seg)

        return merged
