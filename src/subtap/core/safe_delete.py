"""Safe delete module for Subtap.

Provides unified path safety validation and safe deletion operations
for the ~/.subtap directory structure.
"""

from pathlib import Path


class SafeDeleteError(Exception):
    """Raised when a delete operation fails safety validation."""


def validate_delete_path(path: Path, *, allowed_roots: list[Path]) -> Path:
    """Validate that a path is safe for deletion.

    Args:
        path: The path to validate.
        allowed_roots: List of allowed root directories.

    Returns:
        The resolved path if validation passes.

    Raises:
        SafeDeleteError: If the path fails any safety check.
    """
    # 空路径检查
    if not path.parts:
        raise SafeDeleteError("空路径：路径不能为空")

    # 相对路径检查
    if not path.is_absolute():
        raise SafeDeleteError("相对路径：必须使用绝对路径")

    # 解析符号链接
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as e:
        raise SafeDeleteError(f"路径解析失败：{e}")

    # 路径穿越检查（含 ..）
    if ".." in path.parts:
        raise SafeDeleteError("路径穿越：路径不能包含 ..")

    # 控制字符检查
    if any(ord(c) < 32 for c in str(path)):
        raise SafeDeleteError("路径包含控制字符")

    # 用户主目录检查
    home = Path.home()
    if resolved == home:
        raise SafeDeleteError("用户主目录：不能删除用户主目录")

    # Subtap 根目录检查
    subtap_root = home / ".subtap"
    if resolved == subtap_root:
        raise SafeDeleteError("Subtap 根目录：不能删除 Subtap 根目录")

    # 不在允许范围检查
    allowed = False
    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            allowed = True
            break
        except ValueError:
            continue

    if not allowed:
        raise SafeDeleteError(f"不在允许范围：路径 {resolved} 不在任何允许的根目录下")

    return resolved


def safe_delete(path: Path, *, allowed_roots: list[Path]) -> bool:
    """Safely delete a file or directory.

    Args:
        path: The path to delete.
        allowed_roots: List of allowed root directories.

    Returns:
        True if deletion was successful.

    Raises:
        SafeDeleteError: If the path fails safety validation.
    """
    resolved = validate_delete_path(path, allowed_roots=allowed_roots)

    if resolved.is_file():
        resolved.unlink()
    elif resolved.is_dir():
        import shutil
        shutil.rmtree(resolved)
    else:
        # Path doesn't exist, consider it already deleted
        pass

    return True


def ensure_directory_structure(subtap_root: Path) -> dict[str, Path]:
    """Create the standard ~/.subtap directory structure.

    Args:
        subtap_root: The root directory for Subtap (e.g., ~/.subtap).

    Returns:
        Dictionary mapping directory names to their paths.
    """
    directories = {
        "models": subtap_root / "models",
        "glossaries": subtap_root / "glossaries",
        "glossaries/imported": subtap_root / "glossaries" / "imported",
        "manuscripts": subtap_root / "manuscripts",
        "jobs": subtap_root / "jobs",
        "cache": subtap_root / "cache",
        "cache/downloads": subtap_root / "cache" / "downloads",
        "logs": subtap_root / "logs",
    }

    for dir_path in directories.values():
        dir_path.mkdir(parents=True, exist_ok=True)

    return directories
