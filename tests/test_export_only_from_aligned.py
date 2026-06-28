"""Phase 20: 验证 Export 只能从 AlignedSubtitle 导出。"""

from __future__ import annotations

import pytest

from subtap.schemas.alignment import AlignedSubtitle
from subtap.schemas.asr import ASRDraft
from subtap.schemas.enhancement import CleanSegment
from subtap.schemas.subtitle import FinalSubtitle


def test_final_subtitle_from_aligned():
    """FinalSubtitle 只能从 AlignedSubtitle 创建。"""
    aligned = AlignedSubtitle(
        subtitle_id=0,
        start_sec=0.0,
        end_sec=2.0,
        text="你好世界",
    )
    final = FinalSubtitle.from_aligned(aligned)
    assert final.start_sec == aligned.start_sec
    assert final.end_sec == aligned.end_sec
    assert final.text == aligned.text


def test_final_subtitle_preserves_timing():
    """FinalSubtitle 保留 AlignedSubtitle 的时间戳。"""
    aligned = AlignedSubtitle(
        subtitle_id=0,
        start_sec=1.5,
        end_sec=3.5,
        text="测试",
    )
    final = FinalSubtitle.from_aligned(aligned)
    assert final.start_sec == 1.5
    assert final.end_sec == 3.5


def test_final_subtitle_preserves_words():
    """FinalSubtitle 保留 AlignedSubtitle 的词级时间戳。"""
    from subtap.schemas.alignment import AlignedWord

    words = [
        AlignedWord(word="你好", start_sec=0.0, end_sec=0.5),
        AlignedWord(word="世界", start_sec=0.5, end_sec=1.0),
    ]
    aligned = AlignedSubtitle(
        subtitle_id=0,
        start_sec=0.0,
        end_sec=1.0,
        text="你好世界",
        words=words,
        alignment_confidence=0.95,
    )
    final = FinalSubtitle.from_aligned(aligned)
    assert len(final.words) == 2
    assert final.alignment_confidence == 0.95


def test_final_subtitle_with_source_trace():
    """FinalSubtitle 可以包含 source_trace。"""
    aligned = AlignedSubtitle(
        subtitle_id=0,
        start_sec=0.0,
        end_sec=2.0,
        text="test",
    )
    trace = {
        "chunk_id": 0,
        "segment_ids": [0, 1],
        "enhancement_mode": "local",
    }
    final = FinalSubtitle.from_aligned(aligned, source_trace=trace)
    assert final.source_trace["chunk_id"] == 0
    assert final.source_trace["enhancement_mode"] == "local"


def test_final_subtitle_srt_format():
    """FinalSubtitle 可以格式化为 SRT。"""
    aligned = AlignedSubtitle(
        subtitle_id=0,
        start_sec=0.0,
        end_sec=2.0,
        text="你好世界",
    )
    final = FinalSubtitle.from_aligned(aligned)
    srt = final.to_srt_block(1)
    assert "1\n" in srt
    assert "00:00:00,000 --> 00:00:02,000" in srt
    assert "你好世界" in srt


def test_asr_draft_cannot_export_directly():
    """ASRDraft 不能直接导出为 FinalSubtitle（无 from_asr 方法）。"""
    draft = ASRDraft(
        chunk_id=0,
        text="test",
        start_sec=0.0,
        end_sec=1.0,
        model="asr_0.6b",
    )
    # FinalSubtitle 没有 from_asr 方法
    assert not hasattr(FinalSubtitle, "from_asr")


def test_clean_segment_cannot_export_directly():
    """CleanSegment 不能直接导出为 FinalSubtitle（无 from_clean 方法）。"""
    clean = CleanSegment(
        segment_id=0,
        source_chunk_id=0,
        text="test",
        original_text="test",
        start_sec=0.0,
        end_sec=1.0,
    )
    # FinalSubtitle 没有 from_clean 方法
    assert not hasattr(FinalSubtitle, "from_clean")
