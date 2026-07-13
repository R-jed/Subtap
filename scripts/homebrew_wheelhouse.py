#!/usr/bin/env python3
"""Fail-fast checks shared by the proposed Homebrew wheelhouse builder."""

from __future__ import annotations

import argparse
import base64
from email import message_from_bytes
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from typing import Any, Callable, NamedTuple
from urllib.parse import urlparse
from zipfile import BadZipFile, ZipFile

import httpx
from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.tags import Tag, compatible_tags, cpython_tags, mac_platforms
from packaging.utils import canonicalize_name, parse_wheel_filename

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
LICENSE_CLASSIFIERS = {
    "License :: OSI Approved :: MIT License": "MIT",
}
LICENSE_ALIASES = {"Apache 2.0": "Apache-2.0"}
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
SLSA_VERIFIER_TIMEOUT_SECONDS = 60
OTOOL_TIMEOUT_SECONDS = 30
MAX_WHEELHOUSE_BYTES = 300 * 1024 * 1024
SOURCE_DATE_EPOCH = 315532800
JIEBA_SDIST_SHA256 = "055ca12f62674fafed09427f176506079bc135638a14e23e25be909131928db2"
EXTERNAL_PACKAGES = [
    {"name": "numpy", "requirement": ">=1.26.4", "formula": "numpy"},
    {"name": "scipy", "requirement": ">=1.10.0", "formula": "scipy"},
]


class WheelhouseError(ValueError):
    """A wheel violates a release gate."""


class WheelRecord(NamedTuple):
    name: str
    version: str
    sha256: str
    license: str
    filename: str


