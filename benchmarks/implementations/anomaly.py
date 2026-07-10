import re

from .base import SegmentationBenchmark, SegmentationResult

# 句末标点
_SENT_END_RE = re.compile(r"[。！？.!?]+")


class AnomalySegmentation(SegmentationBenchmark):
    """faster-whisper 异常检测

    NOTE: 这是 placeholder / 模拟实现。word_anomaly_score 方法存在但未被
    segment() 调用；当前 segment() 仅按标点断句，不具备真实的异常检测能力。
    """

    def __init__(self, anomaly_threshold: float = 3.0):
        self.anomaly_threshold = anomaly_threshold

    def name(self) -> str:
        return "anomaly"

    def word_anomaly_score(self, word_duration: float, word_probability: float) -> float:
        """计算 word 异常分数"""
        score = 0.0
        if word_probability < 0.15:
            score += 1.0
        if word_duration < 0.133:
            score += (0.133 - word_duration) * 15
        if word_duration > 2.0:
            score += word_duration - 2.0
        return score

    def segment(self, text: str) -> SegmentationResult:
        # 基于标点断句
        parts = self._split_at_pattern(text, _SENT_END_RE)

        # 过滤异常 segment（模拟）
        result = [p.strip() for p in parts if p.strip()]

        return SegmentationResult(
            sentences=result, metadata={"anomaly_threshold": self.anomaly_threshold}
        )

    def _split_at_pattern(self, text: str, pattern: re.Pattern) -> list[str]:
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
        return segments
