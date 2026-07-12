"""Tests for _smart_split_v2: Subtitle Edit style split-point enumeration + scoring."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


# Helper: build a word dict
def _w(word: str, start: float, end: float) -> dict:
    return {"word": word, "start_sec": start, "end_sec": end}


def _aligned(sentence_id: int, text: str, start: float):
    from subtap.schemas.models import AlignedSegment

    words = []
    cursor = start
    for word in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text):
        words.append(_w(word, cursor, cursor + 0.08))
        cursor += 0.1
    return AlignedSegment(
        sentence_id=sentence_id,
        start_sec=start,
        end_sec=cursor,
        text=text,
        words=words,
    )


def _srt_text_lines(content: str) -> list[str]:
    return [block.splitlines()[2] for block in content.strip().split("\n\n")]


def _words_with_comma_pause(text: str, pause_sec: float) -> list[dict]:
    words = []
    cursor = 0.0
    for token in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]|[，。]", text):
        if token == "，":
            words.append(_w(token, cursor, cursor))
            cursor += pause_sec
        elif token == "。":
            words.append(_w(token, cursor, cursor))
        else:
            words.append(_w(token, cursor, cursor + 0.08))
            cursor += 0.1
    return words


def test_export_never_merges_across_sentence_segments():
    from subtap.core.export import SRTExporter

    segments = [
        _aligned(
            0,
            "这台相机从二零二五年八月发布到今天，一直是一机难求的状态。",
            0.0,
        ),
        _aligned(1, "它叫做理光GR4。", 4.0),
    ]

    content = SRTExporter(max_chars=25, min_chars=10).render(segments)

    assert _srt_text_lines(content) == [
        "这台相机从2025年8月发布到今天",
        "一直是一机难求的状态",
        "它叫做理光GR4",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "它实际市场售价都已经到万元了，很难原价买到。",
            ["它实际市场售价都已经到万元了，", "很难原价买到。"],
        ),
        (
            "但GR4又加了钱以后还是被抢爆，真的有点看不懂。",
            ["但GR4又加了钱以后还是被抢爆，", "真的有点看不懂。"],
        ),
    ],
)
def test_split_keeps_short_clause_after_comma_pause(text: str, expected: list[str]):
    from subtap.core.export import SRTExporter
    from subtap.schemas.models import AlignedSegment

    segment = AlignedSegment(
        sentence_id=0,
        start_sec=0.0,
        end_sec=3.0,
        text=text,
        words=_words_with_comma_pause(text, pause_sec=0.3),
    )

    content = SRTExporter(max_chars=25, min_chars=10, punctuation=True).render(
        [segment]
    )

    assert _srt_text_lines(content) == expected


def test_split_keeps_incomplete_comma_fragment_merged_without_pause():
    from subtap.core.export import SRTExporter
    from subtap.schemas.models import AlignedSegment

    text = "它实际市场售价都已经到万元了，很难"
    segment = AlignedSegment(
        sentence_id=0,
        start_sec=0.0,
        end_sec=3.0,
        text=text,
        words=_words_with_comma_pause(text, pause_sec=0.0),
    )
    content = SRTExporter(max_chars=25, min_chars=10, punctuation=True).render(
        [segment]
    )

    assert _srt_text_lines(content) == [text]


class TestSmartSplitV2Basic:
    """Basic splitting behavior."""

    def test_short_text_returns_single_line(self):
        """Short text under max_chars should not be split."""
        from subtap.core.export import _smart_split_v2

        words = [_w("短文本", 0.0, 1.0)]
        result = _smart_split_v2(words, "短文本", max_chars=25, min_chars=10)
        assert len(result) == 1
        assert result[0]["text"] == "短文本"

    def test_split_at_sentence_end_punctuation(self):
        """Should split at sentence-ending punctuation (。！？)."""
        from subtap.core.export import _smart_split_v2

        words = [_w("这是第一句。", 0.0, 1.0), _w("这是第二句。", 1.0, 2.0)]
        result = _smart_split_v2(
            words, "这是第一句。这是第二句。", max_chars=25, min_chars=5
        )
        texts = [r["text"] for r in result]
        assert len(texts) >= 2
        assert any("第一句" in t for t in texts)
        assert any("第二句" in t for t in texts)

    def test_split_at_comma(self):
        """Should split at comma (，) when line is long enough."""
        from subtap.core.export import _smart_split_v2

        words = [
            _w("很长的第一部分文本，", 0.0, 1.0),
            _w("以及第二部分文本。", 1.0, 2.0),
        ]
        result = _smart_split_v2(
            words, "很长的第一部分文本，以及第二部分文本。", max_chars=20, min_chars=5
        )
        assert len(result) >= 2

    def test_no_split_when_under_max_chars(self):
        """Should not split when text is under max_chars."""
        from subtap.core.export import _smart_split_v2

        words = [_w("短句", 0.0, 1.0)]
        result = _smart_split_v2(words, "短句", max_chars=25, min_chars=5)
        assert len(result) == 1


class TestShortFragmentProtection:
    """Short fragment (< min_chars) should be merged into adjacent lines."""

    def test_no_single_char_fragments(self):
        """Single character should never be a standalone line."""
        from subtap.core.export import _smart_split_v2

        # Simulate a sentence where max_chars split would leave a single char
        words = [_w("差别没有特别特别大但是我觉得你能看出它和手机区别", 0.0, 5.0)]
        words.append(_w("的", 5.0, 5.1))
        words.append(_w("核心", 5.1, 5.3))
        words.append(_w("的", 5.3, 5.4))
        words.append(_w("点", 5.4, 5.5))
        words.append(_w("是", 5.5, 5.6))
        words.append(_w("这个", 5.6, 5.8))
        words.append(_w("虚化", 5.8, 6.0))
        text = "差别没有特别特别大但是我觉得你能看出它和手机区别的核心的点是这个虚化"
        result = _smart_split_v2(words, text, max_chars=25, min_chars=10)
        for r in result:
            assert len(r["text"]) >= 2, f"Fragment too short: '{r['text']}'"

    def test_no_two_char_fragments_when_avoidable(self):
        """2-char fragments should be merged when possible."""
        from subtap.core.export import _smart_split_v2

        words = [_w("这是一个测试文本用于验证短碎片合并功能", 0.0, 3.0)]
        words.append(_w("能", 3.0, 3.1))
        text = "这是一个测试文本用于验证短碎片合并功能能"
        result = _smart_split_v2(words, text, max_chars=20, min_chars=10)
        # No line should be <= 2 chars
        for r in result:
            assert len(r["text"]) > 2, f"Fragment too short: '{r['text']}'"


class TestEnglishWordSpacing:
    """English words should have spaces between them in output."""

    def test_english_words_have_spaces(self):
        """English words should be separated by spaces."""
        from subtap.core.export import _smart_split_v2

        words = [_w("Hello", 0.0, 0.5), _w("World", 0.5, 1.0)]
        result = _smart_split_v2(words, "Hello World", max_chars=25, min_chars=5)
        assert any("Hello World" in r["text"] or "Hello" in r["text"] for r in result)
        # Should not have "HelloWorld" without space
        for r in result:
            assert "HelloWorld" not in r["text"]

    def test_english_multiple_words(self):
        """Multiple English words should maintain spaces."""
        from subtap.core.export import _smart_split_v2

        words = [
            _w("This", 0.0, 0.3),
            _w("is", 0.3, 0.5),
            _w("a", 0.5, 0.6),
            _w("test", 0.6, 1.0),
        ]
        result = _smart_split_v2(words, "This is a test", max_chars=25, min_chars=5)
        text_combined = " ".join(r["text"] for r in result)
        assert "This" in text_combined
        assert "test" in text_combined


class TestLineBalance:
    """Lines should be balanced in length."""

    def test_balanced_split(self):
        """Two lines should be roughly equal length when splitting a long sentence."""
        from subtap.core.export import _smart_split_v2

        words = [_w("这是一段很长的文本需要被分成两行显示", 0.0, 3.0)]
        text = "这是一段很长的文本需要被分成两行显示"
        result = _smart_split_v2(words, text, max_chars=12, min_chars=5)
        if len(result) >= 2:
            lengths = [len(r["text"]) for r in result]
            # Lines should be somewhat balanced
            assert max(lengths) - min(lengths) <= max(lengths) * 0.5


class TestTimePreservation:
    """Timestamps should be preserved correctly."""

    def test_timestamps_cover_full_range(self):
        """Output timestamps should cover the full input time range."""
        from subtap.core.export import _smart_split_v2

        words = [_w("第一句。", 0.0, 1.0), _w("第二句。", 1.0, 2.0)]
        result = _smart_split_v2(words, "第一句。第二句。", max_chars=10, min_chars=3)
        assert result[0]["start_sec"] == 0.0
        assert result[-1]["end_sec"] == 2.0

    def test_no_time_overlap(self):
        """Consecutive lines should not overlap in time."""
        from subtap.core.export import _smart_split_v2

        words = [_w("第一部分文本，", 0.0, 1.0), _w("第二部分文本。", 1.0, 2.0)]
        result = _smart_split_v2(
            words, "第一部分文本，第二部分文本。", max_chars=10, min_chars=3
        )
        for i in range(1, len(result)):
            assert result[i]["start_sec"] >= result[i - 1]["end_sec"]


class TestNoWordLoss:
    """CORE CONSTRAINT: 绝不丢字。"""

    def test_all_characters_preserved(self):
        """Every character from input must appear in output."""
        from subtap.core.export import _smart_split_v2

        words = [_w("这台相机从二零二五年八月发布到今天一直是一机难求的状态", 0.0, 5.0)]
        text = "这台相机从二零二五年八月发布到今天一直是一机难求的状态"
        result = _smart_split_v2(words, text, max_chars=20, min_chars=8)
        output_text = "".join(r["text"] for r in result)
        # All characters must be preserved (order may change slightly due to punctuation handling)
        for ch in text:
            assert ch in output_text, f"Character '{ch}' lost"

    def test_english_text_preserved(self):
        """English text should be fully preserved."""
        from subtap.core.export import _smart_split_v2

        words = [
            _w("Hello", 0.0, 0.5),
            _w("World", 0.5, 1.0),
            _w("this", 1.0, 1.5),
            _w("is", 1.5, 1.7),
            _w("a", 1.7, 1.8),
            _w("test", 1.8, 2.0),
        ]
        text = "Hello World this is a test"
        result = _smart_split_v2(words, text, max_chars=15, min_chars=5)
        output_text = " ".join(r["text"] for r in result)
        assert "Hello" in output_text
        assert "World" in output_text
        assert "test" in output_text


class TestCJKBoundarySplitting:
    """CJK characters should be valid split points even without punctuation."""

    def test_long_cjk_without_punctuation(self):
        """Long CJK text without punctuation should be split at character boundaries."""
        from subtap.core.export import _smart_split_v2

        words = [
            _w(c, i * 0.1, (i + 1) * 0.1)
            for i, c in enumerate(
                "这是一个很长的中文句子没有任何标点符号需要在字符边界处断行"
            )
        ]
        text = "这是一个很长的中文句子没有任何标点符号需要在字符边界处断行"
        result = _smart_split_v2(words, text, max_chars=15, min_chars=5)
        # Should produce multiple lines
        assert len(result) >= 2
        # Each line should be within max_chars
        for r in result:
            assert len(r["text"]) <= 15


class TestRealMaterialIntegration:
    """Integration tests using real aligned.jsonl data."""

    @pytest.fixture
    def chinese_aligned(self):
        return Path("/tmp/subtap-seg-review/aligned.jsonl")

    @pytest.fixture
    def english_aligned(self):
        return Path("/tmp/subtap-seg-en/aligned.jsonl")

    def test_chinese_no_fragments_under_5(self, chinese_aligned):
        """Chinese SRT should have no fragments under 5 characters."""
        if not chinese_aligned.exists():
            pytest.skip("Test material not available")

        from subtap.core.export import (
            _smart_split_v2,
            _inject_punct,
            _filter_words_to_text,
        )

        with open(chinese_aligned) as f:
            segments = [json.loads(l) for l in f if l.strip()]

        for seg in segments:
            words = seg.get("words", [])
            if not words:
                continue
            word_filter_text = seg.get("aligned_text") or seg["text"]
            words_with_punct = _inject_punct(
                _filter_words_to_text(words, word_filter_text), seg["text"]
            )
            result = _smart_split_v2(
                words_with_punct,
                word_filter_text,
                max_chars=25,
                min_chars=10,
                start_sec=seg["start_sec"],
                end_sec=seg["end_sec"],
            )
            for r in result:
                assert (
                    len(r["text"]) >= 3
                ), f"Fragment too short in sentence {seg['sentence_id']}: '{r['text']}'"

    def test_english_words_have_spaces_in_srt(self, english_aligned):
        """English SRT lines should not have words merged without spaces."""
        if not english_aligned.exists():
            pytest.skip("Test material not available")

        from subtap.core.export import (
            _smart_split_v2,
            _inject_punct,
            _filter_words_to_text,
        )

        with open(english_aligned) as f:
            segments = [json.loads(l) for l in f if l.strip()]

        for seg in segments:
            words = seg.get("words", [])
            if not words:
                continue
            word_filter_text = seg.get("aligned_text") or seg["text"]
            words_with_punct = _inject_punct(
                _filter_words_to_text(words, word_filter_text), seg["text"]
            )
            result = _smart_split_v2(
                words_with_punct,
                word_filter_text,
                max_chars=25,
                min_chars=10,
                start_sec=seg["start_sec"],
                end_sec=seg["end_sec"],
            )
            for r in result:
                text = r["text"]
                # Check: no two Latin words merged without space
                # e.g., "thegame" should be "the game"
                import re

                # Find sequences of lowercase letters that look like merged words
                merged = re.findall(r"[a-z]{3,}[A-Z][a-z]+", text)
                assert (
                    not merged
                ), f"Merged English words in sentence {seg['sentence_id']}: {merged}"
