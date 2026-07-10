from benchmarks.utils.metrics import calculate_metrics


def test_calculate_metrics_basic():
    sentences = ["第一句话", "第二句话是一个较长的句子"]
    metrics = calculate_metrics(sentences)
    assert metrics["sentence_count"] == 2
    assert metrics["sentence_length_mean"] > 0
    assert metrics["sentence_length_std"] >= 0
    assert metrics["sentence_length_min"] == 4
    assert metrics["sentence_length_max"] == 12


def test_calculate_metrics_single():
    sentences = ["只有一个句子"]
    metrics = calculate_metrics(sentences)
    assert metrics["sentence_count"] == 1
    assert metrics["sentence_length_std"] == 0.0


def test_calculate_metrics_empty():
    sentences = []
    metrics = calculate_metrics(sentences)
    assert metrics["sentence_count"] == 0
