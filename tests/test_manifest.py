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


def test_model_registry_fails_without_manifest(tmp_path: Path, monkeypatch) -> None:
    """ModelRegistry 缺少可信清单时必须明确失败。"""
    config = _make_config(tmp_path, "")

    import subtap.core.models as models_mod

    monkeypatch.setattr(
        models_mod, "get_manifest_path", lambda _: tmp_path / "nonexistent.yaml"
    )

    from subtap.core.models import ModelRegistry

    with pytest.raises(FileNotFoundError, match="模型清单不存在"):
        ModelRegistry(config)


def test_get_sha256_returns_hash_from_manifest(tmp_path: Path) -> None:
    """get_sha256 returns file hash when manifest is loaded."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(_MANIFEST_YAML)
    config = _make_config(tmp_path, str(manifest_file))

    from subtap.core.models import ModelRegistry

    registry = ModelRegistry(config)
    assert registry.get_sha256("test_model", "config.json") == "abc123"


def test_model_registry_reports_invalid_manifest(tmp_path: Path, monkeypatch) -> None:
    """清单格式错误必须传递给调用方。"""
    config = _make_config(tmp_path, "")

    import subtap.core.models as models_mod

    invalid = tmp_path / "manifest.yaml"
    invalid.write_text("models: [invalid", encoding="utf-8")
    monkeypatch.setattr(models_mod, "get_manifest_path", lambda _: invalid)

    from subtap.core.models import ModelRegistry

    with pytest.raises(Exception):
        ModelRegistry(config)


def test_download_refuses_file_without_manifest_hash(
    tmp_path: Path, monkeypatch
) -> None:
    """下载主流程缺少可信哈希时必须失败。"""
    from subtap.core.models import ModelDownloader, ModelRegistry

    monkeypatch.setattr(
        ModelDownloader,
        "_download_file_with_resume",
        lambda self, url, dest, progress=None: dest.write_bytes(b"unverified"),
    )
    monkeypatch.setattr(ModelRegistry, "get_sha256", lambda *args: None)

    downloader = ModelDownloader(_make_config(tmp_path, ""))
    with pytest.raises(RuntimeError, match="缺少 SHA256"):
        downloader.download("asr_0.6b", max_retries=1)


def test_download_validates_all_hashes_before_network(
    tmp_path: Path, monkeypatch
) -> None:
    """清单末尾缺哈希也必须在任何网络请求前失败。"""
    from subtap.core.models import ModelDownloader, ModelRegistry

    downloaded = []
    monkeypatch.setattr(
        ModelDownloader,
        "_download_file_with_resume",
        lambda self, url, dest, progress=None: downloaded.append(dest),
    )
    monkeypatch.setattr(
        ModelRegistry,
        "get_sha256",
        lambda self, model, filename: None if filename == "merges.txt" else "0" * 64,
    )

    with pytest.raises(RuntimeError, match="merges.txt"):
        ModelDownloader(_make_config(tmp_path, "")).download("asr_0.6b", max_retries=1)

    assert downloaded == []


def test_default_manifest_resolves_packaged_resource(
    tmp_path: Path, monkeypatch
) -> None:
    """安装包内的 manifest 是默认可信清单。"""
    import subtap.core.manifest as manifest_mod

    module_path = tmp_path / "subtap" / "core" / "manifest.py"
    packaged = tmp_path / "subtap" / "resources" / "model_manifest.yaml"
    packaged.parent.mkdir(parents=True)
    packaged.write_text("version: '1.0.0'\nmodels: {}\n", encoding="utf-8")
    monkeypatch.setattr(manifest_mod, "__file__", str(module_path))

    assert manifest_mod.get_manifest_path(object()) == packaged


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


def test_default_manifest_requires_asr_preprocessor_config() -> None:
    """ASR models must include the feature extractor configuration."""
    manifest = load_manifest(get_manifest_path(None))

    for model_id in ("asr_0.6b", "asr_1.7b"):
        required = {
            file_info.name for file_info in manifest.models[model_id].required_files
        }
        assert "preprocessor_config.json" in required
