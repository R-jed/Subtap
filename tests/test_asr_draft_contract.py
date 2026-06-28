"""Phase 20: 验证 ASRDraft 数据契约。"""

from __future__ import annotations

from subtap.schemas.asr import ASRDraft, WordTiming


def test_asr_draft_has_required_fields():
    """ASRDraft 必须包含所有必需字段。"""
    draft = ASRDraft(
        chunk_id=0,
        text="你好世界",
        start_sec=0.0,
        end_sec=2.0,
        model="asr_0.6b",
    )
    assert draft.chunk_id == 0
    assert draft.text == "你好世界"
    assert draft.start_sec == 0.0
    assert draft.end_sec == 2.0
    assert draft.model == "asr_0.6b"


def test_asr_draft_provider_default():
    """ASRDraft provider 默认为 qwen3_mlx。"""
    draft = ASRDraft(
        chunk_id=0,
        text="test",
        start_sec=0.0,
        end_sec=1.0,
        model="asr_0.6b",
    )
    assert draft.provider == "qwen3_mlx"


def test_asr_draft_is_reference_only():
    """ASRDraft 时间戳是参考值，不是最终时间轴。"""
    draft = ASRDraft(
        chunk_id=0,
        text="test",
        start_sec=0.0,
        end_sec=1.0,
        model="asr_0.6b",
    )
    assert draft.is_reference_only() is True


def test_asr_draft_words_optional():
    """ASRDraft words 字段可选。"""
    draft = ASRDraft(
        chunk_id=0,
        text="test",
        start_sec=0.0,
        end_sec=1.0,
        model="asr_0.6b",
    )
    assert draft.words == []


def test_asr_draft_with_word_timing():
    """ASRDraft 可以包含词级时间戳。"""
    words = [
        WordTiming(word="你好", start_sec=0.0, end_sec=0.5),
        WordTiming(word="世界", start_sec=0.5, end_sec=1.0),
    ]
    draft = ASRDraft(
        chunk_id=0,
        text="你好世界",
        start_sec=0.0,
        end_sec=1.0,
        words=words,
        model="asr_1.7b",
    )
    assert len(draft.words) == 2
    assert draft.words[0].word == "你好"


def test_asr_draft_confidence_optional():
    """ASRDraft confidence 字段可选。"""
    draft = ASRDraft(
        chunk_id=0,
        text="test",
        start_sec=0.0,
        end_sec=1.0,
        model="asr_0.6b",
    )
    assert draft.confidence is None


def test_asr_draft_raw_ref_optional():
    """ASRDraft raw_ref 字段可选。"""
    draft = ASRDraft(
        chunk_id=0,
        text="test",
        start_sec=0.0,
        end_sec=1.0,
        model="asr_0.6b",
    )
    assert draft.raw_ref is None
