"""Fail-fast gates for Homebrew wheelhouse inputs."""

from __future__ import annotations

import base64
from email.message import Message
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/homebrew_wheelhouse.py"
OLD_SENTENCEPIECE_SHA256 = (
    "097f3394e99456e9e4efba1737c3749d7e23563dd1588ce71a3d007f25475fff"
)
MACHO_FIXTURE = b"\xcf\xfa\xed\xfe" + b"\0" * 28


def load_module():
    spec = importlib.util.spec_from_file_location("homebrew_wheelhouse", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_wheel(
    tmp_path: Path,
    name: str = "example",
    version: str = "1.0",
    *,
    license_expression: str | None = "MIT",
    legacy_license: str | None = None,
    declared_license_files: tuple[str, ...] = (),
    license_classifiers: tuple[str, ...] = (),
    license_files: dict[str, str] | None = None,
    extra: dict[str, bytes] | None = None,
) -> Path:
    path = tmp_path / f"{name}-{version}-py3-none-any.whl"
    metadata = Message()
    metadata["Metadata-Version"] = "2.4"
    metadata["Name"] = name
    metadata["Version"] = version
    if license_expression:
        metadata["License-Expression"] = license_expression
    if legacy_license:
        metadata["License"] = legacy_license
    for filename in declared_license_files:
        metadata["License-File"] = filename
    for classifier in license_classifiers:
        metadata["Classifier"] = classifier
    with ZipFile(path, "w") as archive:
        archive.writestr(f"{name}-{version}.dist-info/METADATA", metadata.as_bytes())
        for filename, content in (license_files or {}).items():
            archive.writestr(filename, content)
        for filename, content in (extra or {}).items():
            archive.writestr(filename, content)
    return path


def approved_policy(path: Path, license_id: str = "Apache-2.0") -> dict[str, object]:
    return {
        "allowed_licenses": ["MIT", "Apache-2.0", "BSD-3-Clause"],
        "wheel_approvals": {
            hashlib.sha256(path.read_bytes()).hexdigest(): {
                "license": license_id,
                "approval_file": "docs/approval.md",
                "approved_by": "maintainer",
                "approved_on": "2026-07-13",
                "source_commit": "31646a4",
                "provenance_url": "https://pypi.org/integrity/example/provenance",
            }
        },
    }


def sentencepiece_policy(wheel: Path, **overrides: object) -> dict[str, object]:
    release: dict[str, object] = {
        "filename": wheel.name,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "slsa_subject": f"python/wheelhouse/{wheel.name}",
        "source_tag": "v0.2.2",
        "required_notice_components": [
            "SentencePiece",
            "Abseil",
            "protobuf-lite",
            "darts-clone",
            "esaxx",
            "pybind11",
        ],
    }
    release.update(overrides)
    return {
        "allowed_licenses": ["Apache-2.0"],
        "wheel_approvals": {},
        "sentencepiece_release": release,
    }


def make_bundle(
    tmp_path: Path,
    wheel: Path,
    *,
    tag: str = "v0.2.2",
    commit: str = "e0cce7d37b065b5140349dbe12c6bcf6192fdd78",
    workflow: str = ".github/workflows/wheel.yml",
    subject_name: str | None = None,
) -> Path:
    statement = {
        "subject": [
            {
                "name": subject_name or f"python/wheelhouse/{wheel.name}",
                "digest": {"sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()},
            }
        ],
        "predicate": {
            "invocation": {
                "configSource": {
                    "uri": f"git+https://github.com/google/sentencepiece@refs/tags/{tag}",
                    "digest": {"sha1": commit},
                    "entryPoint": workflow,
                }
            }
        },
    }
    bundle = {
        "dsseEnvelope": {
            "payload": base64.b64encode(json.dumps(statement).encode()).decode()
        }
    }
    path = tmp_path / "multiple.intoto.jsonl"
    path.write_text(json.dumps(bundle) + "\n", encoding="utf-8")
    return path


def rewrite_bundle(bundle_path: Path, field: str, value: object) -> None:
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    statement = json.loads(base64.b64decode(bundle["dsseEnvelope"]["payload"]))
    if field == "subject":
        statement["subject"] = value
    elif field == "configSource":
        statement["predicate"]["invocation"]["configSource"] = value
    else:
        raise AssertionError(field)
    bundle["dsseEnvelope"]["payload"] = base64.b64encode(
        json.dumps(statement).encode()
    ).decode()
    bundle_path.write_text(json.dumps(bundle) + "\n", encoding="utf-8")


def make_notices(tmp_path: Path) -> tuple[Path, list[dict[str, str]]]:
    notices_dir = tmp_path / "third-party"
    notices_dir.mkdir()
    notices = []
    for component in (
        "SentencePiece",
        "Abseil",
        "protobuf-lite",
        "darts-clone",
        "esaxx",
        "pybind11",
    ):
        filename = f"{component.lower()}-LICENSE"
        path = notices_dir / filename
        path.write_text(f"{component} license", encoding="utf-8")
        notices.append(
            {
                "component": component,
                "filename": filename,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return notices_dir, notices


def make_release_inputs(
    tmp_path: Path,
    additional_files: dict[str, bytes] | None = None,
) -> tuple[Path, Path, Path, Path, Path, dict[str, object]]:
    native_member = "sentencepiece/_sentencepiece.cpython-313-darwin.so"
    wheel_files = {native_member: MACHO_FIXTURE}
    wheel_files.update(additional_files or {})
    wheel = make_wheel(
        tmp_path,
        "sentencepiece",
        "0.2.2",
        license_expression="Apache-2.0",
        extra=wheel_files,
    )
    bundle = make_bundle(tmp_path, wheel)
    notices_dir, notices = make_notices(tmp_path)
    verifier = tmp_path / "slsa-verifier"
    verifier.write_text("#!/bin/sh\nexit 0\n")
    verifier.chmod(0o755)
    otool = tmp_path / "otool"
    otool.write_text(
        "#!/bin/sh\n"
        'echo "$2:"\n'
        "echo '  /usr/lib/libc++.1.dylib (compatibility version 1.0.0)'\n"
        "echo '  /usr/lib/libSystem.B.dylib (compatibility version 1.0.0)'\n"
    )
    otool.chmod(0o755)
    policy = sentencepiece_policy(
        wheel,
        slsa_bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        source_repository="github.com/google/sentencepiece",
        source_tag="v0.2.2",
        source_commit="e0cce7d37b065b5140349dbe12c6bcf6192fdd78",
        source_workflow=".github/workflows/wheel.yml",
        notices=notices,
        slsa_verifier={
            "sha256": hashlib.sha256(verifier.read_bytes()).hexdigest(),
        },
        native_members=[native_member],
        allowed_native_dependencies=[
            "/usr/lib/libc++.1.dylib",
            "/usr/lib/libSystem.B.dylib",
        ],
    )
    return wheel, bundle, notices_dir, verifier, otool, policy


def test_sentencepiece_release_rejects_wheel_hash_drift(tmp_path: Path) -> None:
    wheel = make_wheel(
        tmp_path,
        "sentencepiece",
        "0.2.2",
        license_expression="Apache-2.0",
    )
    policy = sentencepiece_policy(wheel, sha256="0" * 64)
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="wheel SHA256 mismatch"):
        module.verify_sentencepiece_release(
            wheel,
            tmp_path / "multiple.intoto.jsonl",
            tmp_path / "third-party",
            tmp_path / "slsa-verifier",
            {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
            policy,
        )


def test_sentencepiece_release_rejects_bundle_hash_drift(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "sentencepiece", "0.2.2")
    bundle = make_bundle(tmp_path, wheel)
    policy = sentencepiece_policy(wheel, slsa_bundle_sha256="0" * 64)
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="SLSA bundle SHA256 mismatch"):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            tmp_path / "third-party",
            tmp_path / "slsa-verifier",
            {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
            policy,
        )


@pytest.mark.parametrize(
    ("bundle_overrides", "message"),
    [
        ({"tag": "v9.9.9"}, "source tag mismatch"),
        ({"commit": "f" * 40}, "source commit mismatch"),
        ({"workflow": ".github/workflows/other.yml"}, "source workflow mismatch"),
    ],
)
def test_sentencepiece_release_rejects_wrong_bundle_source(
    tmp_path: Path, bundle_overrides: dict[str, str], message: str
) -> None:
    wheel = make_wheel(tmp_path, "sentencepiece", "0.2.2")
    bundle = make_bundle(tmp_path, wheel, **bundle_overrides)
    policy = sentencepiece_policy(
        wheel,
        slsa_bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        source_repository="github.com/google/sentencepiece",
        source_tag="v0.2.2",
        source_commit="e0cce7d37b065b5140349dbe12c6bcf6192fdd78",
        source_workflow=".github/workflows/wheel.yml",
    )
    module = load_module()

    with pytest.raises(module.WheelhouseError, match=message):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            tmp_path / "third-party",
            tmp_path / "slsa-verifier",
            {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
            policy,
        )


def test_sentencepiece_release_rejects_subject_with_same_basename(
    tmp_path: Path,
) -> None:
    wheel = make_wheel(tmp_path, "sentencepiece", "0.2.2")
    bundle = make_bundle(tmp_path, wheel, subject_name=f"attacker/path/{wheel.name}")
    policy = sentencepiece_policy(
        wheel,
        slsa_bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        slsa_subject=f"python/wheelhouse/{wheel.name}",
        source_repository="github.com/google/sentencepiece",
        source_tag="v0.2.2",
        source_commit="e0cce7d37b065b5140349dbe12c6bcf6192fdd78",
        source_workflow=".github/workflows/wheel.yml",
    )
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="missing the exact wheel subject"):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            tmp_path / "third-party",
            tmp_path / "slsa-verifier",
            {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
            policy,
        )


def test_sentencepiece_release_rejects_missing_notice(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "sentencepiece", "0.2.2")
    bundle = make_bundle(tmp_path, wheel)
    policy = sentencepiece_policy(
        wheel,
        slsa_bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        source_repository="github.com/google/sentencepiece",
        source_tag="v0.2.2",
        source_commit="e0cce7d37b065b5140349dbe12c6bcf6192fdd78",
        source_workflow=".github/workflows/wheel.yml",
        notices=[
            {
                "component": component,
                "filename": f"{component.lower()}-LICENSE",
                "sha256": "0" * 64,
            }
            for component in (
                "SentencePiece",
                "Abseil",
                "protobuf-lite",
                "darts-clone",
                "esaxx",
                "pybind11",
            )
        ],
    )
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="missing notice"):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            tmp_path / "third-party",
            tmp_path / "slsa-verifier",
            {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
            policy,
        )


def test_sentencepiece_release_rejects_failed_slsa_verifier(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "sentencepiece", "0.2.2")
    bundle = make_bundle(tmp_path, wheel)
    notices_dir, notices = make_notices(tmp_path)
    verifier = tmp_path / "slsa-verifier"
    verifier.write_text("#!/bin/sh\necho signature-invalid >&2\nexit 7\n")
    verifier.chmod(0o755)
    policy = sentencepiece_policy(
        wheel,
        slsa_bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        source_repository="github.com/google/sentencepiece",
        source_tag="v0.2.2",
        source_commit="e0cce7d37b065b5140349dbe12c6bcf6192fdd78",
        source_workflow=".github/workflows/wheel.yml",
        notices=notices,
        slsa_verifier={
            "sha256": hashlib.sha256(verifier.read_bytes()).hexdigest(),
        },
    )
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="signature-invalid"):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            notices_dir,
            verifier,
            {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
            policy,
        )


