"""Model management system: registry, download, verify."""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import urllib.request
from pathlib import Path
from typing import Any, TypedDict, cast

from subtap.core.manifest import ModelManifest, get_manifest_path, load_manifest
from subtap.schemas.config import SubtapConfig

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ROOT = Path.home() / ".subtap" / "models"
ASR_MODEL_BY_MODE = {"fast": "asr_0.6b", "quality": "asr_1.7b"}


class ModelEntry(TypedDict):
    """Schema for a single model registry entry."""

    description: str
    subdir: str
    required_files: list[str]
    hf_repo: str
    modelscope_repo: str


class DownloadCancelled(Exception):
    """Raised when a caller cancels a model download."""


class ModelIntegrityError(RuntimeError):
    """Raised when downloaded model content fails trusted hash verification."""


def verify_file_sha256(path: Path, expected_sha256: str, *, cancelled=None) -> bool:
    """Hash a file in chunks, allowing long checks to be cancelled."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            if cancelled is not None and cancelled():
                raise DownloadCancelled("模型校验已取消，可稍后继续")
            digest.update(chunk)
    return digest.hexdigest() == expected_sha256


# Backward-compatible public export, derived from the default trusted manifest.
MODEL_REGISTRY = cast(
    dict[str, ModelEntry],
    {
        name: entry.to_legacy_dict()
        for name, entry in load_manifest(get_manifest_path(None)).models.items()
    },
)


def required_model_names(config: SubtapConfig) -> tuple[str, ...]:
    """Return the complete model set required by the current offline runtime."""
    names = tuple(dict.fromkeys((config.asr.model, config.align.model)))
    available = load_manifest(get_manifest_path(config)).models
    unknown = [name for name in names if name not in available]
    if unknown:
        raise ValueError(f"未知必需模型：{', '.join(unknown)}")
    return names


def apply_asr_mode(config: SubtapConfig, mode: str | None) -> None:
    """Apply an explicit user-facing quality mode to the ASR model selection."""
    if mode is None:
        return
    try:
        config.asr.model = ASR_MODEL_BY_MODE[mode]
    except KeyError as exc:
        raise ValueError(f"--mode 必须是 fast/quality，收到：{mode}") from exc


def asr_mode_for_model(model_name: str) -> str:
    """Return the user-facing quality mode for a supported ASR model."""
    for mode, candidate in ASR_MODEL_BY_MODE.items():
        if candidate == model_name:
            return mode
    raise ValueError(f"未知 ASR 模型：{model_name}")


def validate_required_models(
    config: SubtapConfig, model_names: tuple[str, ...] | None = None
) -> None:
    """Fail before runtime work starts when a required local model is unavailable."""
    required = model_names or required_model_names(config)
    status_by_name = {status.name: status for status in ModelRegistry(config).status()}
    unknown = [name for name in required if name not in status_by_name]
    if unknown:
        raise ValueError(f"未知必需模型：{', '.join(unknown)}")
    missing = [
        status_by_name[name] for name in required if not status_by_name[name].installed
    ]
    if not missing:
        return

    details = "; ".join(
        f"{status.name}（{', '.join(status.missing_files)}）" for status in missing
    )
    commands = "；".join(f"subtap models install {status.name}" for status in missing)
    raise RuntimeError(f"必需模型未就绪：{details}。请运行：{commands}")


def validate_runtime_models(config: SubtapConfig) -> None:
    """Validate the models used by the configured ASR and mandatory aligner."""
    model_names = (
        required_model_names(config)
        if config.asr.backend == "mlx-qwen-asr"
        else (config.align.model,)
    )
    validate_required_models(config, model_names)


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

    def _load_manifest_if_available(self, config: SubtapConfig) -> ModelManifest:
        """Load the trusted manifest or fail before model operations continue."""
        path = get_manifest_path(config)
        if not path.exists():
            raise FileNotFoundError(f"模型清单不存在: {path}")
        return load_manifest(path)

    def _registry(self) -> dict[str, dict[str, Any]]:
        """Return the validated manifest-backed model registry."""
        return {
            name: entry.to_legacy_dict()
            for name, entry in self._manifest.models.items()
        }

    def list_available(self) -> list[str]:
        """List all available model names."""
        return list(self._registry().keys())

    def status(self) -> list[ModelStatus]:
        """Check required files and their declared sizes."""
        results: list[ModelStatus] = []
        for name, entry in self._manifest.models.items():
            model_dir = self.root / entry.subdir
            issues = self._file_issues(name)
            results.append(
                ModelStatus(
                    name=name,
                    installed=not issues,
                    path=model_dir,
                    missing_files=issues,
                )
            )
        return results

    def _file_issues(self, model_name: str) -> list[str]:
        entry = self._manifest.models[model_name]
        model_dir = self.root / entry.subdir
        issues: list[str] = []
        for file in entry.required_files:
            path = model_dir / file.name
            if not path.exists():
                issues.append(file.name)
            elif file.size_bytes > 0 and path.stat().st_size != file.size_bytes:
                issues.append(f"{file.name}（大小不匹配）")
        return issues

    def get_path(self, model_name: str) -> Path:
        """Get the directory path for a specific model."""
        info = self._registry().get(model_name)
        if info is None:
            raise ValueError(f"Unknown model: {model_name}")
        return self.root / info["subdir"]

    def is_available(self, model_name: str) -> bool:
        """Check if a model is installed and complete."""
        if model_name not in self._manifest.models:
            return False
        return not self._file_issues(model_name)

    def get_sha256(self, model_name: str, filename: str) -> str | None:
        """Get SHA256 hash for a model file from the manifest.

        Returns None when the model or file has no hash.
        """
        entry = self._manifest.models.get(model_name)
        if entry is None:
            return None
        for f in entry.required_files:
            if f.name == filename:
                return f.sha256 or None
        return None

    def get_size_bytes(self, model_name: str, filename: str) -> int:
        """Get the declared size of one model file."""
        entry = self._manifest.models.get(model_name)
        if entry is None:
            return 0
        for file in entry.required_files:
            if file.name == filename:
                return file.size_bytes
        return 0


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
        filename = "config.json"
        url = self.build_file_url(source, repo, filename)
        request = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
                return 200 <= response.status < 400
        except Exception:
            return False

    def download(
        self,
        model_name: str,
        source: str = "hf",
        progress=None,
        cancelled=None,
        verified_files: set[str] | None = None,
        max_retries: int = 3,
    ) -> Path:
        """Download model files from source with resume and SHA256 verification.

        Args:
            model_name: Name from MODEL_REGISTRY
            source: Download source (hf, hf-mirror, modelscope)
            progress: Optional callback(filename, downloaded_bytes, total_bytes)
            max_retries: Maximum retry attempts per file (default 3)

        Returns:
            Path to downloaded model directory

        Raises:
            RuntimeError: If SHA256 verification fails after all retries
        """
        registry = ModelRegistry(self.config)
        info = registry._registry().get(model_name)
        if info is None:
            raise ValueError(f"未知模型：{model_name}")
        expected_hashes: dict[str, str] = {}
        for filename in info["required_files"]:
            expected_sha256 = registry.get_sha256(model_name, filename)
            if expected_sha256 is None:
                raise RuntimeError(f"缺少 SHA256，拒绝下载: {model_name}/{filename}")
            expected_hashes[filename] = expected_sha256

        model_dir = self.root / info["subdir"]
        model_dir.mkdir(parents=True, exist_ok=True)
        try:
            for filename in info["required_files"]:
                if cancelled is not None and cancelled():
                    raise DownloadCancelled("模型下载已取消，可稍后继续")
                repo_key = "modelscope_repo" if source == "modelscope" else "hf_repo"
                repo = cast(str, info.get(repo_key) or "")
                if not repo:
                    raise ValueError(
                        f"{model_name} 未配置 {source} / ModelScope 下载仓库，请手动放入 models/"
                    )
                url = self.build_file_url(source, repo, filename)
                dest = model_dir / filename
                expected_sha256 = expected_hashes[filename]
                expected_size = registry.get_size_bytes(model_name, filename)
                if dest.exists():
                    current_size = dest.stat().st_size
                    if filename in (verified_files or set()) and (
                        expected_size <= 0 or current_size == expected_size
                    ):
                        if progress:
                            progress(filename, current_size, current_size)
                        continue
                    complete_size = expected_size <= 0 or current_size == expected_size
                    if complete_size and self._verify_sha256(
                        dest, expected_sha256, cancelled=cancelled
                    ):
                        if progress:
                            progress(filename, current_size, current_size)
                        continue
                    if expected_size > 0 and current_size >= expected_size:
                        logger.warning("删除无法续传的损坏文件: %s", dest)
                        dest.unlink()
                last_error: Exception | None = None
                for attempt in range(1, max_retries + 1):
                    try:
                        self._download_file_with_resume(url, dest, progress=progress)
                    except DownloadCancelled:
                        raise
                    except Exception as exc:
                        last_error = exc
                        logger.warning(
                            "下载 %s 第 %d/%d 次失败: %s",
                            filename,
                            attempt,
                            max_retries,
                            exc,
                        )
                        continue
                    if self._verify_sha256(dest, expected_sha256, cancelled=cancelled):
                        break
                    last_error = ModelIntegrityError(f"SHA256 校验失败: {filename}")
                    logger.warning(
                        "SHA256 校验失败 %s 第 %d/%d 次",
                        filename,
                        attempt,
                        max_retries,
                    )
                    dest.unlink(missing_ok=True)
                    continue
                else:
                    # all retries exhausted
                    raise last_error or RuntimeError(f"下载失败: {filename}")
        except DownloadCancelled:
            logger.info("模型 %s 下载已取消，保留断点文件", model_name)
            raise
        except ModelIntegrityError as exc:
            logger.error(
                "模型 %s 下载内容校验失败，保留其他已校验文件: %s",
                model_name,
                exc,
            )
            raise
        except Exception as exc:
            logger.error("模型 %s 下载失败，保留断点文件: %s", model_name, exc)
            raise
        return model_dir

    def _download_file_with_resume(self, url: str, dest: Path, progress=None) -> None:
        """Download a single file with HTTP Range resume support.

        If dest already exists and is non-empty, sends a Range header to
        resume from where it left off. Server must respond with 206 Partial
        Content for resume to work; otherwise the file is re-downloaded
        from scratch.
        """
        existing_size = dest.stat().st_size if dest.exists() else 0
        headers: dict[str, str] = {}
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"

        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
            status = response.status
            if status == 206 and existing_size > 0:
                # Resume: append to existing file
                total_header = response.getheader("content-range", "")
                match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", total_header)
                if match is None:
                    dest.write_bytes(b"")
                    raise RuntimeError(
                        "服务器返回的续传位置不一致，已清空断点文件以便重新下载"
                    )
                range_start, range_end, total = map(int, match.groups())
                if (
                    range_start != existing_size
                    or range_end < range_start
                    or range_end >= total
                ):
                    dest.write_bytes(b"")
                    raise RuntimeError(
                        "服务器返回的续传位置不一致，已清空断点文件以便重新下载"
                    )
                downloaded = existing_size
                if progress:
                    progress(dest.name, downloaded, total)
                with open(dest, "ab") as f:
                    while downloaded <= range_end:
                        remaining = range_end + 1 - downloaded
                        chunk = response.read(min(8192, remaining))
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            progress(dest.name, downloaded, total)
                if downloaded != range_end + 1 or downloaded != total:
                    raise RuntimeError(
                        "服务器续传响应不完整，已保留有效断点供下次继续下载"
                    )
            else:
                # Fresh download (server returned 200 or no prior file)
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

    def _verify_sha256(
        self, path: Path, expected_sha256: str, *, cancelled=None
    ) -> bool:
        """Verify file integrity by comparing SHA256 hash.

        Computes hash in 8192-byte chunks to avoid loading entire file
        into memory.
        """
        return verify_file_sha256(path, expected_sha256, cancelled=cancelled)

    def _download_file(self, url: str, dest: Path, progress=None) -> None:
        """Download a single file with optional progress callback."""
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

    def verify(
        self, model_name: str, *, require_hash: bool = False, cancelled=None
    ) -> dict:
        """Verify a model's files exist, are non-empty, and optionally match SHA256.

        Returns dict with status and details.
        """
        registry = ModelRegistry(self.config)
        info = registry._registry().get(model_name)
        if info is None:
            return {
                "name": model_name,
                "status": "unknown",
                "error": "Model not in registry",
            }

        model_dir = self.root / info["subdir"]
        results: dict[str, Any] = {"name": model_name, "status": "ok", "files": {}}
        for f in info["required_files"]:
            if cancelled is not None and cancelled():
                raise DownloadCancelled("模型校验已取消，可稍后继续")
            fpath = model_dir / f
            if fpath.exists():
                size = fpath.stat().st_size
                results["files"][f] = {"exists": True, "size": size}
                if size == 0:
                    results["status"] = "corrupt"
                elif require_hash:
                    expected = registry.get_sha256(model_name, f)
                    if expected is None:
                        results["files"][f]["sha256_ok"] = False
                        results["status"] = "unverified"
                    else:
                        matches = verify_file_sha256(
                            fpath, expected, cancelled=cancelled
                        )
                        results["files"][f]["sha256_ok"] = matches
                        if not matches:
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
        registry = ModelRegistry(self.config)
        info = registry._registry().get(model_name)
        if info is None:
            raise ValueError(f"Unknown model: {model_name}")

        model_dir = self.root / info["subdir"]
        if model_dir.exists():
            shutil.rmtree(model_dir)
            return True
        return False
