"""Tests for sentence segmentation stage."""

from __future__ import annotations

from pathlib import Path

from subtap.core.segment import run_segment
from subtap.core.segmentation import (
    _split_sentences,
    _allocate_time,
    segment_clean_segments,
)
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import CleanSegment, SentenceSegment

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
        assert len(s) <= 80


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
    """Write mock CleanSegments to cleaned.jsonl and a single-chunk chunks.jsonl."""
    ws.ensure_dirs()
    with open(ws.cleaned_jsonl, "w") as f:
        for i, text in enumerate(texts):
            seg = CleanSegment(
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
        CleanSegment(
            segment_id=0,
            original_text="a",
            cleaned_text="First sentence。Second sentence。",
            glossary_applied=[],
        ),
        CleanSegment(
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
        CleanSegment(
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
        CleanSegment(
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
        CleanSegment(
            segment_id=0,
            original_text="a",
            cleaned_text="One。Two。",
            glossary_applied=[],
        ),
        CleanSegment(
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
