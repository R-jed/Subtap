"""Translate aligned subtitles after source-language alignment."""

from __future__ import annotations

import re
from pathlib import Path

from subtap.backends.llm import get_llm_backend
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import AlignedSegment


def _format_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _load_aligned(path: Path) -> list[AlignedSegment]:
    return [
        AlignedSegment.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_aligned(path: Path, segments: list[AlignedSegment]) -> None:
    path.write_text(
        "".join(segment.model_dump_json() + "\n" for segment in segments),
        encoding="utf-8",
    )


def render_srt_from_aligned(aligned_jsonl: Path) -> str:
    blocks = []
    for index, segment in enumerate(_load_aligned(aligned_jsonl), start=1):
        blocks.append(
            f"{index}\n"
            f"{_format_time(segment.start_sec)} --> {_format_time(segment.end_sec)}\n"
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

    llm = get_llm_backend(clean_config, config.remote_api)
    source_srt = render_srt_from_aligned(workspace.aligned_jsonl)
    source_blocks = parse_srt(source_srt)
    translated_srt = llm.translate_srt(source_srt, target_language)
    translated_blocks = parse_srt(translated_srt)
    validate_translated_srt(source_blocks, translated_blocks)

    segments = _load_aligned(workspace.aligned_jsonl)
    for segment, block in zip(segments, translated_blocks):
        segment.translated_text = block["text"]
    _write_aligned(workspace.aligned_jsonl, segments)
    return {"translated_count": len(segments), "target_language": target_language}
