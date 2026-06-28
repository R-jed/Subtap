"""Phase 21: 验证翻译功能。"""

from __future__ import annotations

from subtap.enhancement.tasks import (
    EnhancementTask,
    get_tasks_for_mode,
    get_tasks_for_mode_with_translation,
)


def test_translation_task_exists():
    """TRANSLATION 任务存在。"""
    assert EnhancementTask.TRANSLATION.value == "translation"


def test_translation_not_in_default_api_tasks():
    """翻译不在默认 API 任务中。"""
    tasks = get_tasks_for_mode("api")
    assert EnhancementTask.TRANSLATION not in tasks


def test_translation_added_when_target_language_set():
    """指定目标语言时添加翻译任务。"""
    tasks = get_tasks_for_mode_with_translation("api", target_language="en")
    assert EnhancementTask.TRANSLATION in tasks


def test_translation_not_added_when_no_target():
    """不指定目标语言时不添加翻译任务。"""
    tasks = get_tasks_for_mode_with_translation("api", target_language=None)
    assert EnhancementTask.TRANSLATION not in tasks


def test_supported_target_languages():
    """支持的目标语言。"""
    # These should be valid
    for lang in ("en", "ja", "zh"):
        tasks = get_tasks_for_mode_with_translation("api", target_language=lang)
        assert EnhancementTask.TRANSLATION in tasks
