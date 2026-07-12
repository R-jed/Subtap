import pytest
from benchmarks.implementations.funasr_punct import FunASRPunctuation


def _funasr_available():
    try:
        import funasr

        return True
    except ImportError:
        return False


def test_funasr_name():
    impl = FunASRPunctuation()
    assert impl.name() == "funasr_punct"


def test_funasr_requires_model():
    impl = FunASRPunctuation()
    assert impl.requires_model() is True


@pytest.mark.skipif(not _funasr_available(), reason="funasr not installed")
def test_funasr_segment():
    impl = FunASRPunctuation()
    text = "GR系列的核心卖点就是轻便整机带电池只有262g"
    result = impl.segment(text)
    assert len(result.sentences) >= 1
    assert "punctuated_text" in result.metadata
