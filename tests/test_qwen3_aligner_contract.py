"""Phase 22: Qwen3 ForcedAligner contract."""

from __future__ import annotations

from pathlib import Path

from subtap.core.align import run_align
from subtap.core.workspace import Workspace
from subtap.schemas.alignment import AlignedSubtitle
from subtap.schemas.config import AlignConfig, SubtapConfig
from subtap.schemas.models import AlignedSegment, SentenceSegment


class MockAlignerBackend:
    name = "mlx-qwen-aligner"

    def __init__(self):
        self._model = object()

    def align(self, sentences, audio_path: Path):
        return [
            AlignedSegment(
                sentence_id=sentence.sentence_id,
                start_sec=sentence.start_sec,
                end_sec=sentence.end_sec,
                text=sentence.text,
            )
            for sentence in sentences
        ]

    def release_model(self):
        self._model = None


class MockAlignerWithWords:
    """Mock aligner that returns word-level timing."""

    name = "mlx-qwen-aligner"

    def __init__(self):
        self._model = object()

    def align(self, sentences, audio_path: Path):
        results = []
        for sentence in sentences:
            words = [
                {"word": w, "start_sec": sentence.start_sec + i * 0.1, "end_sec": sentence.start_sec + (i + 1) * 0.1}
                for i, w in enumerate(sentence.text)
            ]
            results.append(AlignedSegment(
                sentence_id=sentence.sentence_id,
                start_sec=words[0]["start_sec"],
                end_sec=words[-1]["end_sec"],
                text=sentence.text,
                words=words,
            ))
        return results

    def release_model(self):
        self._model = None


def test_align_config_supports_model_quantization_and_no_keep_alive():
    """Align config should express model, quantization, and non-resident defaults."""
    config = AlignConfig()
    assert config.model == "aligner"
    assert config.quantization == "q8"
    assert config.keep_model_alive is False
    assert config.warmup is False
    assert config.language == "Chinese"


def test_run_align_writes_aligned_subtitle_contract(monkeypatch, tmp_path):
    """run_align should write AlignedSubtitle final-timing artifact."""
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    workspace.source_audio.write_bytes(b"fake")
    sentence = SentenceSegment(
        sentence_id=0,
        chunk_id=0,
        start_sec=0.0,
        end_sec=1.0,
        text="测试字幕",
        source_text="测试字幕",
    )
    workspace.sentences_jsonl.write_text(
        sentence.model_dump_json() + "\n",
        encoding="utf-8",
    )

    backend = MockAlignerBackend()
    monkeypatch.setattr("subtap.core.align.get_aligner_backend", lambda _cfg: backend)

    result = run_align(workspace, config)

    assert result["aligned_count"] == 1
    assert workspace.aligned_subtitles_jsonl.exists()
    subtitle = AlignedSubtitle.model_validate_json(
        workspace.aligned_subtitles_jsonl.read_text(encoding="utf-8").strip()
    )
    assert subtitle.subtitle_id == 0
    assert subtitle.text == "测试字幕"
    assert backend._model is None


def test_run_align_passthrough_word_level_timing(monkeypatch, tmp_path):
    """run_align should passthrough word-level timing from aligner to AlignedSubtitle."""
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    workspace.source_audio.write_bytes(b"fake")
    sentence = SentenceSegment(
        sentence_id=0,
        chunk_id=0,
        start_sec=0.0,
        end_sec=1.0,
        text="你好世界",
        source_text="你好世界",
    )
    workspace.sentences_jsonl.write_text(
        sentence.model_dump_json() + "\n",
        encoding="utf-8",
    )

    backend = MockAlignerWithWords()
    monkeypatch.setattr("subtap.core.align.get_aligner_backend", lambda _cfg: backend)

    result = run_align(workspace, config)

    assert result["aligned_count"] == 1
    subtitle = AlignedSubtitle.model_validate_json(
        workspace.aligned_subtitles_jsonl.read_text(encoding="utf-8").strip()
    )
    # Words should be populated
    assert len(subtitle.words) == 4  # 你 好 世 界
    assert subtitle.words[0].word == "你"
    assert subtitle.words[0].start_sec < subtitle.words[0].end_sec
    # Sentence time should match first/last word
    assert subtitle.start_sec == subtitle.words[0].start_sec
    assert subtitle.end_sec == subtitle.words[-1].end_sec
