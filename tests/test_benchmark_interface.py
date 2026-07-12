from benchmarks.implementations.base import SegmentationBenchmark, SegmentationResult


def test_segmentation_result_creation():
    result = SegmentationResult(sentences=["第一句", "第二句"], metadata={})
    assert len(result.sentences) == 2
    assert result.metadata == {}


def test_segmentation_benchmark_interface():
    class MockBenchmark(SegmentationBenchmark):
        def name(self) -> str:
            return "mock"

        def segment(self, text: str) -> SegmentationResult:
            return SegmentationResult(
                sentences=[s for s in text.split("。") if s], metadata={}
            )

    impl = MockBenchmark()
    assert impl.name() == "mock"
    assert impl.requires_word_level() is False
    assert impl.requires_model() is False

    result = impl.segment("第一句。第二句。")
    assert len(result.sentences) == 2