@pytest.mark.parametrize(
    "release_metadata",
    [
        {"tag_name": "v0.2.2", "draft": False, "prerelease": True},
        {"tag_name": "v0.2.2", "draft": True, "prerelease": False},
    ],
)
def test_formal_sentencepiece_release_rejects_unpublished_status(
    tmp_path: Path, release_metadata: dict[str, object]
) -> None:
    wheel, bundle, notices_dir, verifier, _, policy = make_release_inputs(tmp_path)
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="formal release is not published"):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            notices_dir,
            verifier,
            release_metadata,
            policy,
            formal_release=True,
        )


def test_formal_sentencepiece_release_accepts_published_release(
    tmp_path: Path,
) -> None:
    wheel, bundle, notices_dir, verifier, otool, policy = make_release_inputs(tmp_path)
    module = load_module()

    record = module.verify_sentencepiece_release(
        wheel,
        bundle,
        notices_dir,
        verifier,
        {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
        policy,
        formal_release=True,
        otool_path=otool,
    )

    assert record.name == "sentencepiece"
    assert record.version == "0.2.2"


def test_sentencepiece_release_rejects_unexpected_native_member(
    tmp_path: Path,
) -> None:
    wheel, bundle, notices_dir, verifier, otool, policy = make_release_inputs(tmp_path)
    policy["sentencepiece_release"]["native_members"] = []
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="native members mismatch"):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            notices_dir,
            verifier,
            {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
            policy,
            otool_path=otool,
        )


