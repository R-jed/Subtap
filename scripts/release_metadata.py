#!/usr/bin/env python3
"""Validate a release tag and expose metadata to GitHub Actions."""

from __future__ import annotations

import os
from pathlib import Path
import re
import tomllib


def validate_tag(tag: str, version: str) -> bool:
    expected = f"v{version}"
    if tag != expected:
        raise ValueError(f"release tag {tag!r} must exactly match {expected!r}")
    return bool(re.search(r"(?:a|b|rc)\d+$|\.dev\d+$", version))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with (root / "pyproject.toml").open("rb") as file:
        version = tomllib.load(file)["project"]["version"]
    is_prerelease = validate_tag(os.environ["GITHUB_REF_NAME"], version)

    output = Path(os.environ["GITHUB_OUTPUT"])
    with output.open("a", encoding="utf-8") as file:
        file.write(f"version={version}\n")
        file.write(f"is_prerelease={str(is_prerelease).lower()}\n")


if __name__ == "__main__":
    main()
