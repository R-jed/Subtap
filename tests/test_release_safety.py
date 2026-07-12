"""Release workflow and destructive acceptance-script safety gates."""

import os
from pathlib import Path
import subprocess
import tomllib
import importlib.util

import yaml
import pytest

ROOT = Path(__file__).parents[1]


def test_attestation_blocks_publication() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    jobs = workflow["jobs"]

    assert jobs["attest"]["permissions"]["attestations"] == "write"
    assert "attest" in jobs["github-release"]["needs"]
    assert "attest" in jobs["publish"]["needs"]


def test_release_jobs_are_bounded_and_build_uses_uv() -> None:
    text = (ROOT / ".github/workflows/release.yml").read_text()
    workflow = yaml.safe_load(text)

    assert "pip install build" not in text
    assert "uv build" in text
    assert "uv build --frozen" not in text
    assert "grep -- --tui" not in text
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert all("timeout-minutes" in job for job in workflow["jobs"].values())


def test_release_candidate_cannot_publish_stable_channels() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    jobs = workflow["jobs"]

    assert (
        jobs["publish"]["if"]
        == "${{ needs.metadata.outputs.is_prerelease == 'false' }}"
    )
    assert "homebrew" not in jobs
    assert "metadata" in jobs["publish"]["needs"]
    assert "metadata" in jobs["github-release"]["needs"]
    release_step = next(
        step
        for step in jobs["github-release"]["steps"]
        if step.get("name") == "Upload GitHub Release assets"
    )
    assert (
        release_step["with"]["prerelease"]
        == "${{ needs.metadata.outputs.is_prerelease }}"
    )

    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["version"] == "0.1.0rc2"


def test_release_metadata_requires_exact_tag_and_detects_prerelease() -> None:
    path = ROOT / "scripts/release_metadata.py"
    spec = importlib.util.spec_from_file_location("release_metadata", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.validate_tag("v0.1.0rc1", "0.1.0rc1") is True
    assert module.validate_tag("v0.1.0", "0.1.0") is False
    for invalid in ("v0.1.0-rc1", "v9.9.9", "0.1.0rc1"):
        with pytest.raises(ValueError):
            module.validate_tag(invalid, "0.1.0rc1")


def test_homebrew_acceptance_requires_ephemeral_environment() -> None:
    text = (ROOT / "scripts/homebrew_acceptance.sh").read_text()

    assert "SUBTAP_HOMEBREW_ACCEPTANCE" in text
    assert "brew list --versions subtap" in text
    assert "brew uninstall subtap 2>/dev/null || true" not in text
    assert "brew audit --strict" in text
    assert "brew test r-jed/tap/subtap" in text
    assert 'warn "⚠ brew audit' not in text
    assert 'warn "⚠ brew test' not in text
    assert "PREVIOUS_FORMULA" in text
    assert 'test "$upgraded_version" != "$previous_version"' in text
    assert 'test "$rollback_version" = "$previous_version"' in text
    assert "brew outdated --quiet subtap" not in text
    assert 'payload.get("models_error")' in text


def test_homebrew_acceptance_preseeds_and_preserves_user_data() -> None:
    text = (ROOT / "scripts/homebrew_acceptance.sh").read_text()

    assert "for directory in models glossaries manuscripts jobs" in text
    assert "acceptance-sentinel" in text


def test_homebrew_acceptance_refuses_existing_install(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    home = tmp_path / "home"
    bin_dir.mkdir()
    home.mkdir()
    for name, body in {
        "uname": "#!/bin/sh\necho arm64\n",
        "brew": "#!/bin/sh\n[ \"$1 $2 $3\" = 'list --versions subtap' ]\n",
    }.items():
        path = bin_dir / name
        path.write_text(body)
        path.chmod(0o755)

    env = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(home),
        "SUBTAP_ACCEPTANCE_HOME": str(home),
        "SUBTAP_HOMEBREW_ACCEPTANCE": "1",
    }
    result = subprocess.run(
        [ROOT / "scripts/homebrew_acceptance.sh"],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "refusing to touch an existing Subtap installation" in result.stderr
