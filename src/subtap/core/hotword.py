"""Pipeline hotword stage — replace ASR errors with correct terms."""

from __future__ import annotations

import json
from pathlib import Path

from subtap.glossary.hotword import HotwordGlossary, load_glossary
from subtap.core.workspace import Workspace


def _load_glossary_for_lang(
    lang: str, glossary_dir: Path | None = None
) -> HotwordGlossary:
    """Load the canonical default glossary."""
    if glossary_dir is None:
        path = Path.home() / ".subtap" / "glossaries" / "default.yaml"
    else:
        path = glossary_dir / f"hotwords_{lang}.txt"
        if not path.exists():
            path = glossary_dir / f"hotwords_{lang}.tsv"
    return load_glossary(path, lang)


def run_hotword(
    workspace: Workspace,
    glossary_dir: Path | None = None,
    mode: str = "local",
    lang: str = "zh",
) -> dict:
    """Run hotword replacement on aligned segments (post-alignment).

    Reads aligned.jsonl, applies hotword replacement on text field,
    writes back. Preserves word-level timestamps.
    """
    input_path = workspace.aligned_jsonl
    if not input_path.exists():
        return {"replaced": 0, "total": 0}

    glossary = _load_glossary_for_lang(lang, glossary_dir)

    # Read segments
    segments = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                segments.append(json.loads(line))

    # Apply hotword replacement on aligned text
    # Preserve original text in "aligned_text" for word-level timing matching
    # Store replacement pairs for post-split application in exporter
    replaced_count = 0
    for seg in segments:
        original = seg.get("text", "")
        corrected = glossary.replace_in_text(original)
        if corrected != original:
            replacements = glossary.get_applied_replacements(original)
            seg["aligned_text"] = original  # preserve for word filtering
            seg["text"] = corrected
            seg["hotword_replacements"] = replacements  # for post-split application
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
