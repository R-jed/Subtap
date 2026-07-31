"""Shared pipeline stubs for integration tests.

These stubs replace heavy media/model boundaries at their function
boundaries while preserving real Pipeline, real RichRunner stage loop,
real run_clean(), real segment, and real export.

All stubs follow the workspace-based API used by Pipeline.run_stage().
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from subtap.schemas.models import ASRSegment, Chunk

# ── ASR seed helper ─────────────────────────────────────────


def seed_asr(workspace_or_ws, texts: list[str]) -> None:
    """Write ASR segments to workspace.asr_jsonl.

    Args:
        workspace_or_ws: Workspace object with .asr_dir and .asr_jsonl.
        texts: Text for each segment.  Segments are numbered 0..N-1.
    """
    ws = workspace_or_ws
    ws.asr_dir.mkdir(parents=True, exist_ok=True)
    with open(ws.asr_jsonl, "w") as f:
        for i, text in enumerate(texts):
            seg = ASRSegment(
                chunk_id=0,
                segment_id=i,
                start_sec=float(i),
                end_sec=float(i + 1),
                text=text,
            )
            f.write(seg.model_dump_json() + "\n")


def make_instrumented_init(original_init, texts: list[str]):
    """Return a Pipeline.__init__ wrapper that seeds ASR data after init.

    Args:
        original_init: The real Pipeline.__init__ to wrap.
        texts: Text for each ASR segment to seed.
    """

    def instrumented(self, config, work_dir, **kwargs):
        original_init(self, config, work_dir, **kwargs)
        self.workspace.ensure_dirs()
        seed_asr(self.workspace, texts)

    return instrumented


# ── Pipeline stage stubs ────────────────────────────────────


def stub_prepare(input_path, workspace, config):
    """Stub prepare_media: write media_info.json."""
    info = {"duration": 1.0, "sample_rate": 16000, "channels": 1}
    ws_root = Path(workspace.root)
    ws_root.mkdir(parents=True, exist_ok=True)
    (ws_root / "media_info.json").write_text(json.dumps(info))
    return SimpleNamespace(model_dump=lambda: info)


def stub_prepare_duration(duration: float):
    """Return a prepare_media stub with custom duration."""

    def _stub(input_path, workspace, config):
        info = {"duration": duration, "sample_rate": 16000, "channels": 1}
        ws_root = Path(workspace.root)
        ws_root.mkdir(parents=True, exist_ok=True)
        (ws_root / "media_info.json").write_text(json.dumps(info))
        return SimpleNamespace(model_dump=lambda: info)

    return _stub


def stub_chunks(workspace, config):
    """Stub split_chunks: return one chunk covering [0, 1]."""
    ws_root = Path(workspace.root)
    ws_root.mkdir(parents=True, exist_ok=True)
    chunk = Chunk(
        chunk_id=0,
        start_sec=0.0,
        end_sec=1.0,
        path=str(ws_root / "chunk0.wav"),
    )
    with open(workspace.chunks_jsonl, "w") as f:
        f.write(chunk.model_dump_json() + "\n")
    return [chunk]


def stub_chunks_duration(tmp_path, duration: float = 2.0):
    """Return a split_chunks stub with custom duration and path."""

    def _stub(workspace, config):
        chunk = Chunk(
            chunk_id=0,
            start_sec=0.0,
            end_sec=duration,
            path=str(tmp_path / "chunk0.wav"),
        )
        with open(workspace.chunks_jsonl, "w") as f:
            f.write(chunk.model_dump_json() + "\n")
        return [chunk]

    return _stub


def stub_asr(workspace, config, **kwargs):
    """Stub run_asr: ASR data already seeded."""
    count = 0
    if workspace.asr_jsonl.exists():
        with open(workspace.asr_jsonl) as f:
            count = sum(1 for _ in f)
    return {"segment_count": count}


def stub_align(workspace, config, **kwargs):
    """Stub run_align: read actual sentences.jsonl, write aligned.jsonl."""
    sentences_path = kwargs.get("sentences_path") or workspace.sentences_jsonl
    aligned = []
    with open(sentences_path) as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                aligned.append(
                    {
                        "sentence_id": rec.get("sentence_id", 0),
                        "start_sec": rec.get("start_sec", 0.0),
                        "end_sec": rec.get("end_sec", 1.0),
                        "text": rec["text"],
                    }
                )
    with open(workspace.aligned_jsonl, "w") as f:
        for rec in aligned:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"aligned_count": len(aligned)}


def stub_hotword(workspace, **kwargs):
    """Stub run_hotword: no replacements."""
    return {"replaced": 0, "total": 0}
