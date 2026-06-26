"""Release verification tests."""

import pytest
import subprocess
import sys


def test_pip_install():
    """Test pip install works."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", "."],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0


def test_subtap_setup_help():
    """Test subtap setup --help works."""
    # 使用 Python 直接运行来捕获输出
    import io
    import sys
    from unittest.mock import patch

    # 捕获 stdout
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()

    try:
        from subtap.cli import app
        with patch('sys.argv', ['subtap', 'setup', '--help']):
            try:
                app()
            except SystemExit:
                pass

        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old_stdout

    assert "初始化向导" in output or "用户初始化向导" in output


def test_subtap_doctor():
    """Test subtap doctor works."""
    result = subprocess.run(
        [sys.executable, "-m", "subtap.cli", "doctor"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0


def test_subtap_demo_help():
    """Test subtap demo --help works."""
    result = subprocess.run(
        [sys.executable, "-m", "subtap.cli", "demo", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0


def test_subtap_run_help():
    """Test subtap run --help works."""
    result = subprocess.run(
        [sys.executable, "-m", "subtap.cli", "run", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0


def test_subtap_models_list():
    """Test subtap models list works."""
    result = subprocess.run(
        [sys.executable, "-m", "subtap.cli", "models", "list"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
