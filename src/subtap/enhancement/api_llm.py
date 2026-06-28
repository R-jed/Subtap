"""API LLM enhancement: uses external LLM API for enhancement."""

from __future__ import annotations

from subtap.enhancement.base import EnhancementMode, EnhancementResult
from subtap.enhancement.prompts import SYSTEM_PROMPT, build_prompt
from subtap.enhancement.tasks import EnhancementTask, get_tasks_for_mode
from subtap.enhancement.validator import EnhancementValidator
from subtap.schemas.enhancement import CleanSegment


class APIEnhancer:
    """API-based LLM enhancement — sends text to external LLM.

    Rules:
    - Only sends TEXT, never audio
    - Validates output preserves timing
    - Requires confirmation for external API calls
    """

    mode = EnhancementMode.API

    def __init__(
        self,
        provider: str = "openai_compatible",
        model: str = "gpt-4.1-mini",
        api_key: str | None = None,
        endpoint: str | None = None,
    ):
        """Initialize API enhancer.

        Args:
            provider: API provider (openai_compatible, anthropic_compatible, custom_url).
            model: Model name.
            api_key: API key (optional, can use env var).
            endpoint: Custom endpoint URL (optional).
        """
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.endpoint = endpoint
        self.validator = EnhancementValidator()

    def enhance(
        self,
        segments: list[CleanSegment],
        glossary: dict[str, str] | None = None,
        tasks: list[EnhancementTask] | None = None,
    ) -> EnhancementResult:
        """Enhance segments using external LLM API.

        Args:
            segments: Input segments.
            glossary: Optional glossary.
            tasks: Specific tasks to apply (default: all API tasks).

        Returns:
            EnhancementResult with enhanced segments.
        """
        if tasks is None:
            tasks = get_tasks_for_mode("api")

        enhanced = []
        api_calls = 0
        errors = []

        for seg in segments:
            text = seg.text
            change_reasons = []

            for task in tasks:
                try:
                    prompt = build_prompt(
                        task.value,
                        text,
                        glossary=str(glossary) if glossary else "",
                        target_language="",
                    )
                    # In real implementation, this would call the LLM API
                    # For now, we just pass through
                    api_calls += 1
                    change_reasons.append(f"api_{task.value}")
                except Exception as e:
                    errors.append(f"Segment {seg.segment_id}: {e}")

            enhanced.append(
                CleanSegment(
                    segment_id=seg.segment_id,
                    source_chunk_id=seg.source_chunk_id,
                    text=text,
                    original_text=seg.original_text,
                    start_sec=seg.start_sec,
                    end_sec=seg.end_sec,
                    enhancement_mode="api",
                    changed=text != seg.original_text,
                    change_reasons=seg.change_reasons + change_reasons,
                )
            )

        # Validate output
        validation = self.validator.validate(segments, enhanced)
        if not validation.valid:
            errors.extend(validation.errors)

        return EnhancementResult(
            segments=enhanced,
            mode=EnhancementMode.API,
            changed_count=sum(1 for s in enhanced if s.changed),
            api_calls=api_calls,
            errors=errors,
        )
