"""Tests for model management system."""

from __future__ import annotations

from pathlib import Path

import pytest

from subtap.core.models import (
    ModelRegistry,
    ModelDownloader,
    ModelVerifier,
    ModelRemover,
    MODEL_REGISTRY,
)
from subtap.core.manifest import get_manifest_path, load_manifest
from subtap.schemas.config import SubtapConfig


def test_remote_api_config_defaults():
    """Remote API config defaults support optional API backends."""
    from subtap.schemas.config import RemoteAPIConfig

    config = SubtapConfig()

    assert config.mode == "offline"
    assert isinstance(config.remote_api, RemoteAPIConfig)
    assert config.remote_api.provider == "openai-compatible"
    assert config.remote_api.base_url == ""
    assert config.remote_api.api_key_env == "SUBTAP_API_KEY"


def _config_with_model_root(tmp_path: Path) -> SubtapConfig:
    """Config with model root pointing to tmp."""
    from subtap.schemas.config import (
        AudioConfig,
        ASRConfig,
        CleanConfig,
        AlignConfig,
        ModelConfig,
        WorkspaceConfig,
    )

    return SubtapConfig(
        audio=AudioConfig(),
        asr=ASRConfig(),
        clean=CleanConfig(),
        align=AlignConfig(),
        models=ModelConfig(root=str(tmp_path / "models")),
        workspace=WorkspaceConfig(root=str(tmp_path / "work")),
    )


def _create_model_files(model_dir: Path) -> None:
    """Create all required model files for testing."""
    model_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(get_manifest_path(SubtapConfig()))
    for file in manifest.models["asr_0.6b"].required_files:
        with (model_dir / file.name).open("wb") as handle:
            handle.truncate(file.size_bytes)


# ── Registry tests ──


def test_model_registry_has_expected_models():
    """Only the three supported 8-bit MLX models require downloads."""
    assert set(MODEL_REGISTRY) == {"asr_0.6b", "asr_1.7b", "aligner"}
    assert "required_files" in MODEL_REGISTRY["asr_0.6b"]


def test_default_qwen_models_are_complete_8bit_mlx_entries():
    """The shipped Qwen model catalog contains only the supported 8-bit MLX models."""
    config = SubtapConfig()
    manifest = load_manifest(get_manifest_path(config))
    qwen_models = {
        name: entry
        for name, entry in manifest.models.items()
        if "Qwen3" in entry.description
    }

    assert set(qwen_models) == {"asr_0.6b", "asr_1.7b", "aligner"}
    assert all("8bit" in entry.hf_repo.lower() for entry in qwen_models.values())
    assert all(
        file.sha256 and file.size_bytes > 0
        for entry in qwen_models.values()
        for file in entry.required_files
    )


def test_legacy_model_registry_is_derived_from_default_manifest():
    """The compatibility export must exactly match the default manifest."""
    manifest = load_manifest(get_manifest_path(SubtapConfig()))

    assert MODEL_REGISTRY == {
        name: entry.to_legacy_dict() for name, entry in manifest.models.items()
    }


def test_registry_status_all_missing(tmp_path: Path):
    """Status shows all models missing when no files exist."""
    config = _config_with_model_root(tmp_path)
    registry = ModelRegistry(config)
    status = registry.status()
    assert len(status) == 3
    assert all(not ms.installed for ms in status)


def test_registry_status_asr_installed(tmp_path: Path):
    """Status shows asr_0.6b installed when files exist."""
    config = _config_with_model_root(tmp_path)
    registry = ModelRegistry(config)
    asr_dir = registry.get_path("asr_0.6b")
    _create_model_files(asr_dir)

    status = registry.status()
    asr_status = next(s for s in status if s.name == "asr_0.6b")
    assert asr_status.installed


def test_registry_status_rejects_wrong_model_size(tmp_path: Path):
    """A different or truncated quantized model must not be reported as installed."""
    config = _config_with_model_root(tmp_path)
    registry = ModelRegistry(config)
    asr_dir = registry.get_path("asr_0.6b")
    _create_model_files(asr_dir)
    (asr_dir / "model.safetensors").write_bytes(b"wrong model")

    status = registry.status()
    asr_status = next(s for s in status if s.name == "asr_0.6b")

    assert not asr_status.installed
    assert asr_status.missing_files == ["model.safetensors（大小不匹配）"]
    assert not registry.is_available("asr_0.6b")


def test_registry_get_path(tmp_path: Path):
    """get_path returns correct directory."""
    config = _config_with_model_root(tmp_path)
    registry = ModelRegistry(config)
    path = registry.get_path("asr_0.6b")
    assert path.name == "asr_0.6b"
    assert "models" in str(path)


