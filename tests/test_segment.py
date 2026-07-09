"""Tests for sentence segmentation stage."""

from __future__ import annotations

from pathlib import Path

from subtap.core.segment import run_segment
from subtap.core.segmentation import (
    _split_sentences,
    _split_at_word_boundary,
    _merge_short_sentences,
    _allocate_time,
    segment_clean_segments,
)
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import RawCleanSegment, SentenceSegment

# ── Sentence splitting tests ──


def test_split_on_cjk_punctuation():
    """CJK punctuation splits into separate sentences."""
    result = _split_sentences("你好世界。今天天气不错。")
    assert result == ["你好世界。", "今天天气不错。"]


def test_split_on_latin_punctuation():
    """Latin punctuation splits into separate sentences."""
    result = _split_sentences("Hello world. How are you? Fine!")
    assert result == ["Hello world.", "How are you?", "Fine!"]


def test_split_long_segment():
    """Long segment (>80 chars) is force-split at word boundaries."""
    long_text = "word " * 30  # 150 chars
    result = _split_sentences(long_text.strip())
    for s in result:
        assert len(s) <= 60


def test_split_empty_text():
    """Empty text returns single empty sentence."""
    result = _split_sentences("")
    assert result == [""]


# ── Time allocation tests ──


def test_allocate_time_basic():
    """Time allocated proportionally by character count."""
    sentences = ["ab", "abcd"]  # 2 vs 4 chars → 1/3 vs 2/3
    times = _allocate_time(sentences, 0.0, 3.0)
    assert len(times) == 2
    assert times[0] == (0.0, 1.0)
    assert times[1] == (1.0, 3.0)


def test_allocate_time_no_regression():
    """Time never goes backwards."""
    sentences = ["a", "bb", "ccc", "dddd"]
    times = _allocate_time(sentences, 1.0, 5.0)
    for i in range(1, len(times)):
        assert times[i][0] >= times[i - 1][1]


def test_allocate_time_single():
    """Single sentence gets full time range."""
    times = _allocate_time(["only one"], 2.0, 4.0)
    assert times == [(2.0, 4.0)]


def test_allocate_time_empty():
    """Empty list returns empty."""
    assert _allocate_time([], 0.0, 1.0) == []


# ── Segment pipeline tests ──


def _make_cleaned_jsonl(ws: Workspace, texts: list[str]) -> None:
    """Write mock RawCleanSegments to cleaned.jsonl and a single-chunk chunks.jsonl."""
    ws.ensure_dirs()
    with open(ws.cleaned_jsonl, "w") as f:
        for i, text in enumerate(texts):
            seg = RawCleanSegment(
                segment_id=i,
                source_chunk_id=0,
                original_text=f"orig {i}",
                cleaned_text=text,
                glossary_applied=[],
            )
            f.write(seg.model_dump_json() + "\n")
    # Create a minimal chunks.jsonl so run_segment can load boundaries
    from subtap.schemas.models import Chunk

    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=60.0, path="chunks/chunk_000.wav")
    with open(ws.chunks_jsonl, "w") as f:
        f.write(chunk.model_dump_json() + "\n")


def test_segment_clean_segments_basic(test_config: SubtapConfig, tmp_path: Path):
    """segment_clean_segments splits and assigns time."""
    segments = [
        RawCleanSegment(
            segment_id=0,
            original_text="a",
            cleaned_text="First sentence。Second sentence。",
            glossary_applied=[],
        ),
        RawCleanSegment(
            segment_id=1,
            original_text="b",
            cleaned_text="Third sentence.",
            glossary_applied=[],
        ),
    ]
    result = segment_clean_segments(segments, chunk_start=0.0, chunk_end=10.0)

    assert len(result) == 3
    assert result[0].text == "First sentence。"
    assert result[1].text == "Second sentence。"
    assert result[2].text == "Third sentence."


def test_time_monotonic_in_segment(test_config: SubtapConfig, tmp_path: Path):
    """Sentence times are monotonic within a chunk."""
    segments = [
        RawCleanSegment(
            segment_id=0,
            original_text="a",
            cleaned_text="Aa。Bb。Cc。",
            glossary_applied=[],
        ),
    ]
    result = segment_clean_segments(segments, chunk_start=0.0, chunk_end=6.0)

    for i in range(1, len(result)):
        assert result[i].start_sec >= result[i - 1].end_sec


def test_chunk_id_integrity(test_config: SubtapConfig, tmp_path: Path):
    """chunk_id in SentenceSegment matches source_chunk_id."""
    segments = [
        RawCleanSegment(
            segment_id=5,
            source_chunk_id=3,
            original_text="a",
            cleaned_text="Test sentence.",
            glossary_applied=[],
        ),
    ]
    result = segment_clean_segments(segments, chunk_start=0.0, chunk_end=1.0)
    assert result[0].chunk_id == 3


