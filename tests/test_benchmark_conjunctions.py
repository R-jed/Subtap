from benchmarks.implementations.conjunctions import ConjunctionSegmentation


def test_conjunctions_name():
    impl = ConjunctionSegmentation()
    assert impl.name() == "conjunctions"


def test_conjunctions_segment_at_conjunction():
    impl = ConjunctionSegmentation()
    text = "这个相机很好但是太贵了所以我没买"
    result = impl.segment(text)
    assert len(result.sentences) >= 2
    assert "但是" in result.sentences[0] or "但是" in result.sentences[1]


def test_conjunctions_no_conjunction():
    impl = ConjunctionSegmentation()
    text = "这个相机很好"
    result = impl.segment(text)
    assert len(result.sentences) == 1


def test_conjunctions_multiple():
    impl = ConjunctionSegmentation()
    text = "因为太贵了所以没买但是后来又后悔了"
    result = impl.segment(text)
    assert len(result.sentences) >= 2
