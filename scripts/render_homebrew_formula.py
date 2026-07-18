"""Render a Homebrew Formula from a wheelhouse manifest and template."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

PLACEHOLDER_URL = "WHEELHOUSE_URL_PLACEHOLDER"
PLACEHOLDER_SHA256 = "WHEELHOUSE_SHA256_PLACEHOLDER"


def _sha256_file(path: Path) -> str:
    try:
        with path.open("rb") as file:
            digest = hashlib.file_digest(file, "sha256")
    except OSError as exc:
        raise ValueError(f"cannot read wheelhouse {path}: {exc}") from exc
    return digest.hexdigest()


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
    wheelhouse_path: Path,
) -> str:
    """Render the Formula template with values from the manifest.

    Raises ``ValueError`` on contract violations, file I/O, or JSON errors.
    """
    if not wheelhouse_url:
        raise ValueError("wheelhouse_url must not be empty")
    wheelhouse_sha256 = _sha256_file(wheelhouse_path)

    manifest = _read_json(manifest_path)
    version = manifest.get("subtap_version")
    if not version:
        raise ValueError("manifest is missing required field 'subtap_version'")
    version = str(version)
    archive_name = Path(urlparse(wheelhouse_url).path).name
    if version not in archive_name:
        raise ValueError(
            f"wheelhouse URL archive name must include manifest version {version}"
        )

    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {template_path}: {exc}") from exc

    rendered = template.replace(PLACEHOLDER_URL, wheelhouse_url).replace(
        PLACEHOLDER_SHA256, wheelhouse_sha256
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
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="Output path for subtap.rb"
    )
    args = parser.parse_args()

    result = render(
        manifest_path=args.manifest,
        template_path=args.template,
        wheelhouse_url=args.wheelhouse_url,
        wheelhouse_path=args.wheelhouse,
    )
    args.output.write_text(result, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
