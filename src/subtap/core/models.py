"""Model management system: registry, download, verify."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

from subtap.schemas.config import SubtapConfig

logger = logging.getLogger(__name__)

# Model registry: name → (description, expected_subdir, required_files)
MODEL_REGISTRY: dict[str, dict] = {
    "asr": {
        "description": "MLX Qwen ASR model",
        "subdir": "asr",
        "required_files": ["config.json", "model.safetensors"],
    },
    "aligner": {
        "description": "MLX Qwen ForcedAligner model",
        "subdir": "aligner",
        "required_files": ["config.json", "model.safetensors"],
    },
}


def _get_model_root(config: SubtapConfig) -> Path:
    """Resolve model root path from config."""
    return Path(config.models.root).expanduser()


class ModelStatus:
    """Status of a single model."""

    def __init__(self, name: str, installed: bool, path: Path, missing_files: list[str] | None = None):
        self.name = name
        self.installed = installed
        self.path = path
        self.missing_files = missing_files or []

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "installed": self.installed,
            "path": str(self.path),
            "missing_files": self.missing_files,
        }


class ModelRegistry:
    """Query model status across all registered models."""

    def __init__(self, config: SubtapConfig):
        self.config = config
        self.root = _get_model_root(config)

    def status(self) -> list[ModelStatus]:
        """Check status of all registered models."""
        results: list[ModelStatus] = []
        for name, info in MODEL_REGISTRY.items():
            model_dir = self.root / info["subdir"]
            missing = []
            for f in info["required_files"]:
                if not (model_dir / f).exists():
                    missing.append(f)
            results.append(ModelStatus(
                name=name,
                installed=len(missing) == 0,
                path=model_dir,
                missing_files=missing,
            ))
        return results

    def get_path(self, model_name: str) -> Path:
        """Get the directory path for a specific model."""
        info = MODEL_REGISTRY.get(model_name)
        if info is None:
            raise ValueError(f"Unknown model: {model_name}")
        return self.root / info["subdir"]

    def is_available(self, model_name: str) -> bool:
        """Check if a model is installed and complete."""
        info = MODEL_REGISTRY.get(model_name)
        if info is None:
            return False
        model_dir = self.root / info["subdir"]
        return all((model_dir / f).exists() for f in info["required_files"])


class ModelDownloader:
    """Download models (stub — real implementation needs model hosting)."""

    def __init__(self, config: SubtapConfig):
        self.config = config
        self.root = _get_model_root(config)

    def download(self, model_name: str, force: bool = False) -> Path:
        """Download a model. Stub implementation raises.

        Real implementation would fetch from model hosting service.
        """
        info = MODEL_REGISTRY.get(model_name)
        if info is None:
            raise ValueError(f"Unknown model: {model_name}")

        model_dir = self.root / info["subdir"]
        model_dir.mkdir(parents=True, exist_ok=True)

        # Stub: check if already present
        if not force and all((model_dir / f).exists() for f in info["required_files"]):
            logger.info("Model %s already present at %s", model_name, model_dir)
            return model_dir

        raise NotImplementedError(
            f"Model download not yet implemented. "
            f"Please manually place model files in: {model_dir}\n"
            f"Expected files: {info['required_files']}"
        )


class ModelVerifier:
    """Verify model integrity."""

    def __init__(self, config: SubtapConfig):
        self.config = config
        self.root = _get_model_root(config)

    def verify(self, model_name: str) -> dict:
        """Verify a model's files exist and are non-empty.

        Returns dict with status and details.
        """
        info = MODEL_REGISTRY.get(model_name)
        if info is None:
            return {"name": model_name, "status": "unknown", "error": "Model not in registry"}

        model_dir = self.root / info["subdir"]
        results = {"name": model_name, "status": "ok", "files": {}}

        for f in info["required_files"]:
            fpath = model_dir / f
            if fpath.exists():
                size = fpath.stat().st_size
                results["files"][f] = {"exists": True, "size": size}
                if size == 0:
                    results["status"] = "corrupt"
            else:
                results["files"][f] = {"exists": False, "size": 0}
                results["status"] = "missing"

        return results
