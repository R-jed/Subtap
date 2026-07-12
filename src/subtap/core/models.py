"""Model management system: registry, download, verify."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, TypedDict, cast

from subtap.core.manifest import ModelManifest, get_manifest_path, load_manifest
from subtap.schemas.config import SubtapConfig

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ROOT = Path.home() / ".subtap" / "models"


class ModelEntry(TypedDict):
    """Schema for a single model registry entry."""

    description: str
    subdir: str
    required_files: list[str]
    hf_repo: str
    modelscope_repo: str


# Model registry: name → ModelEntry
MODEL_REGISTRY: dict[str, ModelEntry] = {
    "asr_0.6b": {
        "description": "Qwen3 ASR 0.6B MLX 8bit",
        "subdir": "asr_0.6b",
        "required_files": [
            "config.json",
            "model.safetensors",
            "tokenizer_config.json",
            "vocab.json",
            "merges.txt",
        ],
        "hf_repo": "aufklarer/Qwen3-ASR-0.6B-MLX-8bit",
        "modelscope_repo": "aufklarer/Qwen3-ASR-0.6B-MLX-8bit",
    },
    "asr_1.7b": {
        "description": "Qwen3 ASR 1.7B MLX 8bit",
        "subdir": "asr_1.7b",
        "required_files": [
            "config.json",
            "model.safetensors",
            "tokenizer_config.json",
            "vocab.json",
            "merges.txt",
        ],
        "hf_repo": "aufklarer/Qwen3-ASR-1.7B-MLX-8bit",
        "modelscope_repo": "aufklarer/Qwen3-ASR-1.7B-MLX-8bit",
    },
    "aligner": {
        "description": "Qwen3 ForcedAligner 0.6B MLX 8bit",
        "subdir": "aligner",
        "required_files": [
            "config.json",
            "model.safetensors",
            "tokenizer_config.json",
            "vocab.json",
            "merges.txt",
        ],
        "hf_repo": "mlx-community/Qwen3-ForcedAligner-0.6B-8bit",
        "modelscope_repo": "mlx-community/Qwen3-ForcedAligner-0.6B-8bit",
    },
}


def _get_model_root(config: SubtapConfig) -> Path:
    """Resolve model root path from config."""
    root = Path(config.models.root).expanduser()
    if root.is_absolute():
        return root
    if root == Path("models"):
        return DEFAULT_MODEL_ROOT
    return Path.home() / ".subtap" / root


class ModelStatus:
    """Status of a single model."""

    def __init__(
        self,
        name: str,
        installed: bool,
        path: Path,
        missing_files: list[str] | None = None,
    ):
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
        self._manifest = self._load_manifest_if_available(config)

    def _load_manifest_if_available(
        self, config: SubtapConfig
    ) -> ModelManifest | None:
        """Try loading manifest; return None on any failure."""
        try:
            path = get_manifest_path(config)
            if not path.exists():
                return None
            return load_manifest(path)
        except Exception:
            logger.debug("Failed to load manifest, falling back to MODEL_REGISTRY")
            return None

    def _registry(self) -> dict[str, dict[str, Any]]:
        """Return model registry: manifest-backed or legacy hardcoded."""
        if self._manifest is not None:
            return {
                name: entry.to_legacy_dict()
                for name, entry in self._manifest.models.items()
            }
        return MODEL_REGISTRY  # type: ignore[return-value]

    def list_available(self) -> list[str]:
        """List all available model names."""
        return list(self._registry().keys())

    def status(self) -> list[ModelStatus]:
        """Check status of all registered models."""
        results: list[ModelStatus] = []
        for name, info in self._registry().items():
            model_dir = self.root / info["subdir"]
            missing = []
            for f in info["required_files"]:
                if not (model_dir / f).exists():
                    missing.append(f)
            results.append(
                ModelStatus(
                    name=name,
                    installed=len(missing) == 0,
                    path=model_dir,
                    missing_files=missing,
                )
            )
        return results

    def get_path(self, model_name: str) -> Path:
        """Get the directory path for a specific model."""
        info = self._registry().get(model_name)
        if info is None:
            raise ValueError(f"Unknown model: {model_name}")
        return self.root / info["subdir"]

    def is_available(self, model_name: str) -> bool:
        """Check if a model is installed and complete."""
        info = self._registry().get(model_name)
        if info is None:
            return False
        model_dir = self.root / info["subdir"]
        return all((model_dir / f).exists() for f in info["required_files"])

    def get_sha256(self, model_name: str, filename: str) -> str | None:
        """Get SHA256 hash for a model file from the manifest.

        Returns None when no manifest is loaded or the file has no hash.
        """
        if self._manifest is None:
            return None
        entry = self._manifest.models.get(model_name)
        if entry is None:
            return None
        for f in entry.required_files:
            if f.name == filename:
                return f.sha256 or None
        return None


DEFAULT_TIMEOUT = 5


def _clean_endpoint(value: str) -> str:
    """Remove trailing slash from endpoint URL."""
    return value.rstrip("/")


class ModelDownloader:
    """Download models from HuggingFace, HF Mirror, or ModelScope."""

    def __init__(self, config: SubtapConfig):
        self.config = config
        self.root = _get_model_root(config)

    def build_file_url(self, source: str, repo: str, filename: str) -> str:
        """Build download URL for a model file."""
        if source == "hf":
            endpoint = _clean_endpoint(self.config.models.hf_endpoint)
            return f"{endpoint}/{repo}/resolve/main/{filename}"
        if source == "hf-mirror":
            endpoint = _clean_endpoint(self.config.models.hf_mirror_endpoint)
            return f"{endpoint}/{repo}/resolve/main/{filename}"
        if source == "modelscope":
            return f"https://modelscope.cn/models/{repo}/resolve/master/{filename}"
        raise ValueError(f"未知下载源：{source}")

    def check_connectivity(self, source: str, repo: str) -> bool:
        """Check if source is reachable by HEAD request."""
        import urllib.request

        filename = "config.json"
        url = self.build_file_url(source, repo, filename)
        request = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
                return 200 <= response.status < 400
        except Exception:
            return False

    def download(self, model_name: str, source: str = "hf", progress=None) -> Path:
        """Download model files from source.

        Args:
            model_name: Name from MODEL_REGISTRY
            source: Download source (hf, hf-mirror, modelscope)
            progress: Optional callback(filename, downloaded_bytes, total_bytes)

        Returns:
            Path to downloaded model directory
        """
        if model_name not in MODEL_REGISTRY:
            raise ValueError(f"未知模型：{model_name}")

        info = MODEL_REGISTRY[model_name]
        repo_key = "modelscope_repo" if source == "modelscope" else "hf_repo"
        repo = cast(str, info.get(repo_key) or "")
        if not repo:
            raise ValueError(
                f"{model_name} 未配置 {source} / ModelScope 下载仓库，请手动放入 models/"
            )

        model_dir = self.root / info["subdir"]
        model_dir.mkdir(parents=True, exist_ok=True)
        try:
            for filename in info["required_files"]:
                url = self.build_file_url(source, repo, filename)
                self._download_file(url, model_dir / filename, progress=progress)
        except Exception:
            if model_dir.exists():
                shutil.rmtree(model_dir)
            raise
        return model_dir

    def _download_file(self, url: str, dest: Path, progress=None) -> None:
        """Download a single file with optional progress callback."""
        import urllib.request

        request = urllib.request.Request(url)
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
            total = int(response.getheader("content-length", "0"))
            downloaded = 0
            if progress:
                progress(dest.name, downloaded, total)
            with open(dest, "wb") as f:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(dest.name, downloaded, total)


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
            return {
                "name": model_name,
                "status": "unknown",
                "error": "Model not in registry",
            }

        model_dir = self.root / info["subdir"]
        results: dict[str, Any] = {"name": model_name, "status": "ok", "files": {}}

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


class ModelRemover:
    """Remove installed models."""

    def __init__(self, config: SubtapConfig):
        self.config = config
        self.root = _get_model_root(config)

    def remove(self, model_name: str) -> bool:
        """Remove a model directory.

        Args:
            model_name: Name of model to remove

        Returns:
            True if removal succeeded.
        """
        info = MODEL_REGISTRY.get(model_name)
        if info is None:
            raise ValueError(f"Unknown model: {model_name}")

        model_dir = self.root / info["subdir"]
        if model_dir.exists():
            shutil.rmtree(model_dir)
            return True
        return False
