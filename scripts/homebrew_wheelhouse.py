#!/usr/bin/env python3
"""Fail-fast checks shared by the proposed Homebrew wheelhouse builder."""

from __future__ import annotations

import argparse
import base64
from email import message_from_bytes
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, NamedTuple
from zipfile import BadZipFile, ZipFile

FORBIDDEN_MEMBERS = (
    "libgfortran",
    "libgcc",
    "libquadmath",
    "openblas",
    "tcmalloc",
    "libatomic",
)
FORBIDDEN_LICENSE_MARKERS = (
    "GNU AFFERO GENERAL PUBLIC LICENSE",
    "GNU GENERAL PUBLIC LICENSE",
    "GNU LESSER GENERAL PUBLIC LICENSE",
    "AGPL-",
    "GPL-",
    "LGPL-",
)
LICENSE_FILE_MARKERS = ("license", "copying", "notice")
MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf",
    b"\xbf\xba\xfe\xca",
}
AR_MAGIC = b"!<arch>\n"


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


def _matching_slsa_statement(
    bundle_path: Path, expected_subject: str, wheel_sha256: str
) -> dict[str, Any]:
    for line in bundle_path.read_text(encoding="utf-8").splitlines():
        try:
            bundle = json.loads(line)
            envelope = bundle["dsseEnvelope"]
            statement = json.loads(base64.b64decode(envelope["payload"], validate=True))
            subjects = statement["subject"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise WheelhouseError("invalid SLSA bundle") from exc
        matches = [
            subject for subject in subjects if subject.get("name") == expected_subject
        ]
        if matches:
            if len(matches) != 1:
                raise WheelhouseError("SLSA bundle has duplicate wheel subjects")
            if matches[0].get("digest", {}).get("sha256") != wheel_sha256:
                raise WheelhouseError("SLSA subject SHA256 mismatch")
            return statement
    raise WheelhouseError("SLSA bundle is missing the exact wheel subject")


def _verify_notices(notices_dir: Path, release: dict[str, object]) -> None:
    required = release.get("required_notice_components")
    if not isinstance(required, list) or not all(
        isinstance(component, str) for component in required
    ):
        raise WheelhouseError("required_notice_components must be strings")
    notices = release.get("notices")
    if not isinstance(notices, list) or not all(
        isinstance(notice, dict) for notice in notices
    ):
        raise WheelhouseError("notices must be an array of objects")
    components = [notice.get("component") for notice in notices]
    if (
        len(required) != len(set(required))
        or len(components) != len(required)
        or set(components) != set(required)
    ):
        raise WheelhouseError("notice components do not match policy requirements")
    for notice in notices:
        filename = notice.get("filename")
        if not isinstance(filename, str):
            raise WheelhouseError("notice filename must be a string")
        path = notices_dir / filename
        if not path.is_file():
            raise WheelhouseError(f"missing notice: {filename}")
        actual_sha = sha256_file(path)
        if actual_sha != notice.get("sha256"):
            raise WheelhouseError(f"notice SHA256 mismatch: {filename}")


def _run_slsa_verifier(
    verifier_path: Path,
    wheel_path: Path,
    bundle_path: Path,
    release: dict[str, object],
) -> None:
    verifier = release.get("slsa_verifier")
    if not isinstance(verifier, dict):
        raise WheelhouseError("slsa_verifier must be an object")
    if not verifier_path.is_file():
        raise WheelhouseError(f"missing slsa-verifier: {verifier_path}")
    actual_sha = sha256_file(verifier_path)
    if actual_sha != verifier.get("sha256"):
        raise WheelhouseError("slsa-verifier SHA256 mismatch")
    command = [
        str(verifier_path),
        "verify-artifact",
        "--provenance-path",
        str(bundle_path),
        "--source-uri",
        str(release.get("source_repository")),
        "--source-tag",
        str(release.get("source_tag")),
        str(wheel_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown verifier error").strip()
        raise WheelhouseError(f"slsa-verifier failed: {detail}") from exc


def scan_native_members(
    wheel_path: Path, release: dict[str, object], otool_path: Path
) -> None:
    """Require an exact native member and Mach-O dependency set."""

    expected_members = release.get("native_members")
    allowed_dependencies = release.get("allowed_native_dependencies")
    if not isinstance(expected_members, list) or not all(
        isinstance(name, str) for name in expected_members
    ):
        raise WheelhouseError("native_members must be an array of strings")
    if not isinstance(allowed_dependencies, list) or not all(
        isinstance(name, str) for name in allowed_dependencies
    ):
        raise WheelhouseError("allowed_native_dependencies must be an array of strings")
    with ZipFile(wheel_path) as archive:
        native_members = []
        archive_members = set()
        for info in archive.infolist():
            if info.is_dir():
                continue
            with archive.open(info) as member_file:
                header = member_file.read(8)
            if header[:4] in MACHO_MAGICS or header == AR_MAGIC:
                native_members.append(info.filename)
            if header == AR_MAGIC:
                archive_members.add(info.filename)
        native_members.sort()
        if native_members != sorted(expected_members):
            raise WheelhouseError(
                f"native members mismatch: expected {expected_members}, got {native_members}"
            )
        with tempfile.TemporaryDirectory() as directory:
            for member in native_members:
                if member in archive_members:
                    continue
                extracted = Path(directory) / Path(member).name
                extracted.write_bytes(archive.read(member))
                try:
                    result = subprocess.run(
                        [str(otool_path), "-L", str(extracted)],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                except subprocess.CalledProcessError as exc:
                    detail = (exc.stderr or exc.stdout or "unknown otool error").strip()
                    raise WheelhouseError(f"otool failed: {detail}") from exc
                dependencies = sorted(
                    line.strip().split(maxsplit=1)[0]
                    for line in result.stdout.splitlines()[1:]
                    if line.strip()
                )
                forbidden = next(
                    (
                        dependency
                        for dependency in dependencies
                        if any(
                            marker in dependency.lower() for marker in FORBIDDEN_MEMBERS
                        )
                    ),
                    None,
                )
                if forbidden:
                    raise WheelhouseError(f"forbidden native dependency: {forbidden}")
                if dependencies != sorted(allowed_dependencies):
                    raise WheelhouseError(
                        "native dependencies mismatch: "
                        f"expected {allowed_dependencies}, got {dependencies}"
                    )


def verify_sentencepiece_release(
    wheel_path: Path,
    bundle_path: Path,
    notices_dir: Path,
    verifier_path: Path,
    release_metadata: dict[str, object],
    policy: dict[str, object],
    *,
    formal_release: bool = False,
    otool_path: Path = Path("/usr/bin/otool"),
) -> WheelRecord:
    """Verify the exact upstream SentencePiece release inputs."""

    release = policy.get("sentencepiece_release")
    if not isinstance(release, dict):
        raise WheelhouseError("sentencepiece_release must be an object")
    if release_metadata.get("tag_name") != release.get("source_tag"):
        raise WheelhouseError("GitHub release tag mismatch")
    draft = release_metadata.get("draft")
    prerelease = release_metadata.get("prerelease")
    if not isinstance(draft, bool) or not isinstance(prerelease, bool):
        raise WheelhouseError("GitHub release metadata is incomplete")
    if formal_release and (draft or prerelease):
        raise WheelhouseError("formal release is not published")
    if wheel_path.name != release.get("filename"):
        raise WheelhouseError(f"wheel filename mismatch: {wheel_path.name}")
    expected_sha = release.get("sha256")
    actual_sha = sha256_file(wheel_path)
    if actual_sha != expected_sha:
        raise WheelhouseError(
            f"wheel SHA256 mismatch: expected {expected_sha}, got {actual_sha}"
        )
    expected_bundle_sha = release.get("slsa_bundle_sha256")
    actual_bundle_sha = sha256_file(bundle_path)
    if actual_bundle_sha != expected_bundle_sha:
        raise WheelhouseError(
            "SLSA bundle SHA256 mismatch: "
            f"expected {expected_bundle_sha}, got {actual_bundle_sha}"
        )
    expected_subject = release.get("slsa_subject")
    if not isinstance(expected_subject, str):
        raise WheelhouseError("slsa_subject must be a string")
    statement = _matching_slsa_statement(
        bundle_path, expected_subject, str(expected_sha)
    )
    try:
        config_source = statement["predicate"]["invocation"]["configSource"]
    except (KeyError, TypeError) as exc:
        raise WheelhouseError("SLSA bundle is missing configSource") from exc
    repository = release.get("source_repository")
    tag = release.get("source_tag")
    expected_uri = f"git+https://{repository}@refs/tags/{tag}"
    if config_source.get("uri") != expected_uri:
        raise WheelhouseError("SLSA source tag mismatch")
    if config_source.get("digest", {}).get("sha1") != release.get("source_commit"):
        raise WheelhouseError("SLSA source commit mismatch")
    if config_source.get("entryPoint") != release.get("source_workflow"):
        raise WheelhouseError("SLSA source workflow mismatch")
    _verify_notices(notices_dir, release)
    _run_slsa_verifier(verifier_path, wheel_path, bundle_path, release)
    scan_native_members(wheel_path, release, otool_path)
    return inspect_wheel(wheel_path, policy)


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WheelhouseError(f"expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify-sentencepiece")
    verify_parser.add_argument("--wheel", type=Path, required=True)
    verify_parser.add_argument("--bundle", type=Path, required=True)
    verify_parser.add_argument("--notices", type=Path, required=True)
    verify_parser.add_argument("--verifier", type=Path, required=True)
    verify_parser.add_argument("--release-metadata", type=Path, required=True)
    verify_parser.add_argument("--policy", type=Path, required=True)
    verify_parser.add_argument("--otool", type=Path, default=Path("/usr/bin/otool"))
    verify_parser.add_argument("--formal-release", action="store_true")
    args = parser.parse_args()

    if args.command == "verify-sentencepiece":
        record = verify_sentencepiece_release(
            args.wheel,
            args.bundle,
            args.notices,
            args.verifier,
            _json_object(args.release_metadata),
            _json_object(args.policy),
            formal_release=args.formal_release,
            otool_path=args.otool,
        )
        print(json.dumps(record._asdict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
