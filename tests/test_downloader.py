"""Tests for ModelDownloader: resume, SHA256, retries."""

import hashlib

import pytest

from subtap.core.models import DownloadCancelled, ModelDownloader
from subtap.schemas.config import SubtapConfig


def test_verify_sha256_passes_for_correct_hash(tmp_path):
    config = SubtapConfig()
    downloader = ModelDownloader(config)
    content = b"test content"
    expected = hashlib.sha256(content).hexdigest()
    fpath = tmp_path / "test.bin"
    fpath.write_bytes(content)
    assert downloader._verify_sha256(fpath, expected) is True


def test_verify_sha256_fails_for_wrong_hash(tmp_path):
    config = SubtapConfig()
    downloader = ModelDownloader(config)
    fpath = tmp_path / "test.bin"
    fpath.write_bytes(b"test content")
    assert downloader._verify_sha256(fpath, "wrong_hash") is False


def test_verify_sha256_can_be_cancelled(tmp_path):
    config = SubtapConfig()
    downloader = ModelDownloader(config)
    fpath = tmp_path / "test.bin"
    fpath.write_bytes(b"x" * (2 * 1024 * 1024))

    with pytest.raises(DownloadCancelled, match="校验已取消"):
        downloader._verify_sha256(fpath, "wrong_hash", cancelled=lambda: True)


def test_download_cleans_up_corrupt_file_on_sha256_mismatch(tmp_path, monkeypatch):
    config = SubtapConfig()
    config.models.root = str(tmp_path / "models")
    downloader = ModelDownloader(config)

    def fake_download(url, dest, progress=None):
        dest.write_bytes(b"wrong content")

    monkeypatch.setattr(downloader, "_download_file_with_resume", fake_download)
    monkeypatch.setattr(downloader, "_verify_sha256", lambda *a, **kwargs: False)
    # Patch ModelRegistry.get_sha256 so SHA256 verification path is triggered
    from subtap.core.models import ModelRegistry

    monkeypatch.setattr(ModelRegistry, "get_sha256", lambda self, mn, fn: "fake_sha256")
    with pytest.raises(RuntimeError, match="SHA256"):
        downloader.download("asr_0.6b", source="hf")
    model_dir = tmp_path / "models" / "asr_0.6b"
    assert model_dir.exists()
    assert not any(model_dir.iterdir())
