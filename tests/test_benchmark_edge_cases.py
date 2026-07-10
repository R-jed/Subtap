from pathlib import Path

from benchmarks.implementations.baseline import BaselineSegmentation


EDGE_CASES_DIR = Path(__file__).parent.parent / "benchmarks" / "data" / "edge_cases"


def test_no_punctuation():
    text = (EDGE_CASES_DIR / "no_punctuation.txt").read_text(encoding="utf-8")
    impl = BaselineSegmentation()
    result = impl.segment(text)
    assert len(result.sentences) >= 1
    assert all(len(s) > 0 for s in result.sentences)


def test_long_sentence():
    text = (EDGE_CASES_DIR / "long_sentence.txt").read_text(encoding="utf-8")
    impl = BaselineSegmentation()
    result = impl.segment(text)
    assert len(result.sentences) >= 1
    # 长句应该被切分
    assert any(len(s) < len(text) for s in result.sentences)


def test_colloquial():
    text = (EDGE_CASES_DIR / "colloquial.txt").read_text(encoding="utf-8")
    impl = BaselineSegmentation()
    result = impl.segment(text)
    assert len(result.sentences) >= 1


def test_mixed_language():
    text = (EDGE_CASES_DIR / "mixed_lang.txt").read_text(encoding="utf-8")
    impl = BaselineSegmentation()
    result = impl.segment(text)
    assert len(result.sentences) >= 1


def test_numbers():
    text = (EDGE_CASES_DIR / "numbers.txt").read_text(encoding="utf-8")
    impl = BaselineSegmentation()
    result = impl.segment(text)
    assert len(result.sentences) >= 1
