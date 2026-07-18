"""Release workflow and destructive acceptance-script safety gates."""

import os
from pathlib import Path
import subprocess
import tomllib
import importlib.util

import yaml
import pytest

ROOT = Path(__file__).parents[1]

NODE24_ACTIONS = {
    "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0  # v7",
    "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1  # v6",
    "astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990  # v8",
}
NODE24_ACTION_NAMES = (
    "actions/checkout@",
    "actions/setup-python@",
    "astral-sh/setup-uv@",
)


def test_cli_version_matches_distribution_version() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    namespace: dict[str, str] = {}
    exec((ROOT / "src/subtap/__init__.py").read_text(), namespace)

    assert namespace["__version__"] == project["project"]["version"]


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


def test_workflows_pin_node24_actions() -> None:
    texts = [
        (ROOT / ".github/workflows/ci.yml").read_text(),
        (ROOT / ".github/workflows/release.yml").read_text(),
    ]

    for text in texts:
        pinned_actions = {
            line.strip().removeprefix("- uses: ")
            for line in text.splitlines()
            if any(name in line for name in NODE24_ACTION_NAMES)
        }
        assert pinned_actions == NODE24_ACTIONS


def test_release_requires_real_offline_1_7b_acceptance() -> None:
    """No public release may bypass the real local-only Apple Silicon pipeline."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    jobs = workflow["jobs"]
    acceptance = jobs["offline-acceptance"]
    steps = "\n".join(str(step) for step in acceptance["steps"])

    assert set(acceptance["runs-on"]) == {
        "self-hosted",
        "macOS",
        "ARM64",
        "subtap-release",
    }
    assert "SUBTAP_SMOKE_AUDIO_DIR" in acceptance["env"]
    assert "SUBTAP_SMOKE_MODEL_ROOT" in acceptance["env"]
    assert "SUBTAP_SMOKE_REFERENCE_SRT" in acceptance["env"]
    assert acceptance["env"]["NODE_OPTIONS"] == "--use-system-ca"
    assert acceptance["needs"] == ["metadata", "build"]
    assert "actions/download-artifact" in steps
    assert "actions/setup-python@" not in steps
    assert "astral-sh/setup-uv@" not in steps
    assert "command -v python3.13" in steps
    assert "command -v uv" in steps
    assert '--python "$(command -v python3.13)"' in steps
    assert "subtap-release-acceptance/bin/subtap" in steps
    assert "SUBTAP_SMOKE_SUBTAP_BIN" in steps
    assert "./scripts/smoke_offline.sh" in steps
    assert "offline-acceptance" in jobs["github-release"]["needs"]
    assert "offline-acceptance" in jobs["publish"]["needs"]


def test_homebrew_release_executes_supply_chain_and_formula_gates() -> None:
    text = (ROOT / ".github/workflows/release.yml").read_text()

    assert "verify-sentencepiece" in text
    assert "--formal-release" in text
    assert "multiple.intoto.jsonl" in text
    assert "slsa-verifier-darwin-arm64" in text
    assert 'brew tap-new "$local_tap"' in text
    assert 'mkdir -p "$tap_dir/Formula"' in text
    assert 'brew install "$local_tap/subtap"' in text
    assert 'brew test "$local_tap/subtap"' in text


def test_release_candidate_cannot_publish_stable_channels() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    jobs = workflow["jobs"]

    assert (
        jobs["publish"]["if"]
        == "${{ needs.metadata.outputs.is_prerelease == 'false' }}"
    )
    assert "homebrew" in jobs
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
    assert project["project"]["version"] == "0.1.0rc5"


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


def test_wheelhouse_archive_name_is_versioned() -> None:
    """build_wheelhouse() produces a versioned archive name."""
    text = (ROOT / "scripts/homebrew_wheelhouse.py").read_text()
    assert "PYTHON_VERSION.replace('.', '')" in text
    assert "macos-arm64-wheelhouse.tar.gz" in text


def test_publish_job_hard_fails_on_prerelease() -> None:
    """Formal PyPI publish must be blocked when the release is a prerelease."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    publish_if = workflow["jobs"]["publish"]["if"]

    assert "is_prerelease" in publish_if
    assert "false" in publish_if
    # The publish job must depend on metadata so is_prerelease is available
    assert "metadata" in workflow["jobs"]["publish"]["needs"]


