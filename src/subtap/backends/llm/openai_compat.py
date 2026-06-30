"""OpenAI-compatible LLM backend for text cleaning."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import httpx

from subtap.schemas.config import RemoteAPIConfig
from subtap.schemas.glossary import Glossary
from subtap.schemas.models import CleanSegment

logger = logging.getLogger(__name__)

_CLEAN_SYSTEM_PROMPT = """\
You are a subtitle text cleaner. Your ONLY job is to fix ASR transcription errors.

Rules (MUST follow):
- Do NOT change the meaning or semantics
- Do NOT summarize or shorten
- Do NOT delete any content
- Only fix: ASR misrecognitions, missing punctuation, unnatural word breaks
- Keep the same language as the input
- Return ONLY the cleaned text, nothing else
"""


class OpenAICompatibleLLM:
    """LLM backend using OpenAI-compatible API (works with any compatible endpoint)."""

    name = "openai"

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        api_key: str | None = None,
        remote_api: RemoteAPIConfig | None = None,
    ):
        self.model = remote_api.model if remote_api and remote_api.model else model
        if remote_api:
            self.base_url = (
                remote_api.base_url.rstrip("/") if remote_api.base_url else ""
            )
        else:
            self.base_url = (
                base_url
                or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            ).rstrip("/")
        api_key_env = remote_api.api_key_env if remote_api else "OPENAI_API_KEY"
        self.api_key = api_key or os.environ.get(api_key_env, "")
        self.timeout_sec = remote_api.timeout_sec if remote_api else 120
        self.provider = remote_api.provider if remote_api else "openai-compatible"

        if not self.base_url:
            raise ValueError("LLM API base_url 未配置")
        if not self.api_key:
            raise ValueError(f"LLM API key 环境变量未配置：{api_key_env}")

    def _chat(self, user_prompt: str, system_prompt: str) -> str:
        with httpx.Client(timeout=self.timeout_sec) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_segments_json(
        self,
        content: str,
        input_indexes: set[int],
        *,
        require_text: bool,
    ) -> list[dict]:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM 返回不是合法 JSON") from exc

        if not isinstance(payload, dict):
            raise ValueError("LLM 返回不是合法 JSON 对象")

        segments = payload.get("segments")
        if not isinstance(segments, list):
            raise ValueError("LLM JSON 缺少 segments 列表")

        seen: set[int] = set()
        parsed: list[dict] = []
        for item in segments:
            if not isinstance(item, dict) or "i" not in item:
                raise ValueError("LLM JSON segment 缺少索引 i")
            index = item["i"]
            if index not in input_indexes:
                raise ValueError(f"LLM 返回非法索引：{index}")
            if index in seen:
                raise ValueError(f"LLM 返回重复索引：{index}")
            seen.add(index)
            if require_text:
                text = str(item.get("t", "")).strip()
                if not text:
                    raise ValueError(f"LLM 返回空文本：{index}")
                parsed.append({"i": index, "t": text})
            else:
                parsed.append({"i": index})
        return parsed

    def select_suspicious_segments(self, segments: list[dict]) -> list[int]:
        prompt = (
            "你是一个字幕质检助，你的任务：\n\n"
            "1. 阅读给定的字幕 segments。\n\n"
            "2. 只返回“可能有问题”的句子：\n\n"
            "- 语义错误\n\n"
            "- 表达不通顺\n\n"
            "- 专业名词 / 品牌 / 产品名可能识别错\n\n"
            "3. 正常句子不要返回。\n\n"
            "4. 不要改写原句，不要解释原因。\n\n"
            "5. 只输出 JSON，格式必须严格为：\n\n"
            '{"segments":[{"i":0}]}\n\n'
            "6. 每个输入项包含：\n"
            "- i: 原始索引\n"
            "- t: 字幕文本\n\n"
            "7. 只返回原始输入里的索引 i。\n\n"
            '8. 如果没有可疑句子，返回 {"segments":[]}\n\n'
            f"待检查内容：\n{json.dumps({'segments': segments}, ensure_ascii=False)}"
        )
        content = self._chat(prompt, "你只输出 JSON，不输出解释。")
        parsed = self._parse_segments_json(
            content,
            {int(item["i"]) for item in segments},
            require_text=False,
        )
        return [int(item["i"]) for item in parsed]

    def repair_segments(self, segments: list[dict]) -> dict[int, str]:
        prompt = (
            "你是一个字幕纠错助手。请只修正给定字幕中的明显错误。\n\n"
            "规则：\n"
            "1. 只修正语义错误、表达不通顺、专业名词 / 品牌 / 产品名识别错误。\n"
            "2. 不要翻译。\n"
            "3. 不要总结、扩写或删除信息。\n"
            "4. 保持原句意思和字幕口语风格。\n"
            "5. 只输出 JSON，格式严格为：\n"
            '{"segments":[{"i":0,"t":"修正后的字幕文本"}]}\n'
            "6. 每个输出 i 必须来自输入。\n"
            "7. 不需要修改的句子不要返回。\n\n"
            f"待处理内容：\n{json.dumps({'segments': segments}, ensure_ascii=False)}"
        )
        content = self._chat(prompt, "你只输出 JSON，不输出解释。")
        parsed = self._parse_segments_json(
            content,
            {int(item["i"]) for item in segments},
            require_text=True,
        )
        return {int(item["i"]): str(item["t"]) for item in parsed}

    def replace_hotwords(
        self, segments: list[dict], glossary: dict | None
    ) -> dict[int, str]:
        prompt = (
            "你是一个字幕热词替换助手。请根据热词表和上下文修正专有名词。\n\n"
            "规则：\n"
            "1. 只在上下文明确指向热词时替换。\n"
            "2. 不确定时保持原文。\n"
            "3. 不要翻译。\n"
            "4. 不合并、删除、新增字幕行。\n"
            "5. 只输出 JSON，格式严格为：\n"
            '{"segments":[{"i":0,"t":"替换后的字幕文本"}]}\n\n'
            f"热词表：\n{json.dumps(glossary or {}, ensure_ascii=False)}\n\n"
            f"待处理内容：\n{json.dumps({'segments': segments}, ensure_ascii=False)}"
        )
        content = self._chat(prompt, "你只输出 JSON，不输出解释。")
        parsed = self._parse_segments_json(
            content,
            {int(item["i"]) for item in segments},
            require_text=True,
        )
        return {int(item["i"]): str(item["t"]) for item in parsed}

    def translate_srt(self, srt_text: str, target_language: str) -> str:
        prompt = (
            f"你是一名经验丰富的影视字幕翻译专家。请将下面的 SRT 字幕翻译为{target_language}。\n\n"
            "翻译目标：\n"
            "1. 保留原字幕的序号、时间轴、分段结构与换行结构，不要新增或删除字幕块。\n"
            "2. 译文要自然、口语化、准确、简洁，符合真实字幕阅读习惯，而不是生硬直译。\n"
            "3. 优先传达说话者真实意图、语气与信息重点；有口头语时可自然化处理，但不要无故扩写。\n"
            "4. 人名、地名、品牌名、产品名、专业术语要结合上下文统一翻译；无法确认时优先保留原文或使用更稳妥写法。\n"
            "5. 数字、年份、日期、时间、百分比、货币、型号、专有缩写等信息必须准确保留，不要误改。\n"
            "6. 如果原文有上下句承接关系，请确保译文衔接自然，不要把句意翻断。\n"
            "7. 每条字幕尽量控制在适合阅读的长度，避免过长、过书面或过于机器化。\n"
            "8. 不要输出解释、备注、分析、前言、后记，只输出合法的 SRT 内容。\n\n"
            f"待翻译内容：\n{srt_text}"
        )
        return self._chat(prompt, "你只输出合法 SRT 内容。")

    def _build_prompt(
        self,
        segments: list[CleanSegment],
        glossary: Optional[Glossary],
        style_rules: Optional[list[str]],
    ) -> str:
        lines = []
        for seg in segments:
            lines.append(f"[{seg.segment_id}] {seg.cleaned_text}")

        text_block = "\n".join(lines)
        instructions = [
            "Fix ASR errors in the following numbered lines.",
            "Return one cleaned line per input, preserving the [id] prefix.",
        ]
        if glossary and glossary.style:
            instructions.append("Style rules: " + "; ".join(glossary.style))
        if style_rules:
            instructions.extend(style_rules)

        return text_block + "\n\n" + "\n".join(instructions)

    def _parse_response(
        self, response_text: str, segments: list[CleanSegment]
    ) -> list[CleanSegment]:
        lines = [
            line.strip() for line in response_text.strip().split("\n") if line.strip()
        ]
        id_map = {seg.segment_id: seg for seg in segments}

        for line in lines:
            match = re.match(r"\[(\d+)\]\s*(.*)", line)
            if match:
                sid = int(match.group(1))
                text = match.group(2).strip()
                if sid in id_map and text:
                    id_map[sid] = id_map[sid].model_copy(update={"cleaned_text": text})

        return [id_map[seg.segment_id] for seg in segments]

    def clean_segments(
        self,
        segments: list[CleanSegment],
        glossary: Optional[Glossary] = None,
        style_rules: Optional[list[str]] = None,
    ) -> list[CleanSegment]:
        if not segments:
            return segments

        prompt = self._build_prompt(segments, glossary, style_rules)

        try:
            with httpx.Client(timeout=self.timeout_sec) as client:
                if self.provider.startswith("anthropic"):
                    resp = client.post(
                        f"{self.base_url}/messages",
                        headers={
                            "x-api-key": self.api_key,
                            "anthropic-version": "2023-06-01",
                        },
                        json={
                            "model": self.model,
                            "max_tokens": 4096,
                            "system": _CLEAN_SYSTEM_PROMPT,
                            "messages": [{"role": "user", "content": prompt}],
                        },
                    )
                else:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": _CLEAN_SYSTEM_PROMPT},
                                {"role": "user", "content": prompt},
                            ],
                        },
                    )
                resp.raise_for_status()
                data = resp.json()
                if self.provider.startswith("anthropic"):
                    content = data["content"][0]["text"]
                else:
                    content = data["choices"][0]["message"]["content"]
                return self._parse_response(content, segments)

        except Exception as e:
            logger.warning("OpenAI-compatible LLM failed: %s, returning original", e)
            return segments
