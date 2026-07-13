"""Fail-fast gates for Homebrew wheelhouse inputs."""

from __future__ import annotations

from email.message import Message
import hashlib
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/homebrew_wheelhouse.py"
SENTENCEPIECE_SHA256 = (
    "097f3394e99456e9e4efba1737c3749d7e23563dd1588ce71a3d007f25475fff"
)


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


def test_sentencepiece_is_not_approved_by_repository_policy() -> None:
    policy = json.loads(
        (ROOT / "packaging/homebrew/license-policy.json").read_text(encoding="utf-8")
    )

    assert SENTENCEPIECE_SHA256 not in policy["wheel_approvals"]


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
