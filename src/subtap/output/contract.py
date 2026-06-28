"""Stable output contract helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_contract_artifacts(
    work_dir: Path,
    output_dir: Path,
    *,
    quality: dict[str, Any] | None = None,
) -> Path:
    """Write stable debug artifacts into output/latest/artifacts."""
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    artifacts = {
        "asr_draft": _read_jsonl(work_dir / "asr" / "asr_draft.jsonl"),
        "clean_segments": _read_jsonl(work_dir / "cleaned.jsonl"),
        "sentence_candidates": _read_jsonl(work_dir / "sentences.jsonl"),
        "aligned_subtitles": _read_jsonl(work_dir / "aligned_subtitles.jsonl"),
        "quality": quality or {},
    }
    for name, payload in artifacts.items():
        (artifacts_dir / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return artifacts_dir
