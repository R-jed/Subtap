#!/usr/bin/env python3
"""Fail-fast checks shared by the proposed Homebrew wheelhouse builder."""

from __future__ import annotations

from email import message_from_bytes
import hashlib
from pathlib import Path
from typing import NamedTuple
from zipfile import BadZipFile, ZipFile

FORBIDDEN_MEMBERS = ("libgfortran", "libgcc", "libquadmath", "openblas")
FORBIDDEN_LICENSE_MARKERS = (
    "GNU AFFERO GENERAL PUBLIC LICENSE",
    "GNU GENERAL PUBLIC LICENSE",
    "GNU LESSER GENERAL PUBLIC LICENSE",
    "AGPL-",
    "GPL-",
    "LGPL-",
)
LICENSE_FILE_MARKERS = ("license", "copying", "notice")


class WheelhouseError(ValueError):
    """A wheel violates a release gate."""


class WheelRecord(NamedTuple):
    name: str
    version: str
    sha256: str
    license: str
    filename: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_metadata(names: list[str]) -> str:
    matches = [name for name in names if name.endswith(".dist-info/METADATA")]
    if len(matches) != 1:
        raise WheelhouseError(f"expected one METADATA file, found {len(matches)}")
    return matches[0]


def _reject_forbidden_license(text: str, source: str) -> None:
    upper = text.upper()
    marker = next((item for item in FORBIDDEN_LICENSE_MARKERS if item in upper), None)
    if marker:
        raise WheelhouseError(f"forbidden license in {source}: {marker}")


def inspect_wheel(path: Path, policy: dict[str, object]) -> WheelRecord:
    """Inspect one wheel; unknown licenses are rejected until provenance exists."""

    digest = sha256_file(path)
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            forbidden = next(
                (
                    name
                    for name in names
                    if any(marker in name.lower() for marker in FORBIDDEN_MEMBERS)
                ),
                None,
            )
            if forbidden:
                raise WheelhouseError(f"forbidden bundled component: {forbidden}")

            metadata = message_from_bytes(archive.read(_require_metadata(names)))
            declared_licenses = []
            for field in ("License-Expression", "License"):
                for value in metadata.get_all(field, []):
                    value = value.strip()
                    _reject_forbidden_license(value, field)
                    declared_licenses.append(value)
            if len(declared_licenses) > 1:
                raise WheelhouseError("multiple license declarations in METADATA")
            license_id = declared_licenses[0] if declared_licenses else "UNKNOWN"

            license_members = {
                name
                for name in names
                if ".dist-info/licenses/" in name.lower()
                or any(
                    marker in Path(name).name.lower() for marker in LICENSE_FILE_MARKERS
                )
            }
            for declared in metadata.get_all("License-File", []):
                matches = {
                    name
                    for name in names
                    if name == declared or name.endswith(f"/{declared}")
                }
                if not matches:
                    raise WheelhouseError(f"declared License-File missing: {declared}")
                license_members.update(matches)
            for name in license_members:
                content = archive.read(name).decode("utf-8", errors="replace")
                _reject_forbidden_license(content, name)
    except BadZipFile as exc:
        raise WheelhouseError(f"invalid wheel archive: {path.name}") from exc

    approvals = policy.get("wheel_approvals", {})
    if not isinstance(approvals, dict):
        raise WheelhouseError("wheel_approvals must be an object")
    if license_id == "UNKNOWN":
        raise WheelhouseError(f"unapproved wheel hash: {digest}")

    allowed = policy.get("allowed_licenses", [])
    if not isinstance(allowed, list) or license_id not in allowed:
        raise WheelhouseError(f"license is not allowlisted: {license_id}")

    return WheelRecord(
        name=str(metadata["Name"]),
        version=str(metadata["Version"]),
        sha256=digest,
        license=license_id,
        filename=path.name,
    )
