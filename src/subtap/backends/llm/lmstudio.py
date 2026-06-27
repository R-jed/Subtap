"""LMStudio LLM backend stub.

LMStudio exposes an OpenAI-compatible API locally.
This is a thin wrapper — for now delegates to OpenAICompatibleLLM.
"""

from __future__ import annotations

import logging
from typing import Optional

from subtap.schemas.glossary import Glossary
from subtap.schemas.models import CleanSegment

logger = logging.getLogger(__name__)


class LMStudioLLM:
    """LLM backend using LMStudio local API (stub)."""

    name = "lmstudio"

    def __init__(
        self, model: str = "default", base_url: str = "http://localhost:1234/v1"
    ):
        self.model = model
        self.base_url = base_url

    def clean_segments(
        self,
        segments: list[CleanSegment],
        glossary: Optional[Glossary] = None,
        style_rules: Optional[list[str]] = None,
    ) -> list[CleanSegment]:
        """LMStudio stub — delegates to OpenAI-compatible API.

        LMStudio serves at localhost:1234 with OpenAI-compatible format.
        """
        from subtap.backends.llm.openai_compat import OpenAICompatibleLLM

        delegate = OpenAICompatibleLLM(
            model=self.model,
            base_url=self.base_url,
            api_key="lm-studio",
        )
        return delegate.clean_segments(segments, glossary, style_rules)
