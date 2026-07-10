import pytest


def _funasr_available():
    try:
        import funasr

        return True
    except ImportError:
        return False


from benchmarks.implementations.combined import CombinedSegmentation


def test_combined_name():
    impl = CombinedSegmentation()
    assert impl.name() == "combined"


def test_combined_requires_model():
    impl = CombinedSegmentation()
    assert impl.requires_model() is True


@pytest.mark.skipif(
    not _funasr_available(),
    reason="funasr not installed",
)
def test_combined_segment():
    impl = CombinedSegmentation()
    text = "GR系列的核心卖点就是轻便整机带电池只有262g"
    result = impl.segment(text)
    assert len(result.sentences) >= 1
    assert "punctuated_text" in result.metadata
