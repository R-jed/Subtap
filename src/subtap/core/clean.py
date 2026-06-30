"""Clean pipeline stage: ASR segments → replacement → LLM → cleaned.jsonl."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from subtap.backends.llm import get_llm_backend
from subtap.core.replacement import apply_replacements
from subtap.schemas.config import SubtapConfig
from subtap.schemas.glossary import Glossary, load_glossary
from subtap.schemas.models import ASRSegment, CleanSegment
from subtap.core.workspace import Workspace


def load_asr_segments(asr_jsonl: Path) -> list[ASRSegment]:
    """Load ASR segments from JSONL."""
    segments: list[ASRSegment] = []
    with open(asr_jsonl) as f:
        for line in f:
            line = line.strip()
            if line:
                segments.append(ASRSegment.model_validate_json(line))
    return segments


def write_clean_segments(segments: list[CleanSegment], output_path: Path) -> None:
    """Write clean segments to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for seg in segments:
            f.write(seg.model_dump_json() + "\n")


def local_clean_text(text: str, glossary: dict | None = None) -> str:
    """Local rule-based text cleaning. No LLM dependency.

    Steps:
    1. Normalize unicode (NFKC)
    2. Normalize full-width digits to half-width
    3. Remove extra whitespace
    4. Apply glossary replacements
    """
    # 1. Unicode normalization
    text = unicodedata.normalize("NFKC", text)

    # 2. Full-width digit normalization (１２３ → 123)
    text = re.sub(r"[０-９]", lambda m: chr(ord(m.group()) - 0xFEE0), text)

    # 3. Remove extra spaces
    text = re.sub(r"\s+", " ", text).strip()

    # 4. Glossary replacement
    if glossary:
        for wrong, correct in glossary.items():
            text = text.replace(wrong, correct)

    return text


def _segments_for_llm(segments: list[CleanSegment]) -> list[dict]:
    return [{"i": idx, "t": seg.cleaned_text} for idx, seg in enumerate(segments)]


def _apply_text_updates(segments: list[CleanSegment], updates: dict[int, str]) -> None:
    for idx, text in updates.items():
        if idx < 0 or idx >= len(segments):
            raise ValueError(f"LLM 返回非法索引：{idx}")
        clean_text = text.strip()
        if not clean_text:
            raise ValueError(f"LLM 返回空文本：{idx}")
        segments[idx].cleaned_text = clean_text


def _hotword_payload(glossary: Glossary) -> dict[str, list[str]]:
    payload: dict[str, list[str]] = {}

    def add_alias(canonical: str, alias: str) -> None:
        canonical = canonical.strip()
        alias = alias.strip()
        if not canonical or not alias or alias == canonical:
            return
        aliases = payload.setdefault(canonical, [])
        if alias not in aliases:
            aliases.append(alias)

    for term in glossary.terms:
        for alias in term.aliases:
            add_alias(term.canonical, alias)

    for wrong, correct in glossary.get_replacements():
        add_alias(correct, wrong)

    return payload


def run_clean(
    workspace: Workspace,
    config: SubtapConfig,
    llm_backend_name: str | None = None,
    glossary_path: str | None = None,
    style_rules: list[str] | None = None,
    enhance_mode: str | None = None,
    hotword_enabled: bool = True,
    hotword_mode: str = "local",
    hotword_lang: str = "zh",
    hotword_glossary_dir: str | None = None,
) -> dict:
    """Run clean stage: load ASR → local clean → replacement → LLM → cleaned.jsonl.

    Steps:
    1. Load ASR segments from workspace.asr_jsonl
    2. Apply local rule-based cleaning (unicode, full-width digits, whitespace)
    3. Apply deterministic glossary replacements
    4. Pass through LLM backend for ASR error correction (optional)
    5. Write cleaned.jsonl to workspace

    Args:
        workspace: Workspace instance with paths.
        config: Subtap config.
        llm_backend_name: Override LLM backend (e.g. "ollama:qwen3-coder").
        glossary_path: Path to glossary YAML file.
        style_rules: Additional style rules for LLM.
        enhance_mode: "off", "local", or "api".
        hotword_enabled: Whether to run hotword replacement.
        hotword_mode: Hotword engine mode.
        hotword_lang: Hotword glossary language.
        hotword_glossary_dir: Hotword glossary directory override.

    Returns:
        Dict with segment_count.
    """
    # Load ASR segments
    segments = load_asr_segments(workspace.asr_jsonl)
    if not segments:
        raise ValueError(f"No ASR segments found in {workspace.asr_jsonl}")

    # Load glossary
    glossary_file = glossary_path or config.clean.glossary_path
    glossary = load_glossary(Path(glossary_file) if glossary_file else None)

    # Step 1: Deterministic replacement (no LLM)
    replaced = apply_replacements(segments, glossary)

    # Step 2: Local cleaning (always runs, no LLM dependency)
    for seg in replaced:
        seg.cleaned_text = local_clean_text(seg.cleaned_text)

    if llm_backend_name in {"off", "none", "false"}:
        enhance_mode = "off"
    elif enhance_mode is None:
        enhance_mode = "local"

    if enhance_mode not in {"off", "local", "api"}:
        raise ValueError(f"未知增强模式：{enhance_mode}")

    if enhance_mode == "off":
        write_clean_segments(replaced, workspace.cleaned_jsonl)
        return {"segment_count": len(replaced)}

    if hotword_enabled and enhance_mode == "local" and hotword_glossary_dir:
        from subtap.glossary.engine import HotwordEngine

        engine = HotwordEngine(
            mode=hotword_mode,
            glossary_dir=Path(hotword_glossary_dir),
        )
        for seg in replaced:
            seg.cleaned_text = engine.process(seg.cleaned_text, lang=hotword_lang)

    if enhance_mode == "api":
        clean_config = config.clean.model_copy()
        if llm_backend_name and llm_backend_name.startswith("openai:"):
            clean_config.backend = llm_backend_name
        else:
            clean_config.backend = f"openai:{config.remote_api.model or 'gpt-4o-mini'}"

        hotword_payload = _hotword_payload(glossary)
        llm = get_llm_backend(clean_config, config.remote_api)
        llm_segments = _segments_for_llm(replaced)
        suspicious = llm.select_suspicious_segments(llm_segments)
        if suspicious:
            suspicious_ids = set(suspicious)
            selected = [item for item in llm_segments if item["i"] in suspicious_ids]
            _apply_text_updates(replaced, llm.repair_segments(selected))

        if hotword_enabled and hotword_payload:
            _apply_text_updates(
                replaced,
                llm.replace_hotwords(_segments_for_llm(replaced), hotword_payload),
            )

    # Write cleaned.jsonl
    write_clean_segments(replaced, workspace.cleaned_jsonl)

    return {"segment_count": len(replaced)}
