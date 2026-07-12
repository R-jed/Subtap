"""Uninstall preservation tests.

验证：Homebrew 卸载只删除程序，不删除用户资料。
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_user_data_not_in_subtap_package():
    """用户资料目录不在 subtap 包内。"""
    # ~/.subtap 是运行时创建的，不在 wheel 包内
    import subtap

    pkg_path = Path(subtap.__file__).parent
    # 包路径不应包含用户数据目录
    assert ".subtap" not in str(pkg_path)


def test_models_dir_not_in_package():
    """模型目录不在 wheel 包内。"""
    from pathlib import Path
    import tarfile

    sdists = sorted(Path("dist").glob("subtap-*.tar.gz"))
    if not sdists:
        pytest.skip("sdist not built")

    with tarfile.open(sdists[-1]) as tf:
        names = tf.getnames()

    assert not any("/models/" in name for name in names)


def test_state_json_not_in_package():
    """state.json 不在 wheel 包内。"""
    from pathlib import Path
    import tarfile

    sdists = sorted(Path("dist").glob("subtap-*.tar.gz"))
    if not sdists:
        pytest.skip("sdist not built")

    with tarfile.open(sdists[-1]) as tf:
        names = tf.getnames()

    assert not any("state.json" in name for name in names)


def test_glossaries_not_in_package():
    """热词库不在 wheel 包内。"""
    from pathlib import Path
    import tarfile

    sdists = sorted(Path("dist").glob("subtap-*.tar.gz"))
    if not sdists:
        pytest.skip("sdist not built")

    with tarfile.open(sdists[-1]) as tf:
        names = tf.getnames()

    assert not any("/glossaries/" in name for name in names)


def test_safe_delete_refuses_user_home():
    """安全删除拒绝删除用户主目录。"""
    from subtap.core.safe_delete import validate_delete_path, SafeDeleteError

    with pytest.raises(SafeDeleteError):
        validate_delete_path(Path.home(), allowed_roots=[Path.home() / ".subtap"])


def test_safe_delete_refuses_subtap_root():
    """安全删除拒绝删除 ~/.subtap 根目录。"""
    from subtap.core.safe_delete import validate_delete_path, SafeDeleteError

    subtap_root = Path.home() / ".subtap"

    with pytest.raises(SafeDeleteError):
        validate_delete_path(subtap_root, allowed_roots=[subtap_root / "jobs"])