def test_sentencepiece_release_detects_macho_with_bundle_suffix(
    tmp_path: Path,
) -> None:
    wheel, bundle, notices_dir, verifier, otool, policy = make_release_inputs(
        tmp_path, {"sentencepiece/plugin.bundle": MACHO_FIXTURE}
    )
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="native members mismatch"):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            notices_dir,
            verifier,
            {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
            policy,
            otool_path=otool,
        )


def test_sentencepiece_notice_requirements_come_from_policy(tmp_path: Path) -> None:
    wheel, bundle, notices_dir, verifier, otool, policy = make_release_inputs(tmp_path)
    custom_notice = notices_dir / "custom-LICENSE"
    custom_notice.write_text("custom license", encoding="utf-8")
    release = policy["sentencepiece_release"]
    release["required_notice_components"] = ["custom"]
    release["notices"] = [
        {
            "component": "custom",
            "filename": custom_notice.name,
            "sha256": hashlib.sha256(custom_notice.read_bytes()).hexdigest(),
        }
    ]
    module = load_module()

    record = module.verify_sentencepiece_release(
        wheel,
        bundle,
        notices_dir,
        verifier,
        {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
        policy,
        otool_path=otool,
    )

    assert record.version == "0.2.2"


def test_sentencepiece_release_rejects_notice_hash_drift(tmp_path: Path) -> None:
    wheel, bundle, notices_dir, verifier, otool, policy = make_release_inputs(tmp_path)
    notice = notices_dir / "sentencepiece-LICENSE"
    notice.write_text("changed", encoding="utf-8")
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="notice SHA256 mismatch"):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            notices_dir,
            verifier,
            {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
            policy,
            otool_path=otool,
        )


