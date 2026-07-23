"""Paths and initialization for user-owned Subtap resources."""

from __future__ import annotations

from pathlib import Path


def default_glossary_path(subtap_root: Path | None = None) -> Path:
    """Return the canonical default glossary path."""
    root = subtap_root or Path.home() / ".subtap"
    return root / "glossaries" / "default.txt"


def learned_glossary_path(subtap_root: Path | None = None) -> Path:
    """Return the system-owned learned glossary path."""
    root = subtap_root or Path.home() / ".subtap"
    return root / "glossaries" / "learned.txt"


def _migrate_yaml_glossary(path: Path) -> bool:
    from subtap.schemas.glossary import load_glossary, save_glossary

    old_path = path.with_suffix(".yaml")
    if not old_path.exists():
        return False
    backup_path = old_path.with_name(f"{old_path.name}.bak")
    if backup_path.exists():
        raise FileExistsError(f"热词表备份已存在，无法迁移：{backup_path}")
    glossary = load_glossary(old_path)
    if glossary.replacements or glossary.style:
        raise ValueError(
            "旧热词表包含 replacements 或 style，无法无损迁移；"
            f"原文件保持不变：{old_path}"
        )
    try:
        save_glossary(path, glossary)
        if load_glossary(path) != glossary:
            raise ValueError("迁移后的热词内容校验失败")
        old_path.rename(backup_path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return True


def ensure_default_glossary(subtap_root: Path | None = None) -> Path:
    """Create or safely migrate the user-owned default glossary."""
    path = default_glossary_path(subtap_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or _migrate_yaml_glossary(path):
        return path

    path.write_text(
        "# 每行填写一个热词\n" "# 如需纠正常见错写：正确写法 = 常见错写1, 常见错写2\n",
        encoding="utf-8",
    )
    return path


def ensure_learned_glossary(subtap_root: Path | None = None) -> Path:
    """Return the learned glossary path after migrating legacy YAML if present."""
    path = learned_glossary_path(subtap_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        _migrate_yaml_glossary(path)
    return path
