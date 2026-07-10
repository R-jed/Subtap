from benchmarks.implementations.baseline import BaselineSegmentation


def test_baseline_name():
    impl = BaselineSegmentation()
    assert impl.name() == "baseline"


def test_baseline_segment_with_punctuation():
    impl = BaselineSegmentation()
    result = impl.segment("第一句话。第二句话！第三句话？")
    assert len(result.sentences) == 3
    assert "第一句话" in result.sentences[0]


def test_baseline_segment_without_punctuation():
    impl = BaselineSegmentation()
    text = "GR系列的核心卖点就是轻便整机带电池只有262g同样APSC画幅的相机搭配镜头比它大了这么多"
    result = impl.segment(text)
    assert len(result.sentences) >= 1
    assert len(result.metadata) == 0
