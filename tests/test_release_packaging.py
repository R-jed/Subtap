"""Release package content checks."""

from __future__ import annotations

import hashlib
import json
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
    assert any(name.endswith("/resources/silero_vad.onnx") for name in names)
    assert any(name.endswith("/resources/SILERO-VAD-LICENSE") for name in names)
    assert any(name.endswith("/resources/SILERO-VAD-MODEL.json") for name in names)


def test_runtime_dependencies_include_textual_for_tui():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"textual>=' in pyproject


def test_runtime_dependencies_include_mlx_for_local_pipeline():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"mlx>=' in pyproject
    assert '"mlx-audio==0.4.3' in pyproject
    assert "platform_system == 'Darwin'" in pyproject


def test_runtime_dependencies_use_homebrew_safe_vad_backend():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"sherpa-onnx==1.13.4"' in pyproject
    assert '"sherpa-onnx-core==1.13.4"' in pyproject
    assert '"silero-vad' not in pyproject
    assert '"onnxruntime' not in pyproject


def test_bundled_silero_model_matches_recorded_v621_source() -> None:
    model = Path("src/subtap/resources/silero_vad.onnx")
    provenance = json.loads(
        Path("src/subtap/resources/SILERO-VAD-MODEL.json").read_text(encoding="utf-8")
    )

    assert provenance["version"] == "6.2.1"
    assert provenance["wheel_member"] == "silero_vad/data/silero_vad.onnx"
    assert provenance["wheel_sha256"] == (
        "09de93c4d874bb19c53e62a47dd38be5f163cedad2b5599583231f2a84ef79cb"
    )
    assert hashlib.sha256(model.read_bytes()).hexdigest() == provenance["model_sha256"]


def test_install_script_does_not_claim_release_verification_after_plain_doctor():
    install_script = Path("scripts/install.sh").read_text(encoding="utf-8")

    assert 'info "安装验证通过"' not in install_script
    assert "doctor --release" in install_script or "doctor 输出" in install_script
