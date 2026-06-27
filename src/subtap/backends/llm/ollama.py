"""Ollama LLM backend for text cleaning."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

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


class OllamaLLM:
    """LLM backend using Ollama local API."""

    name = "ollama"

    def __init__(
        self, model: str = "qwen3-coder", base_url: str = "http://localhost:11434"
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _build_prompt(
        self,
        segments: list[CleanSegment],
        glossary: Optional[Glossary],
        style_rules: Optional[list[str]],
    ) -> str:
        """Build a single prompt for batch cleaning."""
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
        """Parse LLM response and map back to segments."""
        import re

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
        """Send segments to Ollama for cleaning."""
        if not segments:
            return segments

        prompt = self._build_prompt(segments, glossary, style_rules)

        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": _CLEAN_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("message", {}).get("content", "")
                return self._parse_response(content, segments)

        except Exception as e:
            logger.warning("Ollama LLM failed: %s, returning original", e)
            return segments
