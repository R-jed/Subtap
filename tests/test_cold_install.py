"""Cold install script behavior tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def test_cold_install_script_exists():
    script = Path("scripts/cold_install_test.sh")
    assert script.exists(), "cold_install_test.sh 不存在"
    assert script.stat().st_mode & 0o111, "脚本不可执行"


def test_cold_install_script_is_bash():
    script = Path("scripts/cold_install_test.sh")
    first_line = script.read_text().split("\n")[0]
    assert "bash" in first_line, "脚本必须使用 bash"


def test_cold_install_script_checks_arm64():
    script = Path("scripts/cold_install_test.sh").read_text()
    assert "arm64" in script, "脚本必须检查 arm64 架构"


def test_cold_install_script_uses_isolated_home():
    script = Path("scripts/cold_install_test.sh").read_text()
    assert "mktemp" in script, "脚本必须使用临时目录"
    assert "MOCK_HOME" in script or "HOME=" in script, "脚本必须设置隔离 HOME"
