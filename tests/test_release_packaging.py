"""Release package content checks."""

from __future__ import annotations

from pathlib import Path
import tarfile

import pytest


def test_sdist_excludes_runtime_test_artifacts():
    sdists = sorted(Path("dist").glob("subtap-*.tar.gz"))
    if not sdists:
        pytest.skip("sdist not built; run `python -m build` before this check")

    with tarfile.open(sdists[-1]) as tf:
        names = tf.getnames()

    assert not any("/work_test_vad" in name for name in names)
    assert not any("/work_test_" in name for name in names)
    assert not any(name.endswith("/.coverage") for name in names)
    assert not any("/.superpowers/" in name for name in names)
    assert not any("/graphify-out/" in name for name in names)
    assert not any("/models/model.safetensors" in name for name in names)
    assert any(name.endswith("/configs/models/manifest.yaml") for name in names)


def test_runtime_dependencies_include_textual_for_tui():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"textual>=' in pyproject


def test_runtime_dependencies_include_mlx_for_local_pipeline():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"mlx>=' in pyproject
    assert '"mlx-audio==0.4.3' in pyproject
    assert "platform_system == 'Darwin'" in pyproject


def test_install_script_does_not_claim_release_verification_after_plain_doctor():
    install_script = Path("scripts/install.sh").read_text(encoding="utf-8")

    assert 'info "安装验证通过"' not in install_script
    assert "doctor --release" in install_script or "doctor 输出" in install_script