def test_rc_build_detected_as_prerelease() -> None:
    """RC version tags must be flagged as prerelease, not formal release."""
    path = ROOT / "scripts/release_metadata.py"
    spec = importlib.util.spec_from_file_location("release_metadata", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # RC versions are prerelease
    assert module.validate_tag("v0.2.0rc1", "0.2.0rc1") is True
    # Alpha and beta are also prerelease
    assert module.validate_tag("v0.2.0a1", "0.2.0a1") is True
    assert module.validate_tag("v0.2.0b1", "0.2.0b1") is True
    # Dev versions are prerelease
    assert module.validate_tag("v0.2.0.dev1", "0.2.0.dev1") is True


def test_github_release_marks_prerelease_flag() -> None:
    """The GitHub Release step must propagate the prerelease flag from metadata."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    release_step = next(
        step
        for step in workflow["jobs"]["github-release"]["steps"]
        if step.get("name") == "Upload GitHub Release assets"
    )
    prerelease_value = release_step["with"]["prerelease"]
    assert "is_prerelease" in prerelease_value
    assert "metadata" in prerelease_value


def test_homebrew_acceptance_preserves_user_data_across_lifecycle() -> None:
    """Acceptance script verifies sentinel files survive install/upgrade/rollback/uninstall."""
    text = (ROOT / "scripts/homebrew_acceptance.sh").read_text()

    # Sentinel creation happens before any install
    assert "acceptance-sentinel" in text
    assert "for directory in models glossaries manuscripts jobs" in text

    # Sentinel verification happens after final uninstall
    # Find the final verification block (after "final uninstall")
    final_uninstall_idx = text.index("final uninstall")
    final_check = text[final_uninstall_idx:]
    assert "acceptance-sentinel" in final_check
    assert "user data removed" in final_check


def test_homebrew_acceptance_ab_versioned_wheelhouse_url() -> None:
    """Acceptance script upgrade path uses versioned wheelhouse references."""
    text = (ROOT / "scripts/homebrew_acceptance.sh").read_text()

    # The script must install a previous formula first, then upgrade
    assert "brew install" in text
    assert "brew upgrade subtap" in text

    # After upgrade, version must differ from previous
    assert 'test "$upgraded_version" != "$previous_version"' in text

    # After rollback, version must match previous
    assert 'test "$rollback_version" = "$previous_version"' in text


def test_wheelhouse_attestation_in_workflow() -> None:
    """The workflow must attest wheelhouse build provenance alongside dist artifacts."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    attest_job = workflow["jobs"]["attest"]

    assert attest_job["permissions"]["attestations"] == "write"
    assert attest_job["permissions"]["id-token"] == "write"
    # attest must be a dependency of github-release and publish
    assert "attest" in workflow["jobs"]["github-release"]["needs"]
    assert "attest" in workflow["jobs"]["publish"]["needs"]


def test_release_builds_and_publishes_homebrew_assets() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    homebrew = workflow["jobs"]["homebrew"]
    steps = "\n".join(str(step) for step in homebrew["steps"])

    assert homebrew["runs-on"] == "macos-14"
    assert "homebrew_wheelhouse.py build" in steps
    assert "render_homebrew_formula.py" in steps
    assert "brew install ffmpeg numpy scipy" in steps
    assert any(
        step.get("with", {}).get("name") == "homebrew" for step in homebrew["steps"]
    )
    assert "homebrew" in workflow["jobs"]["attest"]["needs"]
    assert "homebrew" in workflow["jobs"]["github-release"]["needs"]


def test_release_attests_and_uploads_all_release_assets() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    attest_steps = workflow["jobs"]["attest"]["steps"]
    release_steps = workflow["jobs"]["github-release"]["steps"]

    assert workflow["jobs"]["attest"]["needs"] == ["build", "homebrew"]
    assert any(step.get("with", {}).get("name") == "homebrew" for step in attest_steps)
    assert any(step.get("with", {}).get("name") == "homebrew" for step in release_steps)
    attestation = next(
        step
        for step in attest_steps
        if step.get("name") == "Generate build provenance attestation"
    )
    assert attestation["with"]["subject-path"] == "release-assets/"
    release = next(
        step
        for step in release_steps
        if step.get("name") == "Upload GitHub Release assets"
    )
    assert release["with"]["files"] == "release-assets/**/*"


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
