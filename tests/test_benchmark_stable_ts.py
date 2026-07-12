"""Tests for stable-ts style segmentation benchmark."""

from benchmarks.implementations.stable_ts import StableTsSegmentation


def test_stable_ts_name():
    impl = StableTsSegmentation()
    assert impl.name() == "stable_ts"


def test_stable_ts_segment_with_punctuation():
    impl = StableTsSegmentation()
    result = impl.segment("第一句话。第二句话！第三句话？")
    assert len(result.sentences) == 3
    assert "第一句话" in result.sentences[0]


def test_stable_ts_segment_without_punctuation():
    impl = StableTsSegmentation()
    text = "GR系列的核心卖点就是轻便整机带电池只有262g同样APSC画幅的相机搭配镜头比它大了这么多"
    result = impl.segment(text)
    assert len(result.sentences) >= 1


def test_stable_ts_custom_config():
    impl = StableTsSegmentation(max_chars=10, min_chars=5)
    result = impl.segment("这是一个很长的句子需要被切分成多个部分以满足字幕显示的需求")
    assert len(result.sentences) >= 2


def test_stable_ts_comma_split():
    impl = StableTsSegmentation(max_chars=20)
    text = "第一部分，第二部分，第三部分，第四部分，第五部分"
    result = impl.segment(text)
    # 应该按逗号切分
    assert len(result.sentences) >= 2
