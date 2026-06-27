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
from subtap.schemas.config import SubtapConfig


def _config_with_model_root(tmp_path: Path) -> SubtapConfig:
    """Config with model root pointing to tmp."""
    from subtap.schemas.config import AudioConfig, ASRConfig, CleanConfig, AlignConfig, ModelConfig, WorkspaceConfig
    return SubtapConfig(
        audio=AudioConfig(),
        asr=ASRConfig(),
        clean=CleanConfig(),
        align=AlignConfig(),
        models=ModelConfig(root=str(tmp_path / "models")),
        workspace=WorkspaceConfig(root=str(tmp_path / "work")),
    )


# ── Registry tests ──

def test_model_registry_has_expected_models():
    """MODEL_REGISTRY contains asr_0.6b, asr_1.7b and aligner."""
    assert "asr_0.6b" in MODEL_REGISTRY
    assert "asr_1.7b" in MODEL_REGISTRY
    assert "aligner" in MODEL_REGISTRY
    assert "required_files" in MODEL_REGISTRY["asr_0.6b"]


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
    asr_dir.mkdir(parents=True)
    (asr_dir / "config.json").write_text("{}")
    (asr_dir / "model.safetensors").write_bytes(b"\x00" * 100)

    status = registry.status()
    asr_status = next(s for s in status if s.name == "asr_0.6b")
    assert asr_status.installed


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
    try:
        registry.get_path("nonexistent")
        assert False
    except ValueError:
        pass


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
    asr_dir.mkdir(parents=True)
    (asr_dir / "config.json").write_text("{}")
    (asr_dir / "model.safetensors").write_bytes(b"\x00" * 100)

    assert registry.is_available("asr_0.6b")


# ── Downloader tests ──

def test_downloader_download_exists(tmp_path: Path):
    """Downloader returns path when model already present."""
    config = _config_with_model_root(tmp_path)
    asr_dir = Path(config.models.root).expanduser() / "asr_0.6b"
    asr_dir.mkdir(parents=True)
    (asr_dir / "config.json").write_text("{}")
    (asr_dir / "model.safetensors").write_bytes(b"\x00" * 100)

    downloader = ModelDownloader(config)
    result = downloader.download("asr_0.6b")
    assert result == asr_dir


def test_downloader_download_not_implemented(tmp_path: Path):
    """Downloader raises NotImplementedError for missing models."""
    config = _config_with_model_root(tmp_path)
    downloader = ModelDownloader(config)
    try:
        downloader.download("asr_0.6b")
        assert False
    except NotImplementedError as e:
        assert "place model files" in str(e)


def test_downloader_unknown_model(tmp_path: Path):
    """Downloader raises ValueError for unknown model."""
    config = _config_with_model_root(tmp_path)
    downloader = ModelDownloader(config)
    try:
        downloader.download("nonexistent")
        assert False
    except ValueError:
        pass


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
    asr_dir.mkdir(parents=True)
    (asr_dir / "config.json").write_text("{}")
    (asr_dir / "model.safetensors").write_bytes(b"\x00" * 100)

    verifier = ModelVerifier(config)
    result = verifier.verify("asr_0.6b")
    assert result["status"] == "ok"


def test_verifier_corrupt(tmp_path: Path):
    """Verifier reports corrupt when file is empty."""
    config = _config_with_model_root(tmp_path)
    asr_dir = Path(config.models.root).expanduser() / "asr_0.6b"
    asr_dir.mkdir(parents=True)
    (asr_dir / "config.json").write_text("{}")
    (asr_dir / "model.safetensors").write_bytes(b"")  # empty

    verifier = ModelVerifier(config)
    result = verifier.verify("asr_0.6b")
    assert result["status"] == "corrupt"


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

    config = _config_with_model_root(tmp_path)
    import subtap.schemas.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "load_config", lambda p: config)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

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
    assert "asr_0.6b" in models
    assert "asr_1.7b" in models
    assert "aligner" in models


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


# ── Development model path tests ──

def test_default_model_root_is_project_models():
    """Default model root should be project-level models/ directory."""
    from subtap.schemas.config import SubtapConfig
    from subtap.core.models import _get_model_root

    root = _get_model_root(SubtapConfig())

    assert root.name == "models"
    assert root.parent == Path(__file__).resolve().parent.parent


def test_registry_uses_development_model_names():
    """Registry should use development model names with version suffixes."""
    from subtap.core.models import MODEL_REGISTRY

    assert MODEL_REGISTRY["asr_0.6b"]["subdir"] == "asr_0.6b"
    assert MODEL_REGISTRY["asr_1.7b"]["subdir"] == "asr_1.7b"
    assert MODEL_REGISTRY["aligner"]["subdir"] == "aligner"
