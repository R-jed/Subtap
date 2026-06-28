"""OpenAI-compatible LLM backend for text cleaning."""

from __future__ import annotations

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
        self.base_url = (
            (remote_api.base_url if remote_api and remote_api.base_url else None)
            or base_url
            or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        api_key_env = remote_api.api_key_env if remote_api else "OPENAI_API_KEY"
        self.api_key = api_key or os.environ.get(api_key_env, "")
        self.timeout_sec = remote_api.timeout_sec if remote_api else 120
        self.provider = remote_api.provider if remote_api else "openai-compatible"

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
