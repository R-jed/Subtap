"""Tests for subtap.core.safe_delete module."""

import pytest
from pathlib import Path
from subtap.core.safe_delete import safe_delete, SafeDeleteError


def test_rejects_empty_path(tmp_path):
    """空路径应抛出 SafeDeleteError."""
    with pytest.raises(SafeDeleteError, match="空路径"):
        safe_delete(Path(""), allowed_roots=[tmp_path])


def test_rejects_relative_path(tmp_path):
    """相对路径应抛出 SafeDeleteError."""
    with pytest.raises(SafeDeleteError, match="相对路径"):
        safe_delete(Path("models/asr_0.6b"), allowed_roots=[tmp_path])


def test_rejects_dot_dot(tmp_path):
    """含 .. 的路径应抛出 SafeDeleteError."""
    with pytest.raises(SafeDeleteError, match="路径穿越"):
        safe_delete(tmp_path / ".." / "other", allowed_roots=[tmp_path])


def test_rejects_home_directory(tmp_path, monkeypatch):
    """用户主目录本身应抛出 SafeDeleteError."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    with pytest.raises(SafeDeleteError, match="用户主目录"):
        safe_delete(tmp_path, allowed_roots=[tmp_path])


def test_rejects_subtap_root(tmp_path, monkeypatch):
    """~/.subtap 根目录应抛出 SafeDeleteError."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    subtap = tmp_path / ".subtap"
    subtap.mkdir()
    with pytest.raises(SafeDeleteError, match="Subtap 根目录"):
        safe_delete(subtap, allowed_roots=[subtap])


def test_rejects_path_not_under_allowed_root(tmp_path):
    """不在 allowed_roots 下的路径应抛出 SafeDeleteError."""
    target = tmp_path / "other" / "file"
    target.parent.mkdir(parents=True)
    target.write_text("x")
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    with pytest.raises(SafeDeleteError, match="不在允许范围"):
        safe_delete(target, allowed_roots=[allowed])


def test_deletes_file_under_allowed_root(tmp_path):
    """允许范围内的文件应被成功删除."""
    target = tmp_path / "jobs" / "abc" / "chunk.wav"
    target.parent.mkdir(parents=True)
    target.write_text("data")
    assert safe_delete(target, allowed_roots=[tmp_path]) is True
    assert not target.exists()


def test_deletes_directory_under_allowed_root(tmp_path):
    """允许范围内的目录应被成功删除."""
    target = tmp_path / "cache" / "downloads" / "partial"
    target.mkdir(parents=True)
    (target / "file.bin").write_text("data")
    assert safe_delete(target, allowed_roots=[tmp_path]) is True
    assert not target.exists()


def test_resolves_symlinks(tmp_path):
    """符号链接应被正确解析后再删除."""
    real = tmp_path / "real" / "file"
    real.parent.mkdir(parents=True)
    real.write_text("data")
    link = tmp_path / "link"
    link.symlink_to(real.parent)
    safe_delete(link, allowed_roots=[tmp_path])


def test_ensure_directory_structure_creates_all_dirs(tmp_path):
    """应创建所有标准目录."""
    from subtap.core.safe_delete import ensure_directory_structure

    subtap_root = tmp_path / ".subtap"
    ensure_directory_structure(subtap_root)

    assert (subtap_root / "models").is_dir()
    assert (subtap_root / "glossaries").is_dir()
    assert (subtap_root / "glossaries" / "imported").is_dir()
    assert (subtap_root / "manuscripts").is_dir()
    assert (subtap_root / "jobs").is_dir()
    assert (subtap_root / "cache" / "downloads").is_dir()
    assert (subtap_root / "logs").is_dir()


def test_ensure_directory_structure_idempotent(tmp_path):
    """多次调用应幂等，不报错."""
    from subtap.core.safe_delete import ensure_directory_structure

    subtap_root = tmp_path / ".subtap"
    ensure_directory_structure(subtap_root)
    ensure_directory_structure(subtap_root)  # second call ok
    assert (subtap_root / "models").is_dir()
