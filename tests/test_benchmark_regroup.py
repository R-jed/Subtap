from benchmarks.implementations.regroup import RegroupSegmentation


def test_regroup_name():
    impl = RegroupSegmentation()
    assert impl.name() == "regroup"


def test_regroup_segment_with_punctuation():
    impl = RegroupSegmentation()
    result = impl.segment("第一句话。第二句话！第三句话？")
    assert len(result.sentences) == 3


def test_regroup_segment_without_punctuation():
    impl = RegroupSegmentation()
    text = "GR系列的核心卖点就是轻便整机带电池只有262g同样APSC画幅的相机搭配镜头比它大了这么多"
    result = impl.segment(text)
    assert len(result.sentences) >= 1


def test_regroup_custom_config():
    impl = RegroupSegmentation(max_chars=20)
    result = impl.segment("这是一个很长的句子需要被切分成多个部分以满足字幕显示的需求")
    assert len(result.sentences) >= 2
