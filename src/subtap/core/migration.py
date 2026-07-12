"""Legacy ~/.subtap layout migration to new directory structure.

Old layout:
    glossary/hotwords_zh.txt  ->  glossaries/default.yaml
    glossary/global.yaml      ->  glossaries/default.yaml
    config.yaml               ->  kept as-is (skipped)
    subtap.db                 ->  kept as-is (skipped)

New layout directories created if missing:
    models/  glossaries/  manuscripts/  jobs/  cache/downloads/  logs/

Design:
    - plan_migration() is read-only: returns a MigrationPlan without touching files.
    - execute_migration() applies the plan: creates dirs, moves files.
    - Unknown files are never deleted; they appear in skips.
    - Repeated calls produce the same plan (idempotent).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Move:
    """A single file move operation."""

    src: Path
    dst: Path
    reason: str


@dataclass
class MigrationPlan:
    """Planned migration steps. plan_migration() returns this; execute_migration() applies it."""

    moves: list[Move] = field(default_factory=list)
    creates: list[str] = field(default_factory=list)
    skips: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Migration map (hardcoded)
# ---------------------------------------------------------------------------

# Old relative path -> (new relative path, reason)
_MIGRATION_MAP: dict[str, tuple[str, str]] = {
    "glossary/hotwords_zh.txt": (
        "glossaries/default.yaml",
        "hotwords_zh.txt -> glossaries/default.yaml",
    ),
    "glossary/global.yaml": (
        "glossaries/default.yaml",
        "global.yaml -> glossaries/default.yaml",
    ),
}

# New-layout directories that must always exist
_REQUIRED_DIRS: list[str] = [
    "models",
    "glossaries",
    "glossaries/imported",
    "manuscripts",
    "jobs",
    "cache/downloads",
    "logs",
]

# Files/dirs to skip (known old-layout items that are kept as-is)
_KNOWN_SKIP_NAMES: set[str] = {"config.yaml", "subtap.db", "glossary"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def plan_migration(subtap_root: Path) -> MigrationPlan:
    """Plan migration from old ~/.subtap layout to new directory structure.

    This function is **read-only**: it inspects the filesystem and returns a
    plan, but does not create, move, or delete anything.

    Args:
        subtap_root: Path to ~/.subtap directory.

    Returns:
        MigrationPlan with moves, creates, and skips.
    """
    plan = MigrationPlan()

    # --- moves ---
    # If both old hotwords_zh.txt and global.yaml exist and both map to the
    # same destination, we must only keep one move (hotwords wins).  To stay
    # idempotent, we track which destinations are already claimed.
    claimed_dsts: set[str] = set()

    for old_rel, (new_rel, reason) in _MIGRATION_MAP.items():
        src = subtap_root / old_rel
        if src.exists() and new_rel not in claimed_dsts:
            plan.moves.append(
                Move(
                    src=subtap_root / old_rel, dst=subtap_root / new_rel, reason=reason
                )
            )
            claimed_dsts.add(new_rel)

    # --- creates ---
    for d in _REQUIRED_DIRS:
        if not (subtap_root / d).is_dir():
            plan.creates.append(d)

    # --- skips ---
    # Walk the root; anything that isn't part of a move source and isn't a
    # required-dir gets flagged as skip.
    if subtap_root.is_dir():
        for entry in sorted(subtap_root.iterdir()):
            name = entry.name
            # Already a new-layout directory or will be created
            if name in {d.split("/")[0] for d in _REQUIRED_DIRS}:
                continue
            # Part of a move
            rel = entry.relative_to(subtap_root)
            if any(m.src == entry for m in plan.moves):
                continue
            # Parent of a move source (e.g. glossary/ contains files being moved)
            if any(m.src.parent == entry for m in plan.moves):
                continue
            # Known skip
            if name in _KNOWN_SKIP_NAMES:
                plan.skips.append(name)
            elif entry.is_file():
                plan.skips.append(name)

    return plan


def execute_migration(plan: MigrationPlan, subtap_root: Path) -> bool:
    """Execute a migration plan.

    Creates directories listed in ``plan.creates`` and moves files listed in
    ``plan.moves``.  Files in ``plan.skips`` are left untouched.

    Safe to call repeatedly: directories are created with ``exist_ok=True``,
    and moves that have already been applied (source missing, destination
    present) are silently skipped.

    Args:
        plan: The migration plan (from plan_migration).
        subtap_root: Path to ~/.subtap directory.

    Returns:
        True if the migration completed without errors.
    """
    # 1. Create directories
    for rel in plan.creates:
        (subtap_root / rel).mkdir(parents=True, exist_ok=True)

    # 2. Move files
    for move in plan.moves:
        src = move.src
        dst = move.dst
        # Idempotent: skip if source already gone (already moved)
        if not src.exists():
            continue
        # Never overwrite existing destination — preserve user data
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

    # 3. Clean up empty old glossary/ directory if all its contents were moved
    glossary_dir = subtap_root / "glossary"
    if glossary_dir.is_dir() and not any(glossary_dir.iterdir()):
        glossary_dir.rmdir()

    return True
