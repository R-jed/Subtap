"""Translate aligned subtitles after source-language alignment."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from subtap.backends.llm import get_translator
from subtap.core.export import _fmt_srt_time, load_aligned
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import AlignedSegment

logger = logging.getLogger(__name__)

CHUNK_SIZE = 30
CONTEXT_OVERLAP = 3


def _write_aligned(path: Path, segments: list[AlignedSegment]) -> None:
    tmp_path = path.with_suffix(".jsonl.tmp")
    try:
        tmp_path.write_text(
            "".join(segment.model_dump_json() + "\n" for segment in segments),
            encoding="utf-8",
        )
        tmp_path.rename(path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def render_srt_from_aligned(aligned_jsonl: Path) -> str:
    blocks = []
    for index, segment in enumerate(load_aligned(aligned_jsonl), start=1):
        blocks.append(
            f"{index}\n"
            f"{_fmt_srt_time(segment.start_sec)} --> {_fmt_srt_time(segment.end_sec)}\n"
            f"{segment.text}\n"
        )
    return "\n".join(blocks)


def parse_srt(srt_text: str) -> list[dict]:
    normalized = srt_text.strip().replace("\r\n", "\n")
    if not normalized:
        raise ValueError("翻译返回空 SRT")

    blocks: list[dict] = []
    for raw_block in re.split(r"\n{2,}", normalized):
        lines = raw_block.split("\n")
        if len(lines) < 3:
            raise ValueError("翻译返回非法 SRT")
        try:
            index = int(lines[0].strip())
        except ValueError as exc:
            raise ValueError("翻译返回非法 SRT 序号") from exc
        match = re.match(
            r"^(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})$",
            lines[1].strip(),
        )
        if not match:
            raise ValueError("翻译返回非法 SRT 时间轴")
        text = "\n".join(lines[2:]).strip()
        if not text:
            raise ValueError(f"翻译返回空字幕文本：{index}")
        blocks.append(
            {
                "index": index,
                "start": match.group(1),
                "end": match.group(2),
                "text": text,
            }
        )
    return blocks


def validate_translated_srt(source: list[dict], translated: list[dict]) -> None:
    if len(source) != len(translated):
        raise ValueError("翻译返回字幕块数量不一致")
    for source_block, translated_block in zip(source, translated):
        if source_block["index"] != translated_block["index"]:
            raise ValueError("翻译返回序号不一致")
        if (
            source_block["start"] != translated_block["start"]
            or source_block["end"] != translated_block["end"]
        ):
            raise ValueError("翻译返回时间轴不一致")


def _blocks_to_srt(blocks: list[dict]) -> str:
    """Convert parsed blocks back to SRT format."""
    parts = []
    for block in blocks:
        parts.append(
            f"{block['index']}\n"
            f"{block['start']} --> {block['end']}\n"
            f"{block['text']}"
        )
    return "\n\n".join(parts) + "\n"


def _build_chunk_prompt(
    context_before_srt: str,
    to_translate_srt: str,
    context_after_srt: str,
    target_language: str,
) -> str:
    """Build a chunk translation prompt with context markers."""
    parts = [
        "以下是字幕翻译任务。请只翻译标记为【待翻译】的部分。",
    ]
    if context_before_srt:
        parts.append("【上文参考】（仅供理解上下文，无需翻译）")
        parts.append(context_before_srt)
    parts.append("【待翻译】")
    parts.append(to_translate_srt)
    if context_after_srt:
        parts.append("【下文参考】（仅供理解上下文，无需翻译）")
        parts.append(context_after_srt)
    parts.append("")
    parts.append(f"要求：将【待翻译】部分翻译为{target_language}。")
    parts.append("1. 保持序号和时间轴完全不变")
    parts.append("2. 只翻译文本内容")
    parts.append("3. 输出格式与输入完全一致的 SRT")
    parts.append("4. 只输出【待翻译】部分的翻译结果，不要输出上下文参考部分")
    parts.append("5. 译文要自然、口语化、准确、简洁")
    parts.append("6. 不要输出解释、备注、分析，只输出合法的 SRT 内容")
    return "\n".join(parts)


def _chunk_and_translate(
    llm,
    source_blocks: list[dict],
    target_language: str,
) -> list[dict]:
    """Translate SRT in chunks with context overlap.

    Args:
        llm: LLM backend with translate_srt method.
        source_blocks: Parsed source SRT blocks.
        target_language: Target language for translation.

    Returns:
        List of translated blocks (same count as source_blocks).
    """
    total = len(source_blocks)
    translated_blocks: list[dict] = []

    for chunk_start in range(0, total, CHUNK_SIZE):
        chunk_end = min(chunk_start + CHUNK_SIZE, total)

        # Context window: extend before and after
        ctx_start = max(0, chunk_start - CONTEXT_OVERLAP)
        ctx_end = min(total, chunk_end + CONTEXT_OVERLAP)

        context_before = source_blocks[ctx_start:chunk_start]
        to_translate = source_blocks[chunk_start:chunk_end]
        context_after = source_blocks[chunk_end:ctx_end]

        # Build SRT strings
        ctx_before_srt = _blocks_to_srt(context_before) if context_before else ""
        to_translate_srt = _blocks_to_srt(to_translate)
        ctx_after_srt = _blocks_to_srt(context_after) if context_after else ""

        # Build prompt and translate
        prompt = _build_chunk_prompt(
            ctx_before_srt, to_translate_srt, ctx_after_srt, target_language
        )

        chunk_num = chunk_start // CHUNK_SIZE + 1
        total_chunks = (total + CHUNK_SIZE - 1) // CHUNK_SIZE
        logger.info(
            "翻译分块 %d/%d (句 %d-%d)",
            chunk_num, total_chunks, chunk_start + 1, chunk_end,
        )

        translated_srt = llm.translate_srt(
            to_translate_srt, target_language, custom_prompt=prompt
        )
        chunk_translated = parse_srt(translated_srt)

        # Validate this chunk
        validate_translated_srt(to_translate, chunk_translated)
        translated_blocks.extend(chunk_translated)

        logger.info("分块 %d/%d 翻译完成", chunk_num, total_chunks)

    return translated_blocks


def run_translate(
    workspace: Workspace,
    config: SubtapConfig,
    target_language: str,
    llm_backend_name: str | None = None,
) -> dict:
    clean_config = config.clean.model_copy()
    if llm_backend_name:
        if not llm_backend_name.startswith("openai:"):
            raise ValueError("翻译只支持 OpenAI-compatible LLM 后端")
        clean_config.backend = llm_backend_name
    else:
        clean_config.backend = f"openai:{config.remote_api.model or 'gpt-4o-mini'}"

    llm = get_translator(clean_config, config.remote_api)
    source_srt = render_srt_from_aligned(workspace.aligned_jsonl)
    source_blocks = parse_srt(source_srt)

    # 分块翻译
    translated_blocks = _chunk_and_translate(llm, source_blocks, target_language)

    segments = load_aligned(workspace.aligned_jsonl)
    for segment, block in zip(segments, translated_blocks):
        segment.translated_text = block["text"]
    _write_aligned(workspace.aligned_jsonl, segments)
    return {"translated_count": len(segments), "target_language": target_language}
