from benchmarks.utils.srt_generator import generate_srt


def test_generate_srt_basic():
    sentences = ["第一句话", "第二句话"]
    timestamps = [(0.0, 1.5), (1.5, 3.0)]
    srt = generate_srt(sentences, timestamps)
    assert "1\n00:00:00,000 --> 00:00:01,500\n第一句话" in srt
    assert "2\n00:00:01,500 --> 00:00:03,000\n第二句话" in srt


def test_generate_srt_empty():
    srt = generate_srt([], [])
    assert srt == ""
