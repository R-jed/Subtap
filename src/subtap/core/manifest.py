"""Versioned model manifest: YAML-backed schema replacing hardcoded MODEL_REGISTRY."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """Metadata for a single required file."""

    name: str
    sha256: str = ""
    size_bytes: int = 0


class CompatibilityInfo(BaseModel):
    """Subtap version compatibility range."""

    subtap_min: str = "0.0.0"
    subtap_max: str = ""


class ModelEntry(BaseModel):
    """Schema for a single model in the manifest."""

    description: str
    subdir: str
    required_files: list[FileInfo] = Field(default_factory=list)
    hf_repo: str = ""
    modelscope_repo: str = ""
    hf_mirror_repo: str = ""
    min_disk_bytes: int = 0
    compatibility: CompatibilityInfo = Field(default_factory=CompatibilityInfo)
    tags: list[str] = Field(default_factory=list)

    def to_legacy_dict(self) -> dict[str, Any]:
        """Convert to legacy MODEL_REGISTRY format."""
        return {
            "description": self.description,
            "subdir": self.subdir,
            "required_files": [f.name for f in self.required_files],
            "hf_repo": self.hf_repo,
            "modelscope_repo": self.modelscope_repo,
        }


class ModelManifest(BaseModel):
    """Top-level model manifest."""

    version: str
    models: dict[str, ModelEntry] = Field(default_factory=dict)


def load_manifest(path: Path) -> ModelManifest:
    """Load and validate a manifest YAML file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ModelManifest.model_validate(data)


def get_manifest_path(config: Any) -> Path:
    """Resolve manifest path from config, falling back to project default."""
    # Check if config has a custom manifest_path
    manifest_path = getattr(getattr(config, "models", None), "manifest_path", None)
    if manifest_path:
        p = Path(manifest_path).expanduser()
        if p.is_absolute():
            return p
        return Path.cwd() / p
    # Default: configs/models/manifest.yaml relative to project root
    return Path(__file__).resolve().parents[3] / "configs" / "models" / "manifest.yaml"