def test_jsonl_valid_schema(test_config: SubtapConfig, tmp_path: Path):
    """sentences.jsonl produces valid SentenceSegment JSONL."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    _make_cleaned_jsonl(ws, ["Hello world。Goodbye world。"])

    run_segment(ws, chunk_start=0.0, chunk_end=4.0)
    assert ws.sentences_jsonl.exists()

    with open(ws.sentences_jsonl) as f:
        for line in f:
            seg = SentenceSegment.model_validate_json(line.strip())
            assert seg.sentence_id >= 0
            assert seg.start_sec < seg.end_sec


def test_sentence_ids_sequential(test_config: SubtapConfig, tmp_path: Path):
    """sentence_ids are 0-based sequential across all segments."""
    segments = [
        RawCleanSegment(
            segment_id=0,
            original_text="a",
            cleaned_text="One。Two。",
            glossary_applied=[],
        ),
        RawCleanSegment(
            segment_id=1, original_text="b", cleaned_text="Three。", glossary_applied=[]
        ),
    ]
    result = segment_clean_segments(segments, chunk_start=0.0, chunk_end=6.0)

    ids = [s.sentence_id for s in result]
    assert ids == list(range(len(result)))


def test_cli_segment_runnable(test_config: SubtapConfig, tmp_path: Path, monkeypatch):
    """CLI segment command runs without crash."""
    from typer.testing import CliRunner
    from subtap.cli import app

    ws = Workspace(test_config, base_dir=tmp_path / "work")
    _make_cleaned_jsonl(ws, ["Test sentence one。Test sentence two。"])

    import subtap.schemas.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_config", lambda p: test_config)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "segment",
            str(ws.cleaned_jsonl),
            "-w",
            str(ws.root),
        ],
    )
    assert result.exit_code == 0
    assert "完成" in result.output


# ── Chinese colloquial segmentation tests ──


class TestSplitSentencesZh:
    """Test _split_sentences with Chinese colloquial content."""

    def test_basic_punctuation_split(self):
        """标点符号断句：句号、感叹号、问号。"""
        text = "这是第一句。这是第二句！这是第三句？"
        result = _split_sentences(text, language="zh")
        assert len(result) == 3
        assert "第一句" in result[0]
        assert "第二句" in result[1]
        assert "第三句" in result[2]

    def test_comma_split_long_sentence(self):
        """逗号断句：超长句子在逗号处拆分。"""
        text = "理光GR4是一款非常不错的相机，它的画质非常好，而且体积小巧，方便携带"
        result = _split_sentences(text, language="zh")
        for sent in result:
            assert len(sent) <= 60

    def test_no_punctuation_long_text(self):
        """无标点长文本：使用 jieba 词边界断句。"""
        text = "理光GR4是一款非常不错的相机它的画质非常好而且体积小巧方便携带适合旅行使用"
        result = _split_sentences(text, language="zh")
        assert len(result) >= 1
        for sent in result:
            assert len(sent) <= 60
        assert "".join(result) == text

    def test_colloquial_filler_words(self):
        """口语填充词：'然后'、'就是'、'那个' 等不应被误断。"""
        text = "然后那个就是说理光GR4它拍出来的照片非常好看就是那种很有质感的感觉"
        result = _split_sentences(text, language="zh")
        full_text = "".join(result)
        assert "理光" in full_text
        assert "质感" in full_text
        assert "然后" in full_text
        assert "就是" in full_text
        assert "那个" in full_text
        assert "".join(result) == text

    def test_mixed_punctuation_and_no_punctuation(self):
        """混合标点：有标点和无标点混合。"""
        text = "这款相机不错。画质好而且小巧方便携带，价格也合适"
        result = _split_sentences(text, language="zh")
        assert len(result) >= 2

    def test_short_text_no_split(self):
        """短文本不需要拆分。"""
        text = "好的"
        result = _split_sentences(text, language="zh")
        assert len(result) == 1
        assert result[0] == "好的"

    def test_empty_text_zh(self):
        """空文本返回空字符串。"""
        result = _split_sentences("", language="zh")
        assert result == [""]

    def test_english_text(self):
        """英文文本正常断句。"""
        text = "This is the first sentence. This is the second sentence."
        result = _split_sentences(text, language="en")
        assert len(result) == 2


class TestSplitAtWordBoundary:
    """Test _split_at_word_boundary with jieba."""

    def test_short_text_no_split(self):
        """短文本不拆分。"""
        text = "理光GR4相机"
        result = _split_at_word_boundary(text, max_chars=60)
        assert result == [text]

    def test_long_text_split(self):
        """长文本在词边界拆分。"""
        text = "理光GR4是一款非常不错的相机它的画质非常好而且体积小巧方便携带适合旅行使用"
        result = _split_at_word_boundary(text, max_chars=30)
        assert len(result) >= 2
        for part in result:
            assert len(part) <= 30

    def test_preserves_all_characters(self):
        """拆分后所有字符都保留，不丢字。"""
        text = "理光GR4是一款非常不错的相机它的画质非常好而且体积小巧方便携带"
        result = _split_at_word_boundary(text, max_chars=20)
        assert "".join(result) == text


class TestMergeShortSentences:
    """Test _merge_short_sentences."""

    def test_merge_short(self):
        """短句合并。"""
        sentences = ["好的", "然后呢", "理光GR4是一款非常不错的相机"]
        result = _merge_short_sentences(sentences, min_chars=10)
        assert len(result) < len(sentences)

    def test_no_merge_long(self):
        """长句不合并。"""
        sentences = ["理光GR4是一款非常不错的相机", "它的画质非常好而且体积小巧"]
        result = _merge_short_sentences(sentences, min_chars=10)
        assert len(result) == 2

    def test_empty_input(self):
        """空输入返回空列表。"""
        result = _merge_short_sentences([], min_chars=10)
        assert result == []
