"""Tests for versioned model manifest."""

import pytest
from pathlib import Path
from types import SimpleNamespace

from subtap.core.manifest import load_manifest, get_manifest_path


def test_load_manifest_parses_all_models(tmp_path: Path) -> None:
    """Manifest YAML with one model parses into ModelManifest correctly."""
    yaml_content = """
version: "1.0.0"
models:
  asr_0.6b:
    description: "Qwen3 ASR 0.6B MLX 8bit"
    subdir: "asr_0.6b"
    hf_repo: "aufklarer/Qwen3-ASR-0.6B-MLX-8bit"
    modelscope_repo: "aufklarer/Qwen3-ASR-0.6B-MLX-8bit"
    min_disk_bytes: 500000000
    compatibility:
      subtap_min: "0.1.0"
    tags: ["asr", "fast"]
    required_files:
      - name: "config.json"
        sha256: "abc123"
        size_bytes: 1000
"""
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml_content)
    manifest = load_manifest(path)
    assert manifest.version == "1.0.0"
    assert "asr_0.6b" in manifest.models
    entry = manifest.models["asr_0.6b"]
    assert entry.required_files[0].sha256 == "abc123"
    assert entry.compatibility.subtap_min == "0.1.0"
    assert "fast" in entry.tags


def test_manifest_model_entry_to_legacy_dict(tmp_path: Path) -> None:
    """to_legacy_dict returns dict matching old MODEL_REGISTRY format."""
    yaml_content = """
version: "1.0.0"
models:
  aligner:
    description: "Aligner"
    subdir: "aligner"
    hf_repo: "repo/aligner"
    modelscope_repo: "repo/aligner"
    min_disk_bytes: 100000000
    compatibility:
      subtap_min: "0.1.0"
    tags: ["align"]
    required_files:
      - name: "config.json"
        sha256: "def456"
        size_bytes: 500
"""
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml_content)
    manifest = load_manifest(path)
    entry = manifest.models["aligner"]
    legacy = entry.to_legacy_dict()
    assert legacy["subdir"] == "aligner"
    assert legacy["required_files"] == ["config.json"]
    assert legacy["hf_repo"] == "repo/aligner"


def _make_config(tmp_path: Path, manifest_path: str) -> SimpleNamespace:
    """Build a minimal config-like object for ModelRegistry."""
    return SimpleNamespace(
        models=SimpleNamespace(
            root=str(tmp_path / "models"),
            manifest_path=manifest_path,
            hf_endpoint="https://huggingface.co",
            hf_mirror_endpoint="https://hf-mirror.com",
        )
    )


_MANIFEST_YAML = """\
version: "1.0.0"
models:
  test_model:
    description: "Test"
    subdir: "test_model"
    hf_repo: "repo/test"
    modelscope_repo: "repo/test"
    min_disk_bytes: 100
    compatibility:
      subtap_min: "0.1.0"
    tags: ["test"]
    required_files:
      - name: "config.json"
        sha256: "abc123"
        size_bytes: 50
"""


def test_model_registry_loads_from_manifest(tmp_path: Path) -> None:
    """ModelRegistry prefers manifest.yaml over hardcoded MODEL_REGISTRY."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(_MANIFEST_YAML)
    config = _make_config(tmp_path, str(manifest_file))

    from subtap.core.models import ModelRegistry

    registry = ModelRegistry(config)
    assert "test_model" in registry.list_available()
    assert registry._manifest is not None


def test_model_registry_falls_back_without_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    """ModelRegistry falls back to MODEL_REGISTRY when no manifest exists."""
    config = _make_config(tmp_path, "")

    import subtap.core.models as models_mod

    monkeypatch.setattr(
        models_mod, "get_manifest_path", lambda _: tmp_path / "nonexistent.yaml"
    )

    from subtap.core.models import ModelRegistry

    registry = ModelRegistry(config)
    assert registry._manifest is None
    names = registry.list_available()
    assert "asr_0.6b" in names


def test_get_sha256_returns_hash_from_manifest(tmp_path: Path) -> None:
    """get_sha256 returns file hash when manifest is loaded."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(_MANIFEST_YAML)
    config = _make_config(tmp_path, str(manifest_file))

    from subtap.core.models import ModelRegistry

    registry = ModelRegistry(config)
    assert registry.get_sha256("test_model", "config.json") == "abc123"


def test_get_sha256_returns_none_without_manifest(tmp_path: Path, monkeypatch) -> None:
    """get_sha256 returns None when no manifest is loaded."""
    config = _make_config(tmp_path, "")

    import subtap.core.models as models_mod

    monkeypatch.setattr(
        models_mod, "get_manifest_path", lambda _: tmp_path / "nonexistent.yaml"
    )

    from subtap.core.models import ModelRegistry

    registry = ModelRegistry(config)
    assert registry.get_sha256("asr_0.6b", "config.json") is None


def test_manifest_sha256_not_empty() -> None:
    """清单中已下载模型文件的 SHA256 不应为空。"""
    config = SimpleNamespace(models=SimpleNamespace(root="models"))
    manifest_path = get_manifest_path(config)

    if not manifest_path.exists():
        pytest.skip("manifest not found")

    manifest = load_manifest(manifest_path)
    models_root = Path.home() / ".subtap" / "models"
    if not models_root.exists():
        pytest.skip("model files not available")

    for model_id, entry in manifest.models.items():
        model_dir = models_root / entry.subdir
        if not model_dir.exists():
            pytest.skip(f"model {model_id} not downloaded")
        for file_info in entry.required_files:
            if (model_dir / file_info.name).exists():
                assert file_info.sha256, f"{model_id}/{file_info.name} SHA256 为空"
