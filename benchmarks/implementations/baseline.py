from subtap.core.segmentation import _split_sentences_zh
from .base import SegmentationBenchmark, SegmentationResult


class BaselineSegmentation(SegmentationBenchmark):
    """现有正则三层 + jieba"""

    def name(self) -> str:
        return "baseline"

    def segment(self, text: str) -> SegmentationResult:
        sentences = _split_sentences_zh(text)
        return SegmentationResult(sentences=sentences, metadata={})
