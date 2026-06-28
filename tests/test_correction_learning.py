"""Phase 26: correction learning."""

from subtap.learning.corrections import learn_correction_pairs


def test_correction_learning_extracts_changed_lines():
    """Learning should extract explainable typo correction pairs."""
    pairs = learn_correction_pairs(
        draft_texts=["今天使用扣问模型", "字幕没有变化"],
        corrected_texts=["今天使用 Qwen 模型", "字幕没有变化"],
    )

    assert pairs == [{"from": "今天使用扣问模型", "to": "今天使用 Qwen 模型"}]
