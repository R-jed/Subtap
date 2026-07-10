from subtap.core.segmentation import _split_sentences_zh
from .base import SegmentationBenchmark, SegmentationResult


class FunASRPunctuation(SegmentationBenchmark):
    """FunASR CT-Transformer 标点恢复"""

    def __init__(self):
        self._model = None

    def name(self) -> str:
        return "funasr_punct"

    def requires_model(self) -> bool:
        return True

    def _load_model(self):
        if self._model is None:
            try:
                from funasr import AutoModel
                self._model = AutoModel(
                    model="ct-punc",
                    disable_update=True
                )
            except ImportError:
                raise RuntimeError(
                    "funasr not installed. Run: pip install funasr"
                )

    def segment(self, text: str) -> SegmentationResult:
        self._load_model()

        result = self._model.generate(input=text)
        punctuated = result[0]["text"] if result else text

        sentences = _split_sentences_zh(punctuated)

        return SegmentationResult(
            sentences=sentences,
            metadata={"punctuated_text": punctuated}
        )
