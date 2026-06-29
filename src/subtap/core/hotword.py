"""Pipeline hotword stage — replace ASR errors with correct terms."""

from __future__ import annotations

import json
from pathlib import Path

from subtap.glossary.engine import HotwordEngine
from subtap.core.workspace import Workspace


def run_hotword(
    workspace: Workspace,
    glossary_dir: Path | None = None,
    mode: str = "local",
    lang: str = "zh",
) -> dict:
    """Run hotword replacement on cleaned segments.

    Reads cleaned.jsonl, applies hotword replacement, writes back.
    """
    input_path = workspace.cleaned_jsonl
    if not input_path.exists():
        return {"replaced": 0, "total": 0}

    engine = HotwordEngine(mode=mode, glossary_dir=glossary_dir)

    # Read segments
    segments = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                segments.append(json.loads(line))

    # Apply hotword replacement
    replaced_count = 0
    for seg in segments:
        original = seg.get("text", "")
        corrected = engine.process(original, lang=lang)
        if corrected != original:
            seg["text"] = corrected
            replaced_count += 1

    # Write back
    with open(input_path, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(json.dumps(seg, ensure_ascii=False) + "\n")

    return {
        "replaced": replaced_count,
        "total": len(segments),
        "mode": mode,
        "lang": lang,
    }
