"""Tests for versioned model manifest."""

from pathlib import Path

from subtap.core.manifest import load_manifest


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
