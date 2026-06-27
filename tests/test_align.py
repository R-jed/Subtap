"""Tests for forced alignment stage."""

from __future__ import annotations

from pathlib import Path

from subtap.backends.align.base import AlignerBackend
from subtap.backends.align import get_aligner_backend
from subtap.backends.align.mock import MockAligner
from subtap.core.align import run_align
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig, AlignConfig
from subtap.schemas.models import SentenceSegment, AlignedSegment

# ── Backend protocol tests ──


def test_aligner_backend_protocol():
    """MockAligner satisfies the AlignerBackend protocol."""
    mock = MockAligner(AlignConfig(backend="mock-aligner"))
    assert isinstance(mock, AlignerBackend)


def test_get_aligner_mock():
    """get_aligner_backend returns MockAligner for mock-aligner."""
    config = AlignConfig(backend="mock-aligner")
    backend = get_aligner_backend(config)
    assert isinstance(backend, MockAligner)


def test_get_aligner_unknown():
    """get_aligner_backend raises ValueError for unknown backend."""
    config = AlignConfig(backend="nonexistent")
    try:
        get_aligner_backend(config)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "nonexistent" in str(e)


# ── Mock aligner correctness ──


def test_mock_aligner_preserves_text():
    """MockAligner returns text unchanged."""
    sentences = [
        SentenceSegment(
            sentence_id=0,
            chunk_id=0,
            start_sec=0.0,
            end_sec=1.0,
            text="Hello world",
            source_text="Hello world",
        ),
    ]
    backend = MockAligner(AlignConfig(backend="mock-aligner"))
    result = backend.align(sentences, Path("/tmp/fake.wav"))
    assert result[0].text == "Hello world"
    assert result[0].sentence_id == 0


def test_mock_aligner_preserves_timing():
    """MockAligner returns original timing."""
    sentences = [
        SentenceSegment(
            sentence_id=0,
            chunk_id=0,
            start_sec=0.5,
            end_sec=2.5,
            text="Test",
            source_text="Test",
        ),
        SentenceSegment(
            sentence_id=1,
            chunk_id=0,
            start_sec=2.5,
            end_sec=4.0,
            text="Test 2",
            source_text="Test 2",
        ),
    ]
    backend = MockAligner(AlignConfig(backend="mock-aligner"))
    result = backend.align(sentences, Path("/tmp/fake.wav"))
    assert result[0].start_sec == 0.5
    assert result[0].end_sec == 2.5
    assert result[1].start_sec == 2.5
    assert result[1].end_sec == 4.0


# ── Pipeline tests ──


def _make_sentences_jsonl(ws: Workspace, texts: list[str]) -> None:
    """Write mock SentenceSegments to sentences.jsonl."""
    ws.ensure_dirs()
    with open(ws.sentences_jsonl, "w") as f:
        for i, text in enumerate(texts):
            seg = SentenceSegment(
                sentence_id=i,
                chunk_id=i,
                start_sec=float(i),
                end_sec=float(i + 1),
                text=text,
                source_text=text,
            )
            f.write(seg.model_dump_json() + "\n")


def test_align_produces_jsonl(test_config: SubtapConfig, tmp_path: Path):
    """run_align produces valid aligned.jsonl."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    _make_sentences_jsonl(ws, ["Hello", "World"])

    import subtap.backends.align as align_reg

    original = align_reg.get_aligner_backend
    align_reg.get_aligner_backend = lambda cfg: MockAligner(cfg)
    try:
        result = run_align(ws, test_config, backend_name="mock-aligner")
    finally:
        align_reg.get_aligner_backend = original

    assert result["aligned_count"] == 2
    assert ws.aligned_jsonl.exists()

    with open(ws.aligned_jsonl) as f:
        for line in f:
            seg = AlignedSegment.model_validate_json(line.strip())
            assert seg.sentence_id >= 0
            assert seg.start_sec < seg.end_sec


def test_aligned_time_monotonic(test_config: SubtapConfig, tmp_path: Path):
    """Aligned segments have monotonic time."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    _make_sentences_jsonl(ws, ["First", "Second", "Third"])

    import subtap.backends.align as align_reg

    align_reg.get_aligner_backend = lambda cfg: MockAligner(cfg)
    try:
        run_align(ws, test_config, backend_name="mock-aligner")
    finally:
        align_reg.get_aligner_backend = lambda cfg: MockAligner(cfg)

    segments = []
    with open(ws.aligned_jsonl) as f:
        for line in f:
            segments.append(AlignedSegment.model_validate_json(line.strip()))

    for i in range(1, len(segments)):
        assert segments[i].start_sec >= segments[i - 1].end_sec


def test_aligned_text_unchanged(test_config: SubtapConfig, tmp_path: Path):
    """AlignedSegment text matches source SentenceSegment text."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    texts = ["Original text one", "Original text two"]
    _make_sentences_jsonl(ws, texts)

    import subtap.backends.align as align_reg

    align_reg.get_aligner_backend = lambda cfg: MockAligner(cfg)
    try:
        run_align(ws, test_config, backend_name="mock-aligner")
    finally:
        align_reg.get_aligner_backend = lambda cfg: MockAligner(cfg)

    with open(ws.aligned_jsonl) as f:
        lines = [AlignedSegment.model_validate_json(line.strip()) for line in f]

    for seg, orig in zip(lines, texts):
        assert seg.text == orig


def test_cli_align_runnable(test_config: SubtapConfig, tmp_path: Path, monkeypatch):
    """CLI align command runs without crash."""
    from typer.testing import CliRunner
    from subtap.cli import app

    ws = Workspace(test_config, base_dir=tmp_path / "work")
    _make_sentences_jsonl(ws, ["CLI sentence"])

    import subtap.backends.align as align_reg

    monkeypatch.setattr(align_reg, "get_aligner_backend", lambda cfg: MockAligner(cfg))
    import subtap.schemas.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_config", lambda p: test_config)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "align",
            str(ws.sentences_jsonl),
            "-w",
            str(ws.root),
            "-b",
            "mock-aligner",
        ],
    )
    assert result.exit_code == 0
    assert "完成" in result.output
