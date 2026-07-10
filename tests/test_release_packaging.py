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
    assert not any("/models/" in name for name in names)


def test_runtime_dependencies_include_textual_for_tui():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"textual>=' in pyproject