def test_rc_mode_allows_draft_but_runs_remaining_gates(tmp_path: Path) -> None:
    wheel, bundle, notices_dir, verifier, otool, policy = make_release_inputs(tmp_path)
    (notices_dir / "sentencepiece-LICENSE").unlink()
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="missing notice"):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            notices_dir,
            verifier,
            {"tag_name": "v0.2.2", "draft": True, "prerelease": False},
            policy,
            otool_path=otool,
        )


@pytest.mark.parametrize(
    ("field", "value", "error_path"),
    [
        ("subject", [1], "statement.subject\\[0\\]"),
        (
            "configSource",
            "invalid",
            "statement.predicate.invocation.configSource",
        ),
    ],
)
def test_sentencepiece_release_rejects_malformed_slsa_objects(
    tmp_path: Path, field: str, value: object, error_path: str
) -> None:
    wheel, bundle, notices_dir, verifier, otool, policy = make_release_inputs(tmp_path)
    rewrite_bundle(bundle, field, value)
    policy["sentencepiece_release"]["slsa_bundle_sha256"] = hashlib.sha256(
        bundle.read_bytes()
    ).hexdigest()
    module = load_module()

    with pytest.raises(module.WheelhouseError, match=error_path):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            notices_dir,
            verifier,
            {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
            policy,
            otool_path=otool,
        )


