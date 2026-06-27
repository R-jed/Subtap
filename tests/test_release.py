"""Release verification tests."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_pip_install():
    """Test pip install works."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", "."],
        capture_output=True,
        text=True,
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

        with patch("sys.argv", ["subtap", "setup", "--help"]):
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
        [sys.executable, "-m", "subtap.cli", "doctor"], capture_output=True, text=True
    )
    assert result.returncode == 0


def test_subtap_demo_help():
    """Test subtap demo --help works."""
    result = subprocess.run(
        [sys.executable, "-m", "subtap.cli", "demo", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_subtap_run_help():
    """Test subtap run --help works."""
    result = subprocess.run(
        [sys.executable, "-m", "subtap.cli", "run", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_subtap_models_list():
    """Test subtap models list works."""
    result = subprocess.run(
        [sys.executable, "-m", "subtap.cli", "models", "list"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_readme_documents_development_model_sources():
    """Test README documents development model sources."""
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "macOS 开发版" in text
    assert "models/asr_0.6b" in text
    assert "https://hf-mirror.com" in text
    assert "Homebrew" not in text


def test_release_check_does_not_require_model_download():
    """Test release-check does not require model download."""
    text = (PROJECT_ROOT / "scripts/release-check.sh").read_text(encoding="utf-8")

    assert "subtap setup --skip-models" in text
    assert "--download-source hf" not in text


def test_ci_runs_release_check():
    """Test GitHub Actions CI delegates to release-check."""
    ci_path = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    text = ci_path.read_text(encoding="utf-8")

    assert "macos" in text
    assert "scripts/release-check.sh" in text
