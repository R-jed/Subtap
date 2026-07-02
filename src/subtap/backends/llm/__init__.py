"""LLM backend registry and factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from subtap.schemas.config import CleanConfig, RemoteAPIConfig

if TYPE_CHECKING:
    from subtap.backends.llm.base import LLMBackend


def get_llm_backend(
    config: CleanConfig, remote_api: RemoteAPIConfig | None = None
) -> LLMBackend:
    """Instantiate an OpenAI-compatible LLM backend.

    Backend string format: "openai:<model>" (e.g. "openai:gpt-4o-mini").
    The actual API endpoint is determined by remote_api.base_url.
    """
    from subtap.backends.llm.openai_compat import OpenAICompatibleLLM

    backend_str = config.backend
    if backend_str.startswith("openai:"):
        model = backend_str.split(":", 1)[1]
    else:
        # Fallback: treat the whole string as model name
        model = backend_str

    return OpenAICompatibleLLM(model=model, remote_api=remote_api)