def test_sentencepiece_release_rejects_non_string_notice_component(
    tmp_path: Path,
) -> None:
    wheel, bundle, notices_dir, verifier, otool, policy = make_release_inputs(tmp_path)
    policy["sentencepiece_release"]["notices"][0]["component"] = []
    module = load_module()

    with pytest.raises(
        module.WheelhouseError,
        match=r"sentencepiece_release.notices\[0\].component",
    ):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            notices_dir,
            verifier,
            {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
            policy,
            otool_path=otool,
        )


def test_slsa_verifier_timeout_is_bounded(tmp_path: Path, monkeypatch) -> None:
    wheel, bundle, notices_dir, verifier, otool, policy = make_release_inputs(tmp_path)
    module = load_module()

    def timeout(command, **kwargs):
        assert kwargs["timeout"] == module.SLSA_VERIFIER_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(module.subprocess, "run", timeout)
    with pytest.raises(module.WheelhouseError, match=r"slsa-verifier .* timed out"):
        module.verify_sentencepiece_release(
            wheel,
            bundle,
            notices_dir,
            verifier,
            {"tag_name": "v0.2.2", "draft": False, "prerelease": False},
            policy,
            otool_path=otool,
        )


def test_otool_oserror_is_bounded_and_reported(tmp_path: Path, monkeypatch) -> None:
    wheel, _, _, _, otool, policy = make_release_inputs(tmp_path)
    module = load_module()

    def unavailable(command, **kwargs):
        assert kwargs["timeout"] == module.OTOOL_TIMEOUT_SECONDS
        raise OSError("not executable")

    monkeypatch.setattr(module.subprocess, "run", unavailable)
    release = policy["sentencepiece_release"]
    with pytest.raises(
        module.WheelhouseError,
        match=rf"otool {otool} failed: not executable",
    ):
        module.scan_native_members(wheel, release, otool)


