"""Phase 21: 验证 enhance=off 模式。"""

from __future__ import annotations

from subtap.enhancement.base import EnhancementMode
from subtap.enhancement.tasks import get_tasks_for_mode


def test_enhance_off_has_no_tasks():
    """enhance=off 模式不应有任何增强任务。"""
    tasks = get_tasks_for_mode("off")
    assert tasks == []


def test_enhance_off_mode_enum():
    """EnhancementMode.OFF 存在。"""
    assert EnhancementMode.OFF.value == "off"
