"""Tests for legacy data migration (Task 4)."""

from __future__ import annotations

from pathlib import Path

from subtap.core.migration import MigrationPlan, Move, execute_migration, plan_migration


# ---------------------------------------------------------------------------
# plan_migration
# ---------------------------------------------------------------------------


def test_plan_migration_detects_old_glossary(tmp_path: Path) -> None:
    """Old glossary/ directory should produce moves."""
    subtap = tmp_path / ".subtap"
    subtap.mkdir()
    (subtap / "glossary").mkdir()
    (subtap / "glossary" / "hotwords_zh.txt").write_text("热词=错词")
    (subtap / "config.yaml").write_text("mode: offline\n")

    plan = plan_migration(subtap)

    assert any("glossary" in m.src.parts for m in plan.moves)


def test_plan_migration_is_idempotent(tmp_path: Path) -> None:
    """Running plan_migration twice on an already-migrated layout yields identical results."""
    subtap = tmp_path / ".subtap"
    subtap.mkdir()
    (subtap / "glossaries").mkdir()
    (subtap / "models").mkdir()

    plan1 = plan_migration(subtap)
    plan2 = plan_migration(subtap)

    assert len(plan1.moves) == len(plan2.moves)
    assert len(plan1.creates) == len(plan2.creates)
    assert len(plan1.skips) == len(plan2.skips)


def test_plan_migration_preserves_unknown_files(tmp_path: Path) -> None:
    """Unknown files are listed in skips, never deleted."""
    subtap = tmp_path / ".subtap"
    subtap.mkdir()
    (subtap / "mystery_file.txt").write_text("don't delete me")

    plan = plan_migration(subtap)

    assert (subtap / "mystery_file.txt").exists()
    assert plan.skips
    assert "mystery_file.txt" in plan.skips


def test_plan_migration_creates_missing_dirs(tmp_path: Path) -> None:
    """Missing new-layout directories should appear in creates list."""
    subtap = tmp_path / ".subtap"
    subtap.mkdir()

    plan = plan_migration(subtap)

    expected = {"models", "glossaries", "glossaries/imported", "manuscripts", "jobs", "cache/downloads", "logs"}
    assert set(plan.creates) == expected


def test_plan_migration_no_moves_when_already_migrated(tmp_path: Path) -> None:
    """If new layout already exists and old layout is absent, moves should be empty."""
    subtap = tmp_path / ".subtap"
    subtap.mkdir()
    (subtap / "glossaries").mkdir()
    (subtap / "models").mkdir()
    (subtap / "manuscripts").mkdir()
    (subtap / "jobs").mkdir()
    (subtap / "cache" / "downloads").mkdir(parents=True)
    (subtap / "logs").mkdir()

    plan = plan_migration(subtap)

    assert plan.moves == []


def test_plan_migration_hotwords_to_default_yaml(tmp_path: Path) -> None:
    """hotwords_zh.txt should be moved to glossaries/default.yaml."""
    subtap = tmp_path / ".subtap"
    subtap.mkdir()
    (subtap / "glossary").mkdir()
    (subtap / "glossary" / "hotwords_zh.txt").write_text("热词=错词")

    plan = plan_migration(subtap)

    moves = [m for m in plan.moves if "hotwords_zh.txt" in m.src.name]
    assert len(moves) == 1
    assert moves[0].dst.name == "default.yaml"
    assert "glossaries" in moves[0].dst.parts


def test_plan_migration_global_yaml_to_default_yaml(tmp_path: Path) -> None:
    """global.yaml should be moved to glossaries/default.yaml."""
    subtap = tmp_path / ".subtap"
    subtap.mkdir()
    (subtap / "glossary").mkdir()
    (subtap / "glossary" / "global.yaml").write_text("terms: []\n")

    plan = plan_migration(subtap)

    moves = [m for m in plan.moves if "global.yaml" in m.src.name]
    assert len(moves) == 1
    assert moves[0].dst.name == "default.yaml"


# ---------------------------------------------------------------------------
# execute_migration
# ---------------------------------------------------------------------------


def test_execute_migration_moves_files(tmp_path: Path) -> None:
    """execute_migration should physically move files and create directories."""
    subtap = tmp_path / ".subtap"
    subtap.mkdir()
    (subtap / "glossary").mkdir()
    (subtap / "glossary" / "hotwords_zh.txt").write_text("热词=错词")

    plan = plan_migration(subtap)
    result = execute_migration(plan, subtap)

    assert result is True
    assert (subtap / "glossaries" / "default.yaml").exists()
    assert (subtap / "glossaries" / "default.yaml").read_text() == "热词=错词"
    assert not (subtap / "glossary" / "hotwords_zh.txt").exists()


def test_execute_migration_creates_directories(tmp_path: Path) -> None:
    """execute_migration should create all directories listed in creates."""
    subtap = tmp_path / ".subtap"
    subtap.mkdir()

    plan = plan_migration(subtap)
    execute_migration(plan, subtap)

    for rel in plan.creates:
        assert (subtap / rel).is_dir(), f"{rel} should exist"


def test_execute_migration_idempotent(tmp_path: Path) -> None:
    """Running execute_migration twice should succeed without error."""
    subtap = tmp_path / ".subtap"
    subtap.mkdir()
    (subtap / "glossary").mkdir()
    (subtap / "glossary" / "hotwords_zh.txt").write_text("热词=错词")

    plan = plan_migration(subtap)
    result1 = execute_migration(plan, subtap)
    assert result1 is True

    plan2 = plan_migration(subtap)
    result2 = execute_migration(plan2, subtap)
    assert result2 is True


def test_execute_migration_preserves_unknown_files(tmp_path: Path) -> None:
    """Unknown files should remain untouched after migration."""
    subtap = tmp_path / ".subtap"
    subtap.mkdir()
    (subtap / "mystery_file.txt").write_text("don't delete me")

    plan = plan_migration(subtap)
    execute_migration(plan, subtap)

    assert (subtap / "mystery_file.txt").exists()
    assert (subtap / "mystery_file.txt").read_text() == "don't delete me"
