"""Word timestamp quality tests."""

from __future__ import annotations

from pathlib import Path

from subtap.core.align import run_align
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import AlignedSegment, SentenceSegment


class MockAlignerWithBadTimestamps:
    """Mock aligner that produces overlapping/zero-duration timestamps."""

    name = "mlx-qwen-aligner"

    def __init__(self):
        self._model = object()

    def align(self, sentences, audio_path: Path):
        results = []
        for sent in sentences:
            # Simulate model output with issues:
            # - "相" has zero duration (start==end)
            # - "机" overlaps with "相" (start < prev end)
            words = [
                {"word": "这", "start_sec": 0.400, "end_sec": 0.640},
                {"word": "台", "start_sec": 0.640, "end_sec": 0.960},
                {"word": "相", "start_sec": 0.960, "end_sec": 0.960},  # zero duration
                {"word": "机", "start_sec": 0.950, "end_sec": 1.120},  # overlaps with 相 (0.950 < 0.960)
                {"word": "从", "start_sec": 1.120, "end_sec": 1.440},
            ]
            results.append(AlignedSegment(
                sentence_id=sent.sentence_id,
                start_sec=words[0]["start_sec"],
                end_sec=words[-1]["end_sec"],
                text=sent.text,
                words=words,
            ))
        return results

    def release_model(self):
        self._model = None


def test_zero_duration_words_fixed(monkeypatch, tmp_path):
    """Words with start==end should get +20ms minimum duration."""
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    workspace.source_audio.write_bytes(b"fake")
    sentence = SentenceSegment(
        sentence_id=0, chunk_id=0, start_sec=0.0, end_sec=2.0,
        text="这台相机从", source_text="这台相机从",
    )
    workspace.sentences_jsonl.write_text(
        sentence.model_dump_json() + "\n", encoding="utf-8",
    )

    backend = MockAlignerWithBadTimestamps()
    monkeypatch.setattr("subtap.core.align.get_aligner_backend", lambda _cfg: backend)

    result = run_align(workspace, config)

    from subtap.schemas.alignment import AlignedSubtitle
    subtitle = AlignedSubtitle.model_validate_json(
        workspace.aligned_subtitles_jsonl.read_text(encoding="utf-8").strip()
    )

    for w in subtitle.words:
        assert w.end_sec > w.start_sec, f"Word '{w.word}' has zero duration"


def test_monotonic_words(monkeypatch, tmp_path):
    """Words should be monotonically ordered: words[i].end <= words[i+1].start."""
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    workspace.source_audio.write_bytes(b"fake")
    sentence = SentenceSegment(
        sentence_id=0, chunk_id=0, start_sec=0.0, end_sec=2.0,
        text="这台相机从", source_text="这台相机从",
    )
    workspace.sentences_jsonl.write_text(
        sentence.model_dump_json() + "\n", encoding="utf-8",
    )

    backend = MockAlignerWithBadTimestamps()
    monkeypatch.setattr("subtap.core.align.get_aligner_backend", lambda _cfg: backend)

    result = run_align(workspace, config)

    from subtap.schemas.alignment import AlignedSubtitle
    subtitle = AlignedSubtitle.model_validate_json(
        workspace.aligned_subtitles_jsonl.read_text(encoding="utf-8").strip()
    )

    for i in range(len(subtitle.words) - 1):
        assert subtitle.words[i].end_sec <= subtitle.words[i + 1].start_sec, (
            f"Word '{subtitle.words[i].word}' end ({subtitle.words[i].end_sec}) "
            f"> word '{subtitle.words[i+1].word}' start ({subtitle.words[i+1].start_sec})"
        )


def test_normal_words_unchanged(monkeypatch, tmp_path):
    """Normal words should not be modified."""
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    workspace.source_audio.write_bytes(b"fake")

    from tests.test_qwen3_aligner_contract import MockAlignerWithWords
    sentence = SentenceSegment(
        sentence_id=0, chunk_id=0, start_sec=0.0, end_sec=1.0,
        text="你好世界", source_text="你好世界",
    )
    workspace.sentences_jsonl.write_text(
        sentence.model_dump_json() + "\n", encoding="utf-8",
    )

    backend = MockAlignerWithWords()
    monkeypatch.setattr("subtap.core.align.get_aligner_backend", lambda _cfg: backend)

    result = run_align(workspace, config)

    from subtap.schemas.alignment import AlignedSubtitle
    subtitle = AlignedSubtitle.model_validate_json(
        workspace.aligned_subtitles_jsonl.read_text(encoding="utf-8").strip()
    )

    for w in subtitle.words:
        assert w.end_sec > w.start_sec
