"""Smoke offline script behavior tests."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_smoke_offline_script_exists():
    script = Path("scripts/smoke_offline.sh")
    assert script.exists(), "smoke_offline.sh 不存在"
    assert script.stat().st_mode & 0o111, "脚本不可执行"


def test_smoke_offline_uses_isolated_home():
    script = Path("scripts/smoke_offline.sh").read_text()
    assert "mktemp" in script, "脚本必须使用临时目录"
    assert "SMOKE_HOME" in script, "脚本必须设置隔离 HOME"


def test_smoke_offline_disables_network():
    script = Path("scripts/smoke_offline.sh").read_text()
    assert "127.0.0.1:9" in script or "PROXY" in script, "脚本必须禁用网络"


def test_smoke_offline_checks_srt_delivery():
    script = Path("scripts/smoke_offline.sh").read_text()
    assert "check_srt_delivery" in script, "脚本必须检查 SRT 交付"


def test_smoke_offline_accepts_json_output():
    script = Path("scripts/smoke_offline.sh").read_text()
    assert "JSON" in script or "json" in script, "脚本应支持 JSON 输出"