def test_registry_get_path_unknown(tmp_path: Path):
    """get_path raises ValueError for unknown model."""
    config = _config_with_model_root(tmp_path)
    registry = ModelRegistry(config)
    with pytest.raises(ValueError, match="Unknown model"):
        registry.get_path("nonexistent")


def test_registry_is_available_false(tmp_path: Path):
    """is_available returns False when files missing."""
    config = _config_with_model_root(tmp_path)
    registry = ModelRegistry(config)
    assert not registry.is_available("asr_0.6b")


def test_registry_is_available_true(tmp_path: Path):
    """is_available returns True when all files present."""
    config = _config_with_model_root(tmp_path)
    registry = ModelRegistry(config)
    asr_dir = registry.get_path("asr_0.6b")
    _create_model_files(asr_dir)

    assert registry.is_available("asr_0.6b")


# ── Downloader tests ──


def test_downloader_download_calls_urlopen(tmp_path: Path, monkeypatch):
    """Downloader calls urlopen for each file."""
    from unittest.mock import MagicMock

    config = _config_with_model_root(tmp_path)
    downloader = ModelDownloader(config)

    call_count = 0

    def mock_urlopen(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.getheader = lambda name, default=None: (
            "10" if name.lower() == "content-length" else default
        )
        # 第一次 read 返回数据，第二次返回空字节结束循环
        read_count = [0]

        def mock_read(size=-1):
            read_count[0] += 1
            return b"x" * 10 if read_count[0] == 1 else b""

        mock_response.read = mock_read
        return mock_response

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    monkeypatch.setattr(
        "subtap.core.models.ModelRegistry.get_sha256", lambda *args: "0" * 64
    )
    monkeypatch.setattr(ModelDownloader, "_verify_sha256", lambda *args: True)
    result = downloader.download("asr_0.6b")
    assert result.name == "asr_0.6b"
    assert call_count == 5  # config.json + model.safetensors + tokenizer files


def test_downloader_unknown_model(tmp_path: Path):
    """Downloader raises ValueError for unknown model."""
    config = _config_with_model_root(tmp_path)
    downloader = ModelDownloader(config)
    with pytest.raises(ValueError, match="未知模型"):
        downloader.download("nonexistent")


def test_download_cleans_up_on_failure(tmp_path: Path, monkeypatch):
    """Download removes model dir when a file download fails mid-way."""
    from unittest.mock import MagicMock
    import urllib.error

    config = _config_with_model_root(tmp_path)
    downloader = ModelDownloader(config)

    call_count = 0

    def mock_urlopen(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # 第一个文件下载成功
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.getheader = lambda name, default=None: (
                "10" if name.lower() == "content-length" else default
            )
            read_count = [0]

            def mock_read(size=-1):
                read_count[0] += 1
                return b"x" * 10 if read_count[0] == 1 else b""

            mock_response.read = mock_read
            return mock_response
        # 第二个文件下载失败
        raise urllib.error.URLError("connection reset")

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    monkeypatch.setattr(
        "subtap.core.models.ModelRegistry.get_sha256", lambda *args: "0" * 64
    )
    monkeypatch.setattr(ModelDownloader, "_verify_sha256", lambda *args: True)

    model_dir = tmp_path / "models" / "asr_0.6b"
    with pytest.raises(urllib.error.URLError):
        downloader.download("asr_0.6b")

    assert not model_dir.exists(), "失败后应清理残留的模型目录"


# ── Verifier tests ──


def test_verifier_missing(tmp_path: Path):
    """Verifier reports missing when no files."""
    config = _config_with_model_root(tmp_path)
    verifier = ModelVerifier(config)
    result = verifier.verify("asr_0.6b")
    assert result["status"] == "missing"


def test_verifier_ok(tmp_path: Path):
    """Verifier reports ok when files present."""
    config = _config_with_model_root(tmp_path)
    asr_dir = Path(config.models.root).expanduser() / "asr_0.6b"
    _create_model_files(asr_dir)

    verifier = ModelVerifier(config)
    result = verifier.verify("asr_0.6b")
    assert result["status"] == "ok"


def test_verifier_corrupt(tmp_path: Path):
    """Verifier reports corrupt when file is empty."""
    config = _config_with_model_root(tmp_path)
    asr_dir = Path(config.models.root).expanduser() / "asr_0.6b"
    _create_model_files(asr_dir)
    (asr_dir / "model.safetensors").write_bytes(b"")  # overwrite with empty

    verifier = ModelVerifier(config)
    result = verifier.verify("asr_0.6b")
    assert result["status"] == "corrupt"


def test_verifier_strict_rejects_sha256_mismatch(tmp_path: Path):
    """Strict verification rejects a non-empty file with the wrong content."""
    import hashlib

    config = _config_with_model_root(tmp_path)
    manifest = tmp_path / "manifest.yaml"
    expected = hashlib.sha256(b"expected").hexdigest()
    manifest.write_text(f"""version: '1'
models:
  test:
    description: test
    subdir: test
    required_files:
      - name: model.bin
        sha256: {expected}
""")
    config.models.manifest_path = str(manifest)
    model_dir = Path(config.models.root) / "test"
    model_dir.mkdir(parents=True)
    (model_dir / "model.bin").write_bytes(b"wrong")

    assert (
        ModelVerifier(config).verify("test", require_hash=True)["status"] == "corrupt"
    )


def test_verifier_unknown_model(tmp_path: Path):
    """Verifier returns unknown for unregistered model."""
    config = _config_with_model_root(tmp_path)
    verifier = ModelVerifier(config)
    result = verifier.verify("nonexistent")
    assert result["status"] == "unknown"


# ── CLI models tests ──


def test_cli_models_status(tmp_path: Path, monkeypatch):
    """CLI models status runs without crash."""
    from typer.testing import CliRunner
    from subtap.cli import app

    config = _config_with_model_root(tmp_path)
    import subtap.schemas.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_config", lambda p: config)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    runner = CliRunner()
    result = runner.invoke(app, ["models", "status"])
    assert result.exit_code == 0
    assert "asr_0.6b" in result.output


def test_cli_models_verify(tmp_path: Path, monkeypatch):
    """CLI models verify runs without crash."""
    from typer.testing import CliRunner
    from subtap.cli import app

    config = _config_with_model_root(tmp_path)
    import subtap.schemas.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_config", lambda p: config)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    runner = CliRunner()
    result = runner.invoke(app, ["models", "verify"])
    assert result.exit_code == 0
    assert "asr_0.6b" in result.output


def test_cli_models_install_shows_path(tmp_path: Path, monkeypatch):
    """CLI models install shows expected file location."""
    from typer.testing import CliRunner
    from subtap.cli import app
    from unittest.mock import MagicMock

    config = _config_with_model_root(tmp_path)
    import subtap.schemas.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_config", lambda p: config)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    def mock_urlopen(*args, **kwargs):
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.getheader = lambda name, default=None: (
            "10" if name.lower() == "content-length" else default
        )
        read_count = [0]

        def mock_read(size=-1):
            read_count[0] += 1
            return b"x" * 10 if read_count[0] == 1 else b""

        mock_response.read = mock_read
        return mock_response

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    monkeypatch.setattr(
        "subtap.core.models.ModelRegistry.get_sha256", lambda *args: "0" * 64
    )
    monkeypatch.setattr(ModelDownloader, "_verify_sha256", lambda *args: True)
    runner = CliRunner()
    result = runner.invoke(app, ["models", "install", "asr_0.6b"])
    assert result.exit_code == 0
    assert "asr_0.6b" in result.output


# ── List and Remove tests ──


def test_model_registry_list(tmp_path: Path):
    """Test listing available models."""
    config = _config_with_model_root(tmp_path)
    registry = ModelRegistry(config)
    models = registry.list_available()
    assert set(models) == {"asr_0.6b", "asr_1.7b", "aligner"}


def test_model_remover_removes(tmp_path: Path):
    """Test model removal."""
    config = _config_with_model_root(tmp_path)
    remover = ModelRemover(config)

    # Create fake model directory
    model_dir = tmp_path / "models" / "asr_0.6b"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}")

    result = remover.remove("asr_0.6b")
    assert result is True
    assert not model_dir.exists()


def test_model_remover_not_exists(tmp_path: Path):
    """Test removing non-existent model directory returns False."""
    config = _config_with_model_root(tmp_path)
    remover = ModelRemover(config)

    # Don't create model directory
    result = remover.remove("asr_0.6b")
    assert result is False


def test_model_remover_unknown_model(tmp_path: Path):
    """Test removing unknown model raises ValueError."""
    config = _config_with_model_root(tmp_path)
    remover = ModelRemover(config)

    with pytest.raises(ValueError, match="Unknown model"):
        remover.remove("nonexistent_model")


def test_cli_models_list(tmp_path: Path, monkeypatch):
    """Test CLI models list command."""
    from typer.testing import CliRunner
    from subtap.cli import app

    config = _config_with_model_root(tmp_path)
    import subtap.schemas.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_config", lambda p: config)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    runner = CliRunner()
    result = runner.invoke(app, ["models", "list"])
    assert result.exit_code == 0
    assert "可用模型" in result.output
    assert "asr_0.6b" in result.output
    assert "aligner" in result.output


def test_cli_models_remove(tmp_path: Path, monkeypatch):
    """Test CLI models remove command."""
    from typer.testing import CliRunner
    from subtap.cli import app
    from unittest.mock import patch

    config = _config_with_model_root(tmp_path)
    import subtap.schemas.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_config", lambda p: config)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    runner = CliRunner()
    with patch("subtap.core.models.ModelRemover.remove") as mock_remove:
        mock_remove.return_value = True
        result = runner.invoke(app, ["models", "remove", "asr_0.6b"])
        assert result.exit_code == 0
        assert "已移除" in result.output


# ── Downloader URL and connectivity tests ──


def test_downloader_builds_hf_file_url(tmp_path):
    from subtap.core.models import ModelDownloader

    cfg = _config_with_model_root(tmp_path)
    downloader = ModelDownloader(cfg)

    url = downloader.build_file_url(
        source="hf",
        repo="owner/model",
        filename="config.json",
    )

    assert url == "https://huggingface.co/owner/model/resolve/main/config.json"


def test_downloader_builds_hf_mirror_file_url(tmp_path):
    from subtap.core.models import ModelDownloader

    cfg = _config_with_model_root(tmp_path)
    cfg.models.hf_mirror_endpoint = "https://hf-mirror.com"
    downloader = ModelDownloader(cfg)

    url = downloader.build_file_url(
        source="hf-mirror",
        repo="owner/model",
        filename="model.safetensors",
    )

    assert url == "https://hf-mirror.com/owner/model/resolve/main/model.safetensors"


def test_registry_has_modelscope_repos():
    """Development registry should include ModelScope repos for all installable models."""
    from subtap.core.models import MODEL_REGISTRY

    assert all(info["modelscope_repo"] for info in MODEL_REGISTRY.values())


def test_downloader_builds_modelscope_file_url(tmp_path):
    from subtap.core.models import ModelDownloader

    cfg = _config_with_model_root(tmp_path)
    downloader = ModelDownloader(cfg)

    url = downloader.build_file_url(
        source="modelscope",
        repo="owner/model",
        filename="config.json",
    )

    assert url == "https://modelscope.cn/models/owner/model/resolve/master/config.json"


# ── check_connectivity tests ──


def test_check_connectivity_returns_true_on_200(tmp_path, monkeypatch):
    """check_connectivity returns True when HEAD request succeeds."""
    from unittest.mock import MagicMock

    cfg = _config_with_model_root(tmp_path)
    downloader = ModelDownloader(cfg)

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: mock_response)

    assert downloader.check_connectivity("hf", "owner/model") is True


