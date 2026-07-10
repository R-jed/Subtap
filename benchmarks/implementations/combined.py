from .base import SegmentationBenchmark, SegmentationResult
from .funasr_punct import FunASRPunctuation
from .regroup import RegroupSegmentation


class CombinedSegmentation(SegmentationBenchmark):
    """标点恢复 + 可配置管线"""

    def __init__(self, max_chars: int = 60, min_chars: int = 10):
        self.punct_model = FunASRPunctuation()
        self.regroup = RegroupSegmentation(max_chars=max_chars, min_chars=min_chars)

    def name(self) -> str:
        return "combined"

    def requires_model(self) -> bool:
        return True

    def segment(self, text: str) -> SegmentationResult:
        # Step 1: 恢复标点
        punct_result = self.punct_model.segment(text)
        punctuated_text = punct_result.metadata.get("punctuated_text", text)

        # Step 2: 用 regroup 管线断句
        regroup_result = self.regroup.segment(punctuated_text)

        return SegmentationResult(
            sentences=regroup_result.sentences,
            metadata={
                "punctuated_text": punctuated_text,
                "regroup_config": regroup_result.metadata,
            },
        )