def test_json_object_reports_path_and_parse_position(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{", encoding="utf-8")
    module = load_module()

    with pytest.raises(
        module.WheelhouseError,
        match=rf"{re.escape(str(path))}.*line 1 column 2",
    ):
        module._json_object(path)


def test_json_object_reports_missing_file_path(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    module = load_module()

    with pytest.raises(
        module.WheelhouseError,
        match=rf"{re.escape(str(path))}.*No such file",
    ):
        module._json_object(path)


def test_verify_sentencepiece_cli_accepts_verified_release(tmp_path: Path) -> None:
    wheel, bundle, notices_dir, verifier, otool, policy = make_release_inputs(tmp_path)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    release_path = tmp_path / "release.json"
    release_path.write_text(
        json.dumps({"tag_name": "v0.2.2", "draft": False, "prerelease": False}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "verify-sentencepiece",
            "--wheel",
            str(wheel),
            "--bundle",
            str(bundle),
            "--notices",
            str(notices_dir),
            "--verifier",
            str(verifier),
            "--release-metadata",
            str(release_path),
            "--policy",
            str(policy_path),
            "--otool",
            str(otool),
            "--formal-release",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["version"] == "0.2.2"


def test_old_sentencepiece_is_not_approved_by_repository_policy() -> None:
    policy = json.loads(
        (ROOT / "packaging/homebrew/license-policy.json").read_text(encoding="utf-8")
    )

    assert OLD_SENTENCEPIECE_SHA256 not in policy["wheel_approvals"]


def _wheelhouse_fixture(tmp_path: Path) -> tuple[Path, Path, str, dict[str, Path]]:
    demo = make_wheel(tmp_path, "demo", "1.2.3")
    project = make_wheel(tmp_path, "subtap", "0.1.0rc2")
    lock = tmp_path / "uv.lock"
    lock.write_text(
        "version = 1\n"
        "revision = 3\n"
        'requires-python = ">=3.10"\n\n'
        "[[package]]\n"
        'name = "demo"\n'
        'version = "1.2.3"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        "wheels = [\n"
        f'  {{ url = "https://example.test/{demo.name}", '
        f'hash = "sha256:{hashlib.sha256(demo.read_bytes()).hexdigest()}", '
        f"size = {demo.stat().st_size} }},\n"
        "]\n",
        encoding="utf-8",
    )
    export_text = (
        "demo==1.2.3 \\\n"
        f"  --hash=sha256:{hashlib.sha256(demo.read_bytes()).hexdigest()}\n"
    )
    return lock, project, export_text, {f"https://example.test/{demo.name}": demo}


def test_build_wheelhouse_writes_offline_outputs(tmp_path: Path) -> None:
    lock, project, export_text, downloads = _wheelhouse_fixture(tmp_path)
    output = tmp_path / "output"
    module = load_module()

    archive = module.build_wheelhouse(
        output,
        lock_path=lock,
        policy={"allowed_licenses": ["MIT"], "wheel_approvals": {}},
        export_text=export_text,
        download=lambda url, target: shutil.copyfile(downloads[url], target),
        build_project=lambda directory: shutil.copyfile(
            project, directory / project.name
        ),
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert {item["name"] for item in manifest["packages"]} == {"demo", "subtap"}
    assert manifest["external_packages"] == [
        {"name": "numpy", "requirement": ">=1.26.4", "formula": "numpy"},
        {"name": "scipy", "requirement": ">=1.10.0", "formula": "scipy"},
    ]
    # Verify wheelhouse_sha256 is embedded for cross-validation by the renderer.
    sha256_hex = manifest["wheelhouse_sha256"]
    assert len(sha256_hex) == 64
    assert sha256_hex == hashlib.sha256(archive.read_bytes()).hexdigest()
    requirements = (output / "requirements.txt").read_text(encoding="utf-8")
    assert "demo==1.2.3 --hash=sha256:" in requirements
    assert "subtap==0.1.0rc2 --hash=sha256:" in requirements
    assert "numpy" not in requirements and "scipy" not in requirements
    assert "http" not in requirements
    assert archive.name == "subtap-0.1.0rc2-py313-macos-arm64-wheelhouse.tar.gz"


def test_build_wheelhouse_rejects_unknown_sdist(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    lock.write_text(
        'version = 1\nrevision = 3\nrequires-python = ">=3.10"\n\n'
        '[[package]]\nname = "source-only"\nversion = "1.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        'sdist = { url = "https://example.test/source-only.tar.gz", '
        'hash = "sha256:0000000000000000000000000000000000000000000000000000000000000000" }\n',
        encoding="utf-8",
    )
    module = load_module()

    with pytest.raises(
        module.WheelhouseError, match="source distribution is forbidden"
    ):
        module.build_wheelhouse(
            tmp_path / "output",
            lock_path=lock,
            policy={"allowed_licenses": ["MIT"], "wheel_approvals": {}},
            export_text="source-only==1.0\n",
            download=lambda url, target: None,
            build_project=lambda directory: None,
        )


def test_build_wheelhouse_rejects_unlocked_jieba_sdist(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    lock.write_text(
        'version = 1\nrevision = 3\nrequires-python = ">=3.10"\n\n'
        '[[package]]\nname = "jieba"\nversion = "0.42.1"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        'sdist = { url = "https://example.test/jieba-0.42.1.tar.gz", '
        'hash = "sha256:0000000000000000000000000000000000000000000000000000000000000000" }\n',
        encoding="utf-8",
    )
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="jieba sdist SHA256 mismatch"):
        module.build_wheelhouse(
            tmp_path / "output",
            lock_path=lock,
            policy={"allowed_licenses": ["MIT"], "wheel_approvals": {}},
            export_text="jieba==0.42.1\n",
            download=lambda url, target: None,
            build_project=lambda directory: None,
        )


def test_build_wheelhouse_enforces_size_limit(tmp_path: Path) -> None:
    lock, project, export_text, downloads = _wheelhouse_fixture(tmp_path)
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="300 bytes"):
        module.build_wheelhouse(
            tmp_path / "output",
            lock_path=lock,
            policy={"allowed_licenses": ["MIT"], "wheel_approvals": {}},
            export_text=export_text,
            download=lambda url, target: shutil.copyfile(downloads[url], target),
            build_project=lambda directory: shutil.copyfile(
                project, directory / project.name
            ),
            max_bytes=300,
        )


def test_build_wheelhouse_archive_is_deterministic(tmp_path: Path) -> None:
    lock, project, export_text, downloads = _wheelhouse_fixture(tmp_path)
    module = load_module()

    archives = []
    for name in ("one", "two"):
        archives.append(
            module.build_wheelhouse(
                tmp_path / name,
                lock_path=lock,
                policy={"allowed_licenses": ["MIT"], "wheel_approvals": {}},
                export_text=export_text,
                download=lambda url, target: shutil.copyfile(downloads[url], target),
                build_project=lambda directory: shutil.copyfile(
                    project, directory / project.name
                ),
            )
        )

    assert (
        hashlib.sha256(archives[0].read_bytes()).digest()
        == hashlib.sha256(archives[1].read_bytes()).digest()
    )


def test_build_wheelhouse_copies_wheel_license_bytes(tmp_path: Path) -> None:
    demo = make_wheel(
        tmp_path,
        "demo",
        "1.2.3",
        declared_license_files=("LICENSE",),
        license_files={"demo-1.2.3.dist-info/licenses/LICENSE": "exact license\n"},
    )
    project = make_wheel(tmp_path, "subtap", "0.1.0rc2")
    digest = hashlib.sha256(demo.read_bytes()).hexdigest()
    lock = tmp_path / "uv.lock"
    lock.write_text(
        'version = 1\nrevision = 3\nrequires-python = ">=3.10"\n\n'
        '[[package]]\nname = "demo"\nversion = "1.2.3"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        f'wheels = [{{ url = "https://example.test/{demo.name}", '
        f'hash = "sha256:{digest}" }}]\n',
        encoding="utf-8",
    )
    output = tmp_path / "output"
    module = load_module()

    module.build_wheelhouse(
        output,
        lock_path=lock,
        policy={"allowed_licenses": ["MIT"], "wheel_approvals": {}},
        export_text=f"demo==1.2.3 --hash=sha256:{digest}\n",
        download=lambda url, target: shutil.copyfile(demo, target),
        build_project=lambda directory: shutil.copyfile(
            project, directory / project.name
        ),
    )

    copied = output / "THIRD_PARTY_LICENSES/demo/LICENSE"
    assert copied.read_bytes() == b"exact license\n"
    licenses = json.loads((output / "licenses.json").read_text(encoding="utf-8"))
    assert licenses == [
        {
            "component": "demo",
            "path": "THIRD_PARTY_LICENSES/demo/LICENSE",
            "sha256": hashlib.sha256(b"exact license\n").hexdigest(),
            "source_member": "demo-1.2.3.dist-info/licenses/LICENSE",
        }
    ]


def test_sentencepiece_policy_pins_verified_release_inputs() -> None:
    policy = json.loads(
        (ROOT / "packaging/homebrew/license-policy.json").read_text(encoding="utf-8")
    )["sentencepiece_release"]

    assert policy["filename"] == (
        "sentencepiece-0.2.2-cp313-cp313-macosx_11_0_arm64.whl"
    )
    assert policy["sha256"] == (
        "201a8e0f55501a76e08dbf2c54bc45f4642b379271e89c667d517bfbc2191f2a"
    )
    assert policy["slsa_bundle_sha256"] == (
        "cc6f6011e50a3ed6099e0cdfe59ae517c16d2b40c74de76eebaa8e8426f0486b"
    )
    assert policy["source_commit"] == ("e0cce7d37b065b5140349dbe12c6bcf6192fdd78")
    expected_components = {
        "SentencePiece",
        "Abseil",
        "protobuf-lite",
        "darts-clone",
        "esaxx",
        "pybind11",
    }
    assert set(policy["required_notice_components"]) == expected_components
    assert {notice["component"] for notice in policy["notices"]} == expected_components
    for notice in policy["notices"]:
        path = ROOT / "packaging/homebrew/third-party" / notice["filename"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == notice["sha256"]


def test_unknown_license_requires_exact_approved_hash(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "sentencepiece", "0.2.1", license_expression=None)
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="unapproved wheel hash"):
        module.inspect_wheel(wheel, {"allowed_licenses": [], "wheel_approvals": {}})


def test_changed_approved_hash_is_rejected(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, license_expression=None)
    policy = approved_policy(wheel)
    with wheel.open("ab") as file:
        file.write(b"changed")
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="unapproved wheel hash"):
        module.inspect_wheel(wheel, policy)


def test_unknown_license_cannot_be_self_approved(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, license_expression=None)
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="unapproved wheel hash"):
        module.inspect_wheel(wheel, approved_policy(wheel))


def test_rejects_forbidden_legacy_license_even_with_mit_expression(
    tmp_path: Path,
) -> None:
    wheel = make_wheel(
        tmp_path,
        license_expression="MIT",
        legacy_license="GNU General Public License",
    )
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="forbidden license"):
        module.inspect_wheel(wheel, approved_policy(wheel))


@pytest.mark.parametrize(
    "filename",
    [
        "example-1.0.dist-info/licenses/COPYING",
        "example-1.0.dist-info/NOTICE",
        "example/NOTICE",
    ],
)
def test_rejects_lgpl_in_license_or_notice_files(tmp_path: Path, filename: str) -> None:
    wheel = make_wheel(
        tmp_path,
        license_expression=None,
        license_files={filename: "GNU Lesser General Public License"},
    )
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="forbidden license"):
        module.inspect_wheel(wheel, approved_policy(wheel))


def test_allows_psf_license_that_mentions_gpl_compatibility(tmp_path: Path) -> None:
    wheel = make_wheel(
        tmp_path,
        license_expression="PSF-2.0",
        license_files={
            "example-1.0.dist-info/licenses/LICENSE": (
                "PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2\n"
                "This license remains compatible with the GNU General Public License.\n"
            )
        },
    )
    module = load_module()

    record = module.inspect_wheel(
        wheel,
        {"allowed_licenses": ["PSF-2.0"], "wheel_approvals": {}},
    )

    assert record.license == "PSF-2.0"


def test_scans_every_dist_info_license_filename(tmp_path: Path) -> None:
    filename = "example-1.0.dist-info/licenses/COPYRIGHT.txt"
    wheel = make_wheel(
        tmp_path,
        license_expression="MIT",
        declared_license_files=("COPYRIGHT.txt",),
        license_files={filename: "GNU General Public License"},
    )
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="forbidden license"):
        module.inspect_wheel(wheel, approved_policy(wheel))


def test_rejects_forbidden_bundled_library(tmp_path: Path) -> None:
    wheel = make_wheel(
        tmp_path,
        extra={"example/.dylibs/libgfortran.5.dylib": b"binary"},
    )
    module = load_module()

    with pytest.raises(module.WheelhouseError, match="libgfortran"):
        module.inspect_wheel(wheel, approved_policy(wheel, "MIT"))


def test_accepts_allowlisted_license_without_hash_override(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, license_expression="MIT")
    module = load_module()

    record = module.inspect_wheel(
        wheel,
        {
            "allowed_licenses": ["MIT", "Apache-2.0", "BSD-3-Clause"],
            "wheel_approvals": {},
        },
    )

    assert record.name == "example"
    assert record.version == "1.0"
    assert record.license == "MIT"


def test_accepts_standard_mit_license_classifier(tmp_path: Path) -> None:
    wheel = make_wheel(
        tmp_path,
        license_expression=None,
        license_classifiers=("License :: OSI Approved :: MIT License",),
    )
    module = load_module()

    record = module.inspect_wheel(
        wheel,
        {"allowed_licenses": ["MIT"], "wheel_approvals": {}},
    )

    assert record.license == "MIT"


def test_normalizes_legacy_apache_license_name(tmp_path: Path) -> None:
    wheel = make_wheel(
        tmp_path,
        license_expression=None,
        legacy_license="Apache 2.0",
    )
    module = load_module()

    record = module.inspect_wheel(
        wheel,
        {"allowed_licenses": ["Apache-2.0"], "wheel_approvals": {}},
    )

    assert record.license == "Apache-2.0"


def test_repository_policy_allows_permissive_mit_zero() -> None:
    policy = json.loads(
        (ROOT / "packaging/homebrew/license-policy.json").read_text(encoding="utf-8")
    )

    assert "MIT-0" in policy["allowed_licenses"]