def _require_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WheelhouseError(f"{path} must be an object")
    return value


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
    if source in {"License-Expression", "License"}:
        marker = next(
            (item for item in FORBIDDEN_LICENSE_MARKERS if item in upper), None
        )
    else:
        stripped = upper.lstrip()
        marker = next(
            (
                item
                for item in FORBIDDEN_LICENSE_MARKERS[:3]
                if stripped.startswith(item)
            ),
            None,
        )
        if marker is None:
            spdx = re.search(
                r"SPDX-LICENSE-IDENTIFIER:\s*[^\n]*(?:AGPL|LGPL|GPL)-", upper
            )
            marker = spdx.group(0) if spdx else None
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
            classifier_licenses = {
                LICENSE_CLASSIFIERS[classifier]
                for classifier in metadata.get_all("Classifier", [])
                if classifier in LICENSE_CLASSIFIERS
            }
            if len(classifier_licenses) > 1:
                raise WheelhouseError("multiple license classifiers in METADATA")
            license_id = (
                declared_licenses[0]
                if declared_licenses
                else next(iter(classifier_licenses), "UNKNOWN")
            )
            license_id = LICENSE_ALIASES.get(license_id, license_id)

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
            bundle = _require_object(json.loads(line), "bundle")
            envelope = _require_object(bundle["dsseEnvelope"], "bundle.dsseEnvelope")
            statement = _require_object(
                json.loads(base64.b64decode(envelope["payload"], validate=True)),
                "statement",
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise WheelhouseError("invalid SLSA bundle") from exc
        subjects = statement.get("subject")
        if not isinstance(subjects, list):
            raise WheelhouseError("statement.subject must be an array")
        for index, subject in enumerate(subjects):
            subject = _require_object(subject, f"statement.subject[{index}]")
            _require_object(subject.get("digest"), f"statement.subject[{index}].digest")
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
    for index, notice in enumerate(notices):
        for field in ("component", "filename", "sha256"):
            if not isinstance(notice.get(field), str):
                raise WheelhouseError(
                    f"sentencepiece_release.notices[{index}].{field} must be a string"
                )
    components = [notice["component"] for notice in notices]
    if (
        len(required) != len(set(required))
        or len(components) != len(required)
        or set(components) != set(required)
    ):
        raise WheelhouseError("notice components do not match policy requirements")
    for notice in notices:
        filename = notice["filename"]
        path = notices_dir / filename
        if not path.is_file():
            raise WheelhouseError(f"missing notice: {filename}")
        actual_sha = sha256_file(path)
        if actual_sha != notice.get("sha256"):
            raise WheelhouseError(f"notice SHA256 mismatch: {filename}")


def _config_source(statement: dict[str, Any]) -> dict[str, Any]:
    predicate = _require_object(statement.get("predicate"), "statement.predicate")
    invocation = _require_object(
        predicate.get("invocation"), "statement.predicate.invocation"
    )
    config_source = _require_object(
        invocation.get("configSource"),
        "statement.predicate.invocation.configSource",
    )
    _require_object(
        config_source.get("digest"),
        "statement.predicate.invocation.configSource.digest",
    )
    return config_source


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
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=SLSA_VERIFIER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise WheelhouseError(
            f"slsa-verifier {verifier_path} timed out after "
            f"{SLSA_VERIFIER_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise WheelhouseError(f"slsa-verifier {verifier_path} failed: {exc}") from exc
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
                        timeout=OTOOL_TIMEOUT_SECONDS,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise WheelhouseError(
                        f"otool {otool_path} timed out after {OTOOL_TIMEOUT_SECONDS}s"
                    ) from exc
                except OSError as exc:
                    raise WheelhouseError(f"otool {otool_path} failed: {exc}") from exc
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
    config_source = _config_source(statement)
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


def _exported_requirements(text: str) -> list[Requirement]:
    environment = {key: str(value) for key, value in default_environment().items()}
    environment.update(
        {
            "implementation_name": "cpython",
            "platform_machine": "arm64",
            "platform_system": "Darwin",
            "python_full_version": "3.13.0",
            "python_version": "3.13",
            "sys_platform": "darwin",
        }
    )
    requirements = []
    logical = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        logical += line[:-1].strip() + " " if line.endswith("\\") else line
        if line.endswith("\\"):
            continue
        requirement_text = logical.split(" --hash=", 1)[0].strip()
        logical = ""
        requirement = Requirement(requirement_text)
        if requirement.marker is None or requirement.marker.evaluate(environment):
            requirements.append(requirement)
    if logical:
        raise WheelhouseError("truncated uv export output")
    return requirements


def _supported_tags() -> tuple[Tag, ...]:
    platforms = list(mac_platforms((14, 0), "arm64"))
    return tuple(
        dict.fromkeys(
            [
                *cpython_tags((3, 13), platforms=platforms),
                *compatible_tags((3, 13), "cp313", platforms=platforms),
            ]
        )
    )


def _locked_packages(lock_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    try:
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise WheelhouseError(f"cannot read lockfile {lock_path}: {exc}") from exc
    packages: dict[tuple[str, str], dict[str, Any]] = {}
    for package in lock.get("package", []):
        key = (canonicalize_name(package["name"]), str(package["version"]))
        if key in packages:
            raise WheelhouseError(f"duplicate locked package: {key[0]}=={key[1]}")
        packages[key] = package
    return packages


def _select_locked_wheel(
    package: dict[str, Any], supported: tuple[Tag, ...]
) -> dict[str, Any]:
    ranking = {tag: index for index, tag in enumerate(supported)}
    candidates = []
    for wheel in package.get("wheels", []):
        filename = Path(urlparse(wheel["url"]).path).name
        try:
            _, version, _, tags = parse_wheel_filename(filename)
        except ValueError as exc:
            raise WheelhouseError(f"invalid locked wheel filename: {filename}") from exc
        if str(version) != str(package["version"]):
            raise WheelhouseError(f"locked wheel version mismatch: {filename}")
        rank = min((ranking[tag] for tag in tags if tag in ranking), default=None)
        if rank is not None:
            candidates.append((rank, filename, wheel))
    if not candidates:
        name = canonicalize_name(package["name"])
        if "sdist" in package:
            if name == "jieba" and str(package["version"]) == "0.42.1":
                digest = str(package["sdist"].get("hash", "")).removeprefix("sha256:")
                if digest != JIEBA_SDIST_SHA256:
                    raise WheelhouseError("jieba sdist SHA256 mismatch")
            raise WheelhouseError(
                f"source distribution is forbidden: {name}=={package['version']}"
            )
        raise WheelhouseError(f"no compatible wheel: {name}=={package['version']}")
    candidates.sort(key=lambda item: (item[0], item[1]))
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        raise WheelhouseError(f"ambiguous compatible wheel: {package['name']}")
    return candidates[0][2]


def _download_checked(
    artifact: dict[str, Any], target: Path, download: Callable[[str, Path], object]
) -> str:
    try:
        download(artifact["url"], target)
    except WheelhouseError:
        raise
    except Exception as exc:
        raise WheelhouseError(f"download failed: {artifact['url']}: {exc}") from exc
    expected_sha = str(artifact["hash"]).removeprefix("sha256:")
    actual_sha = sha256_file(target)
    if actual_sha != expected_sha:
        raise WheelhouseError(f"artifact SHA256 mismatch: {target.name}")
    return actual_sha


def _safe_extract_sdist(sdist: Path, directory: Path) -> Path:
    directory.mkdir()
    try:
        with tarfile.open(sdist, "r:gz") as archive:
            archive.extractall(directory, filter="data")
    except (OSError, tarfile.TarError) as exc:
        raise WheelhouseError(f"invalid jieba sdist: {exc}") from exc
    roots = [path for path in directory.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise WheelhouseError(f"expected one jieba source root, found {len(roots)}")
    return roots[0]


def _run_offline_build(
    command: list[str], cwd: Path, environment: dict[str, str]
) -> None:
    sandbox = Path("/usr/bin/sandbox-exec")
    if not sandbox.is_file():
        raise WheelhouseError("sandbox-exec is required for the offline jieba build")
    try:
        subprocess.run(
            [
                str(sandbox),
                "-p",
                "(version 1)(allow default)(deny network*)",
                *command,
            ],
            cwd=cwd,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or getattr(exc, "stdout", "") or str(exc)
        raise WheelhouseError(f"offline jieba build failed: {detail.strip()}") from exc


def _build_jieba(
    package: dict[str, Any],
    locked: dict[tuple[str, str], dict[str, Any]],
    supported: tuple[Tag, ...],
    wheels_dir: Path,
    download: Callable[[str, Path], object],
) -> tuple[Path, dict[str, object], bytes]:
    sdist = package.get("sdist")
    if not isinstance(sdist, dict):
        raise WheelhouseError("jieba 0.42.1 must use its locked sdist")
    if str(sdist.get("hash", "")).removeprefix("sha256:") != JIEBA_SDIST_SHA256:
        raise WheelhouseError("jieba sdist SHA256 mismatch")
    setuptools = next(
        (candidate for (name, _), candidate in locked.items() if name == "setuptools"),
        None,
    )
    if setuptools is None:
        raise WheelhouseError("setuptools build dependency is missing from uv.lock")
    setuptools_wheel = _select_locked_wheel(setuptools, supported)
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        sdist_path = temp / Path(urlparse(sdist["url"]).path).name
        sdist_sha = _download_checked(sdist, sdist_path, download)
        build_wheel_path = temp / Path(urlparse(setuptools_wheel["url"]).path).name
        build_wheel_sha = _download_checked(
            setuptools_wheel, build_wheel_path, download
        )
        source = _safe_extract_sdist(sdist_path, temp / "source")
        license_path = source / "LICENSE"
        if not license_path.is_file():
            raise WheelhouseError("jieba sdist is missing LICENSE")
        license_content = license_path.read_bytes()
        environment = os.environ.copy()
        environment.update(
            {
                "HOME": str(temp / "home"),
                "PIP_NO_INDEX": "1",
                "SOURCE_DATE_EPOCH": str(SOURCE_DATE_EPOCH),
            }
        )
        virtualenv = temp / "venv"
        _run_offline_build(
            [sys.executable, "-m", "venv", "--without-pip", str(virtualenv)],
            temp,
            environment,
        )
        site_packages = virtualenv / "lib/python3.13/site-packages"
        site_packages.mkdir(parents=True, exist_ok=True)
        with ZipFile(build_wheel_path) as archive:
            archive.extractall(site_packages)
        python = virtualenv / "bin/python"
        requirements_path = temp / "build-requirements.json"
        requirements_script = (
            "import json,pathlib,setuptools.build_meta as backend;"
            "pathlib.Path(__import__('sys').argv[1]).write_text("
            "json.dumps(backend.get_requires_for_build_wheel({})))"
        )
        _run_offline_build(
            [str(python), "-c", requirements_script, str(requirements_path)],
            source,
            environment,
        )
        try:
            dynamic_requirements = json.loads(
                requirements_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise WheelhouseError("cannot read jieba build requirements") from exc
        if dynamic_requirements:
            raise WheelhouseError(
                f"unexpected jieba build requirements: {dynamic_requirements}"
            )
        result_path = temp / "built-wheel.txt"
        build_script = (
            "import pathlib,setuptools.build_meta as backend,sys;"
            "pathlib.Path(sys.argv[2]).write_text(backend.build_wheel(sys.argv[1], {}))"
        )
        built_dir = temp / "built"
        built_dir.mkdir()
        _run_offline_build(
            [str(python), "-c", build_script, str(built_dir), str(result_path)],
            source,
            environment,
        )
        built_name = result_path.read_text(encoding="utf-8").strip()
        built = built_dir / built_name
        if not built.is_file():
            raise WheelhouseError("jieba build produced no wheel")
        destination = wheels_dir / built.name
        shutil.copyfile(built, destination)

    provenance = {
        "source": {"url": sdist["url"], "sha256": sdist_sha},
        "build_system": [
            {
                "name": "setuptools",
                "version": str(setuptools["version"]),
                "url": setuptools_wheel["url"],
                "sha256": build_wheel_sha,
            }
        ],
        "dynamic_requirements": dynamic_requirements,
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "network": "sandbox-exec deny network*",
    }
    return destination, provenance, license_content


def _download(url: str, target: Path) -> None:
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with target.open("wb") as output:
                for chunk in response.iter_bytes():
                    output.write(chunk)
    except (OSError, httpx.HTTPError) as exc:
        raise WheelhouseError(f"download failed: {url}: {exc}") from exc


def _build_subtap(project_root: Path, directory: Path) -> Path:
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = str(SOURCE_DATE_EPOCH)
    try:
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(directory)],
            cwd=project_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise WheelhouseError(f"subtap wheel build failed: {detail.strip()}") from exc
    wheels = list(directory.glob("subtap-*.whl"))
    if len(wheels) != 1:
        raise WheelhouseError(f"expected one subtap wheel, found {len(wheels)}")
    return wheels[0]


def _write_deterministic_tar(source: Path, archive: Path) -> None:
    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as tar:
                for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
                    relative = path.relative_to(source)
                    info = tar.gettarinfo(str(path), arcname=f"wheelhouse/{relative}")
                    info.mtime = SOURCE_DATE_EPOCH
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mode = 0o755 if path.is_dir() else 0o644
                    if path.is_file():
                        with path.open("rb") as file:
                            tar.addfile(info, file)
                    else:
                        tar.addfile(info)


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _copy_wheel_licenses(
    wheel: Path, component: str, licenses_dir: Path
) -> list[dict[str, str]]:
    records = []
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata = message_from_bytes(archive.read(_require_metadata(names)))
        members = {
            name
            for name in names
            if ".dist-info/licenses/" in name.lower()
            or any(marker in Path(name).name.lower() for marker in LICENSE_FILE_MARKERS)
        }
        for declared in metadata.get_all("License-File", []):
            members.update(
                name
                for name in names
                if name == declared or name.endswith(f"/{declared}")
            )
        component_dir = licenses_dir / canonicalize_name(component)
        for member in sorted(members):
            destination = component_dir / Path(member).name
            if destination.exists():
                raise WheelhouseError(f"duplicate license filename: {destination.name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = archive.read(member)
            destination.write_bytes(content)
            records.append(
                {
                    "component": canonicalize_name(component),
                    "path": destination.relative_to(licenses_dir.parent).as_posix(),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "source_member": member,
                }
            )
    return records


def _copy_sentencepiece_notices(
    project_root: Path,
    policy: dict[str, object],
    licenses_dir: Path,
) -> list[dict[str, str]]:
    release = policy.get("sentencepiece_release")
    if not isinstance(release, dict):
        raise WheelhouseError("sentencepiece_release must be an object")
    _verify_notices(project_root / "packaging/homebrew/third-party", release)
    records = []
    for notice in release["notices"]:
        source = project_root / "packaging/homebrew/third-party" / notice["filename"]
        destination = licenses_dir / "sentencepiece" / notice["filename"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        records.append(
            {
                "component": notice["component"],
                "path": destination.relative_to(licenses_dir.parent).as_posix(),
                "sha256": notice["sha256"],
                "source_member": f"policy:{notice['filename']}",
            }
        )
    return records


def build_wheelhouse(
    output_dir: Path,
    *,
    python_version: str = "3.13",
    platform: str = "macosx_14_0_arm64",
    project_root: Path = Path(__file__).parents[1],
    lock_path: Path | None = None,
    policy: dict[str, object] | None = None,
    export_text: str | None = None,
    download: Callable[[str, Path], object] = _download,
    build_project: Callable[[Path], Path | str] | None = None,
    max_bytes: int = MAX_WHEELHOUSE_BYTES,
) -> Path:
    """Build the locked offline Homebrew wheelhouse for one supported target."""

    if python_version != "3.13" or platform != "macosx_14_0_arm64":
        raise WheelhouseError("only CPython 3.13 / macOS 14 / arm64 is supported")
    if output_dir.exists():
        raise WheelhouseError(f"output already exists: {output_dir}")
    lock_path = lock_path or project_root / "uv.lock"
    policy = policy or _json_object(
        project_root / "packaging/homebrew/license-policy.json"
    )
    if export_text is None:
        try:
            result = subprocess.run(
                [
                    "uv",
                    "export",
                    "--frozen",
                    "--no-dev",
                    "--no-emit-project",
                    "--no-emit-package",
                    "numpy",
                    "--no-emit-package",
                    "scipy",
                    "--python",
                    python_version,
                ],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            raise WheelhouseError(f"uv export failed: {detail.strip()}") from exc
        export_text = result.stdout

    locked = _locked_packages(lock_path)
    requirements = _exported_requirements(export_text)
    names = [canonicalize_name(requirement.name) for requirement in requirements]
    if len(names) != len(set(names)):
        raise WheelhouseError("duplicate package in uv export")
    if {"numpy", "scipy"} & set(names):
        raise WheelhouseError("NumPy/SciPy must be supplied by Homebrew")

    output_dir.mkdir(parents=True)
    wheels_dir = output_dir / "wheels"
    licenses_dir = output_dir / "THIRD_PARTY_LICENSES"
    wheels_dir.mkdir()
    licenses_dir.mkdir()
    records = []
    license_records = []
    supported = _supported_tags()
    for requirement in requirements:
        if len(requirement.specifier) != 1:
            raise WheelhouseError(f"requirement is not exactly pinned: {requirement}")
        version = next(iter(requirement.specifier)).version
        key = (canonicalize_name(requirement.name), version)
        package = locked.get(key)
        if package is None:
            raise WheelhouseError(f"package missing from lock: {key[0]}=={version}")
        if key == ("jieba", "0.42.1"):
            destination, provenance, sdist_license = _build_jieba(
                package,
                locked,
                supported,
                wheels_dir,
                download,
            )
            record = inspect_wheel(destination, policy)
            wheel_licenses = _copy_wheel_licenses(
                destination, record.name, licenses_dir
            )
            license_records.extend(wheel_licenses)
            if not wheel_licenses:
                copied_license = licenses_dir / "jieba/LICENSE"
                copied_license.parent.mkdir(parents=True, exist_ok=True)
                copied_license.write_bytes(sdist_license)
                license_records.append(
                    {
                        "component": "jieba",
                        "path": copied_license.relative_to(
                            licenses_dir.parent
                        ).as_posix(),
                        "sha256": hashlib.sha256(sdist_license).hexdigest(),
                        "source_member": "jieba-0.42.1/LICENSE",
                    }
                )
            records.append(
                {
                    **record._asdict(),
                    "size": destination.stat().st_size,
                    "tags": sorted(
                        str(tag) for tag in parse_wheel_filename(destination.name)[3]
                    ),
                    "url": package["sdist"]["url"],
                    "source_sha256": JIEBA_SDIST_SHA256,
                    "build_provenance": provenance,
                }
            )
            continue
        artifact = _select_locked_wheel(package, supported)
        filename = Path(urlparse(artifact["url"]).path).name
        destination = wheels_dir / filename
        actual_sha = _download_checked(artifact, destination, download)
        record = inspect_wheel(destination, policy)
        if key[0] == "sentencepiece":
            release = policy.get("sentencepiece_release")
            if not isinstance(release, dict):
                raise WheelhouseError("sentencepiece_release must be an object")
            if (
                destination.name != release.get("filename")
                or record.version != "0.2.2"
                or actual_sha != release.get("sha256")
            ):
                raise WheelhouseError("SentencePiece does not match release policy")
            license_records.extend(
                _copy_sentencepiece_notices(project_root, policy, licenses_dir)
            )
        license_records.extend(
            _copy_wheel_licenses(destination, record.name, licenses_dir)
        )
        records.append(
            {
                **record._asdict(),
                "size": destination.stat().st_size,
                "tags": sorted(str(tag) for tag in parse_wheel_filename(filename)[3]),
                "url": artifact["url"],
                "source_sha256": actual_sha,
            }
        )

    builder = build_project or (
        lambda directory: _build_subtap(project_root, directory)
    )
    project_wheel = Path(builder(wheels_dir))
    if not project_wheel.is_file():
        raise WheelhouseError("subtap wheel build produced no wheel")
    project_record = inspect_wheel(project_wheel, policy)
    license_records.extend(
        _copy_wheel_licenses(project_wheel, project_record.name, licenses_dir)
    )
    records.append(
        {
            **project_record._asdict(),
            "size": project_wheel.stat().st_size,
            "tags": sorted(
                str(tag) for tag in parse_wheel_filename(project_wheel.name)[3]
            ),
            "url": "project:.",
            "source_sha256": project_record.sha256,
        }
    )
    records.sort(key=lambda item: canonicalize_name(item["name"]))
    manifest = {
        "target": {"python": python_version, "platform": platform},
        "subtap_version": project_record.version,
        "external_packages": EXTERNAL_PACKAGES,
        "packages": records,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "licenses.json").write_text(
        json.dumps(license_records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "requirements.txt").write_text(
        "".join(
            f"{record['name']}=={record['version']} --hash=sha256:{record['sha256']}\n"
            for record in records
        ),
        encoding="utf-8",
    )
    checksummed = sorted(item for item in output_dir.rglob("*") if item.is_file())
    (output_dir / "SHA256SUMS").write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(output_dir).as_posix()}\n"
            for path in checksummed
        ),
        encoding="utf-8",
    )
    size = _directory_size(output_dir)
    if size > max_bytes:
        raise WheelhouseError(f"wheelhouse exceeds {max_bytes} bytes: {size} bytes")
    archive = output_dir.parent / (
        f"subtap-{project_record.version}-py313-macos-arm64-wheelhouse.tar.gz"
    )
    _write_deterministic_tar(output_dir, archive)
    if archive.stat().st_size > max_bytes:
        raise WheelhouseError(
            f"wheelhouse archive exceeds {max_bytes} bytes: {archive.stat().st_size} bytes"
        )
    # Embed archive SHA256 in manifest for cross-validation by the Formula renderer.
    manifest["wheelhouse_sha256"] = sha256_file(archive)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return archive


def _json_object(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WheelhouseError(f"cannot read JSON {path}: {exc}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WheelhouseError(
            f"invalid JSON {path}: {exc.msg} at line {exc.lineno} column {exc.colno}"
        ) from exc
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
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--python-version", default="3.13")
    build_parser.add_argument("--platform", default="macosx_14_0_arm64")
    build_parser.add_argument("--output", type=Path, required=True)
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
    elif args.command == "build":
        archive = build_wheelhouse(
            args.output,
            python_version=args.python_version,
            platform=args.platform,
        )
        print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
