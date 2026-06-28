"""Enhancement tasks: defines what each enhancement mode does."""

from __future__ import annotations

import enum


class EnhancementTask(enum.Enum):
    """Enhancement tasks that can be applied."""

    CORRECTION = "correction"  # ASR error correction
    GLOSSARY_CORRECTION = "glossary_correction"  # Glossary-based correction
    AI_HOTWORD_REPLACEMENT = "ai_hotword_replacement"  # Contextual hotword replacement
    CLEANING = "cleaning"  # Text cleanup
    SEGMENTATION = "segmentation"  # Smart sentence splitting
    TRANSLATION = "translation"  # Translation


# Default task configuration per mode
MODE_TASKS: dict[str, list[EnhancementTask]] = {
    "off": [],
    "local": [
        EnhancementTask.GLOSSARY_CORRECTION,
        EnhancementTask.CLEANING,
    ],
    "api": [
        EnhancementTask.CORRECTION,
        EnhancementTask.GLOSSARY_CORRECTION,
        EnhancementTask.AI_HOTWORD_REPLACEMENT,
        EnhancementTask.CLEANING,
        EnhancementTask.SEGMENTATION,
    ],
}


def get_tasks_for_mode(mode: str) -> list[EnhancementTask]:
    """Get enhancement tasks for a given mode.

    Args:
        mode: Enhancement mode (off, local, api).

    Returns:
        List of tasks for the mode.
    """
    return MODE_TASKS.get(mode, [])


def get_tasks_for_mode_with_translation(
    mode: str, target_language: str | None = None
) -> list[EnhancementTask]:
    """Get enhancement tasks including translation if requested.

    Args:
        mode: Enhancement mode.
        target_language: Target language for translation (if any).

    Returns:
        List of tasks for the mode.
    """
    tasks = get_tasks_for_mode(mode)
    if target_language:
        tasks = tasks + [EnhancementTask.TRANSLATION]
    return tasks
