from benchmarks.implementations.anomaly import AnomalySegmentation


def test_anomaly_name():
    impl = AnomalySegmentation()
    assert impl.name() == "anomaly"


def test_anomaly_segment_normal():
    impl = AnomalySegmentation()
    result = impl.segment("第一句话。第二句话。")
    assert len(result.sentences) == 2


def test_anomaly_score_calculation():
    impl = AnomalySegmentation()
    # 正常 word: duration=0.5, probability=0.9
    score = impl.word_anomaly_score(0.5, 0.9)
    assert score == 0.0

    # 异常 word: duration 太短
    score = impl.word_anomaly_score(0.1, 0.9)
    assert score > 0.0

    # 异常 word: probability 太低
    score = impl.word_anomaly_score(0.5, 0.1)
    assert score > 0.0
