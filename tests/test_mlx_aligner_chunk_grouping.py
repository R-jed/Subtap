"""MLX aligner should align each chunk once, then split words by sentence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from subtap.backends.align.mlx_qwen_align import MLXQwenAligner
from subtap.core.export import run_export
from subtap.schemas.config import AlignConfig
from subtap.schemas.models import SentenceSegment


@dataclass
class FakeWord:
    text: str
    start_time: float
    end_time: float


class FakeModel:
    def __init__(self):
        self.calls: list[str] = []

    def generate(self, *, audio: str, text: str, language: str):
        self.calls.append(text)
        return [
            FakeWord("你", 0.0, 0.2),
            FakeWord("好", 0.2, 0.4),
            FakeWord("世", 0.6, 0.8),
            FakeWord("界", 0.8, 1.0),
        ]


def test_mlx_aligner_aligns_chunk_once_and_splits_sentence_times(tmp_path):
    """Same-chunk sentences should not all start at chunk start."""
    work_dir = tmp_path / "work"
    chunks_dir = work_dir / "chunks"
    audio_dir = work_dir / "audio"
    chunks_dir.mkdir(parents=True)
    audio_dir.mkdir()
    chunk_audio = chunks_dir / "chunk.wav"
    chunk_audio.write_bytes(b"fake")
    (chunks_dir / "chunks.jsonl").write_text(
        json.dumps(
            {
                "chunk_id": 0,
                "start_sec": 1.23,
                "end_sec": 3.0,
                "path": "chunks/chunk.wav",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    aligner = MLXQwenAligner(AlignConfig(time_offset_sec=0))
    fake_model = FakeModel()
    aligner._model = fake_model
    sentences = [
        SentenceSegment(
            sentence_id=0,
            chunk_id=0,
            start_sec=1.23,
            end_sec=2.0,
            text="你好",
            source_text="你好",
        ),
        SentenceSegment(
            sentence_id=1,
            chunk_id=0,
            start_sec=2.0,
            end_sec=3.0,
            text="世界",
            source_text="世界",
        ),
    ]

    result = aligner.align(sentences, audio_dir / "source.wav")

    assert fake_model.calls == ["你好 世界"]
    assert result[0].start_sec == 1.23
    assert result[0].end_sec == 1.63
    assert result[1].start_sec == 1.83
    assert result[1].end_sec == 2.23
    assert result[1].start_sec >= result[0].end_sec


def test_export_preserves_sentence_after_hyphenated_text_alignment(tmp_path):
    """Punctuation omitted by the aligner must not steal the next sentence's first word."""
    work_dir = tmp_path / "work"
    chunks_dir = work_dir / "chunks"
    audio_dir = work_dir / "audio"
    chunks_dir.mkdir(parents=True)
    audio_dir.mkdir()
    (chunks_dir / "chunk.wav").write_bytes(b"fake")
    (chunks_dir / "chunks.jsonl").write_text(
        json.dumps(
            {
                "chunk_id": 0,
                "start_sec": 0.0,
                "end_sec": 3.0,
                "path": "chunks/chunk.wav",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    class HyphenFakeModel:
        def generate(self, *, audio: str, text: str, language: str):
            aligned = "同样APSC画幅比例219光圈25开机快"
            return [
                FakeWord(ch, index * 0.1, (index + 1) * 0.1)
                for index, ch in enumerate(aligned)
            ]

    aligner = MLXQwenAligner(AlignConfig(time_offset_sec=0))
    aligner._model = HyphenFakeModel()
    sentences = [
        SentenceSegment(
            sentence_id=0,
            chunk_id=0,
            start_sec=0.0,
            end_sec=2.0,
            text="同样 APS-C 画幅，比例 21:9，光圈 2.5。",
            source_text="同样 APS-C 画幅，比例 21:9，光圈 2.5。",
        ),
        SentenceSegment(
            sentence_id=1,
            chunk_id=0,
            start_sec=2.0,
            end_sec=3.0,
            text="开机快",
            source_text="开机快",
        ),
    ]

    aligned = aligner.align(sentences, audio_dir / "source.wav")
    aligned_jsonl = work_dir / "aligned.jsonl"
    aligned_jsonl.write_text(
        "".join(segment.model_dump_json() + "\n" for segment in aligned),
        encoding="utf-8",
    )
    result = run_export(aligned_jsonl, tmp_path / "output", fmt="srt")
    content = Path(result["output_path"]).read_text(encoding="utf-8")

    subtitle_text = "".join(
        line
        for block in content.strip().split("\n\n")
        for line in block.splitlines()[2:]
    )
    expected_text = "".join(sentence.text for sentence in sentences)
    assert "".join(filter(str.isalnum, subtitle_text)) == "".join(
        filter(str.isalnum, expected_text)
    )
    assert aligned[1].words[0]["word"] == "开"
    assert aligned[1].start_sec >= aligned[0].end_sec
