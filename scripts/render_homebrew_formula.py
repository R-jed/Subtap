"""Render a Homebrew Formula from a wheelhouse manifest and template."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLACEHOLDER_VERSION = "VERSION_PLACEHOLDER"
PLACEHOLDER_URL = "WHEELHOUSE_URL_PLACEHOLDER"
PLACEHOLDER_SHA256 = "WHEELHOUSE_SHA256_PLACEHOLDER"


def _read_json(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON {path}: {exc.msg} at line {exc.lineno}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def render(
    *,
    manifest_path: Path,
    template_path: Path,
    wheelhouse_url: str,
    wheelhouse_sha256: str,
) -> str:
    """Render the Formula template with values from the manifest.

    Raises ``ValueError`` on contract violations, file I/O, or JSON errors.
    """
    if not wheelhouse_url:
        raise ValueError("wheelhouse_url must not be empty")
    if not wheelhouse_sha256:
        raise ValueError("wheelhouse_sha256 must not be empty")

    manifest = _read_json(manifest_path)
    version = manifest.get("subtap_version")
    if not version:
        raise ValueError("manifest is missing required field 'subtap_version'")
    version = str(version)

    # Cross-validate SHA256 against manifest (mandatory — tamper detection)
    manifest_sha256 = manifest.get("wheelhouse_sha256")
    if not manifest_sha256:
        raise ValueError(
            "manifest is missing required field 'wheelhouse_sha256' — "
            "possible tampering or stale manifest"
        )
    if str(manifest_sha256) != wheelhouse_sha256:
        raise ValueError(
            f"wheelhouse_sha256 mismatch: manifest has {manifest_sha256!r}, "
            f"but got {wheelhouse_sha256!r}"
        )

    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {template_path}: {exc}") from exc

    rendered = (
        template.replace(PLACEHOLDER_VERSION, version)
        .replace(PLACEHOLDER_URL, wheelhouse_url)
        .replace(PLACEHOLDER_SHA256, wheelhouse_sha256)
    )
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render Homebrew Formula from wheelhouse manifest and template."
    )
    parser.add_argument(
        "--manifest", type=Path, required=True, help="Path to manifest.json"
    )
    parser.add_argument(
        "--template", type=Path, required=True, help="Path to subtap.rb.in"
    )
    parser.add_argument(
        "--wheelhouse-url",
        required=True,
        help="Download URL for the wheelhouse tarball",
    )
    parser.add_argument(
        "--wheelhouse-sha256", required=True, help="SHA256 of the wheelhouse tarball"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Output path for subtap.rb"
    )
    args = parser.parse_args()

    result = render(
        manifest_path=args.manifest,
        template_path=args.template,
        wheelhouse_url=args.wheelhouse_url,
        wheelhouse_sha256=args.wheelhouse_sha256,
    )
    args.output.write_text(result, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