def test_check_connectivity_returns_false_on_timeout(tmp_path, monkeypatch):
    """check_connectivity returns False when request times out."""
    import urllib.error

    cfg = _config_with_model_root(tmp_path)
    downloader = ModelDownloader(cfg)

    def raise_timeout(*args, **kwargs):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", raise_timeout)

    assert downloader.check_connectivity("hf", "owner/model") is False


def test_check_connectivity_returns_false_on_http_error(tmp_path, monkeypatch):
    """check_connectivity returns False when server returns HTTP error."""
    import urllib.error

    cfg = _config_with_model_root(tmp_path)
    downloader = ModelDownloader(cfg)

    def raise_http_error(*args, **kwargs):
        raise urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", raise_http_error)

    assert downloader.check_connectivity("hf", "owner/model") is False


def test_download_file_reports_progress(tmp_path, monkeypatch):
    from io import BytesIO
    from subtap.core.models import ModelDownloader

    class FakeResponse:
        status = 200

        def __init__(self):
            self.fp = BytesIO(b"abc")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def getheader(self, name, default=None):
            return "3" if name.lower() == "content-length" else default

        def read(self, size=-1):
            return self.fp.read(size)

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse())
    cfg = _config_with_model_root(tmp_path)
    downloader = ModelDownloader(cfg)
    seen = []

    downloader._download_file(
        "https://example.test/file",
        tmp_path / "file",
        progress=lambda name, done, total: seen.append((done, total)),
    )

    assert (tmp_path / "file").read_bytes() == b"abc"
    assert seen[0] == (0, 3)
    assert seen[-1] == (3, 3)


# ── Development model path tests ──


def test_default_model_root_is_project_models():
    """Default model root should be user-level models directory for packaged installs."""
    from subtap.schemas.config import SubtapConfig
    from subtap.core.models import _get_model_root

    root = _get_model_root(SubtapConfig())

    assert root.name == "models"
    assert root.parent == Path.home() / ".subtap"


def test_registry_uses_development_model_names():
    """Registry should use development model names with version suffixes."""
    from subtap.core.models import MODEL_REGISTRY

    assert MODEL_REGISTRY["asr_0.6b"]["subdir"] == "asr_0.6b"
    assert MODEL_REGISTRY["asr_1.7b"]["subdir"] == "asr_1.7b"
    assert MODEL_REGISTRY["aligner"]["subdir"] == "aligner"
