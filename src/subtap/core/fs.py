"""Filesystem helpers."""

from __future__ import annotations

import os
from pathlib import Path


def os_access_writable(path: Path) -> bool:
    """Return whether path or its nearest existing parent is writable."""
    target = path
    while not target.exists() and target.parent != target:
        target = target.parent
    return os.access(target, os.W_OK)
