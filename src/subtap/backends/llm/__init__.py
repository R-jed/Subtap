"""LLM backend registry and factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from subtap.schemas.config import CleanConfig

if TYPE_CHECKING:
    from subtap.backends.llm.base import LLMBackend


def get_llm_backend(config: CleanConfig) -> LLMBackend:
    """Instantiate an LLM backend by name.

    Supports formats:
      - "ollama:<model>"  → OllamaLLM
      - "openai:<model>"  → OpenAICompatibleLLM
      - "lmstudio:<model>" → LMStudioLLM (stub)
    """
    backend_str = config.backend

    if backend_str.startswith("ollama:"):
        model = backend_str.split(":", 1)[1]
        from subtap.backends.llm.ollama import OllamaLLM
        return OllamaLLM(model=model)
    elif backend_str.startswith("openai:"):
        model = backend_str.split(":", 1)[1]
        from subtap.backends.llm.openai_compat import OpenAICompatibleLLM
        return OpenAICompatibleLLM(model=model)
    elif backend_str.startswith("lmstudio:"):
        model = backend_str.split(":", 1)[1]
        from subtap.backends.llm.lmstudio import LMStudioLLM
        return LMStudioLLM(model=model)
    else:
        raise ValueError(f"Unknown LLM backend: {backend_str}")
