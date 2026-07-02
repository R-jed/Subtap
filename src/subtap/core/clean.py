"""Clean pipeline stage: ASR segments → replacement → LLM → cleaned.jsonl."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from subtap.backends.llm import get_llm_backend
from subtap.core.export import _ALL_PUNCT_RE, _normalize_punct
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


def local_clean_text(
    text: str,
    glossary: dict | None = None,
    punctuation: bool = False,
    language: str = "zh",
) -> str:
    """Local rule-based text cleaning. No LLM dependency.

    Steps:
    1. Normalize unicode (NFKC)
    2. Normalize full-width digits to half-width
    3. Remove extra whitespace
    4. Remove repeated words (ASR common error)
    5. Handle punctuation (normalize or strip based on config)
    6. Normalize case (English sentences first letter capitalized)
    7. Apply glossary replacements
    """
    # 1. Unicode normalization
    text = unicodedata.normalize("NFKC", text)

    # 2. Full-width digit normalization (１２３ → 123)
    text = re.sub(r"[０-９]", lambda m: chr(ord(m.group()) - 0xFEE0), text)

    # 3. Remove extra spaces
    text = re.sub(r"\s+", " ", text).strip()

    # 4. Remove repeated words (ASR common error, e.g., "的的的" → "的")
    #    Only collapse when same character repeats 3+ times
    text = re.sub(r"([一-鿿])\1{2,}", r"\1", text)
    #    Collapse repeated English words (e.g., "the the the" → "the")
    text = re.sub(r"\b(\w+)(\s+\1){2,}", r"\1", text)

    # 5. Punctuation handling
    if punctuation:
        # Normalize punctuation by language (zh/ja: full-width, en: half-width)
        text = _normalize_punct(text, language)
    else:
        # Replace all punctuation with space, then collapse spaces
        text = _ALL_PUNCT_RE.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()

    # 5b. Fix decimal points corrupted by punctuation normalization (0。6 → 0.6)
    text = re.sub(r"(\d)。(\d)", r"\1.\2", text)

    # 6. Normalize case (English sentences first letter capitalized)
    if language in ("en",):
        text = _capitalize_sentences(text)

    # 7. Glossary replacement
    if glossary:
        for wrong, correct in glossary.items():
            text = text.replace(wrong, correct)

    return text


def _capitalize_sentences(text: str) -> str:
    """Capitalize first letter of each sentence."""
    # Split by sentence-ending punctuation
    sentences = re.split(r"([.!?]+)", text)
    result = []
    for i, part in enumerate(sentences):
        if i % 2 == 0:  # Text parts (not punctuation)
            part = part.strip()
            if part:
                part = part[0].upper() + part[1:]
        result.append(part)
    return "".join(result)


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
    hotword_lang: str = "zh",
    hotword_glossary_dir: str | None = None,
) -> dict:
    """Run clean stage: load ASR → local clean → replacement → LLM → cleaned.jsonl.

    配置优先级：
    1. llm_proofread / llm_hotword 独立配置项（新）
    2. enhance_mode 统一开关（旧，兼容）

    Args:
        workspace: Workspace instance with paths.
        config: Subtap config.
        llm_backend_name: Override LLM backend (e.g. "openai:gpt-4o-mini").
        glossary_path: Path to glossary YAML file.
        style_rules: Additional style rules for LLM.
        enhance_mode: "local" or "api". Controls LLM enhancement level.
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
    # 注意：标点移除后移到 export 阶段，保留标点用于 segment 断句
    punctuation = True  # clean 阶段保留标点，仅做规范化
    language = config.output.subtitle_language
    for seg in replaced:
        seg.cleaned_text = local_clean_text(
            seg.cleaned_text, punctuation=punctuation, language=language
        )

    # 本地热词引擎（始终在 LLM 之前运行，非 LLM 功能）
    if hotword_glossary_dir:
        from subtap.glossary.engine import HotwordEngine

        engine = HotwordEngine(
            mode="local",
            glossary_dir=Path(hotword_glossary_dir),
        )
        for seg in replaced:
            seg.cleaned_text = engine.process(seg.cleaned_text, lang=hotword_lang)

    # 确定 LLM 功能开关
    llm_proofread = config.llm_proofread
    llm_hotword = config.llm_hotword

    # llm_backend_name 控制 LLM 功能（单阶段命令使用）
    if llm_backend_name in {"off", "none", "false"}:
        llm_proofread = False
        llm_hotword = False
    elif enhance_mode == "api":
        # api 模式开启 LLM 功能
        if llm_proofread is None:
            llm_proofread = True
        if not llm_hotword:
            llm_hotword = True
    elif enhance_mode == "local":
        # local 模式不使用 LLM
        llm_proofread = False
        llm_hotword = False

    # 首次接入时，如果 llm_proofread 未设置，默认开启
    if llm_proofread is None:
        llm_proofread = True

    # LLM 增强层
    if llm_proofread or llm_hotword:
        clean_config = config.clean.model_copy()
        if llm_backend_name and llm_backend_name.startswith("openai:"):
            clean_config.backend = llm_backend_name
        else:
            clean_config.backend = f"openai:{config.remote_api.model or 'gpt-4o-mini'}"

        hotword_payload = _hotword_payload(glossary)
        llm = get_llm_backend(clean_config, config.remote_api)
        llm_segments = _segments_for_llm(replaced)

        # AI 校对（质检+纠错）
        if llm_proofread:
            suspicious = llm.select_suspicious_segments(llm_segments)
            if suspicious:
                suspicious_ids = set(suspicious)
                selected = [
                    item for item in llm_segments if item["i"] in suspicious_ids
                ]
                _apply_text_updates(replaced, llm.repair_segments(selected))

        # AI 热词替换（本地热词为空时，AI 自主发现领域专有名词）
        if llm_hotword:
            _apply_text_updates(
                replaced,
                llm.replace_hotwords(_segments_for_llm(replaced), hotword_payload),
            )

    # Filter empty segments
    replaced = [seg for seg in replaced if seg.cleaned_text.strip()]

    # Write cleaned.jsonl
    write_clean_segments(replaced, workspace.cleaned_jsonl)

    return {"segment_count": len(replaced)}
