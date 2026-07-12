"""Model download recovery tests — calls actual ModelDownloader production code."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from subtap.core.models import ModelDownloader, MODEL_REGISTRY


def _make_downloader(tmp_path: Path) -> ModelDownloader:
    """Create a ModelDownloader with a temporary model root."""
    config = MagicMock()
    config.models.root = str(tmp_path / "models")
    config.models.hf_endpoint = "https://huggingface.co"
    config.models.hf_mirror_endpoint = "https://hf-mirror.com"
    downloader = ModelDownloader(config)
    return downloader


def _make_http_response(data: bytes, status: int = 200, headers: dict | None = None):
    """Build a fake urllib response object that works as a context manager."""
    resp = MagicMock()
    resp.status = status
    resp.read = io.BytesIO(data).read
    hdrs = {"content-length": str(len(data)), **(headers or {})}
    resp.getheader = lambda name, default="": hdrs.get(name.lower(), default)
    # Make `with urlopen(...) as r:` yield our configured mock, not a child MagicMock
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# --- _verify_sha256: calls real production code ---


def test_verify_sha256_correct_hash(tmp_path):
    """SHA256 校验通过：正确 hash 返回 True。"""
    downloader = _make_downloader(tmp_path)
    content = b"hello world"
    expected = hashlib.sha256(content).hexdigest()

    target = tmp_path / "test.bin"
    target.write_bytes(content)

    assert downloader._verify_sha256(target, expected) is True


def test_verify_sha256_wrong_hash(tmp_path):
    """SHA256 校验失败：错误 hash 返回 False。"""
    downloader = _make_downloader(tmp_path)
    target = tmp_path / "test.bin"
    target.write_bytes(b"hello world")

    assert downloader._verify_sha256(target, "0" * 64) is False


# --- _download_file_with_resume: mocks urllib, calls production code ---


def test_resume_appends_to_partial_file(tmp_path):
    """断点续传：已有部分文件时，发送 Range 请求并追加数据。"""
    downloader = _make_downloader(tmp_path)
    partial_data = b"A" * 500
    remaining_data = b"B" * 500
    total_data = partial_data + remaining_data

    dest = tmp_path / "model.bin"
    dest.write_bytes(partial_data)

    response = _make_http_response(
        remaining_data,
        status=206,
        headers={"content-range": f"bytes 500-999/1000"},
    )

    with patch("subtap.core.models.urllib.request.urlopen", return_value=response):
        downloader._download_file_with_resume("https://example.com/model.bin", dest)

    assert dest.read_bytes() == total_data


def test_resume_sends_range_header(tmp_path):
    """断点续传：请求头包含 Range 字段。"""
    downloader = _make_downloader(tmp_path)
    dest = tmp_path / "model.bin"
    dest.write_bytes(b"X" * 100)

    response = _make_http_response(b"Y" * 50, status=206)

    with patch(
        "subtap.core.models.urllib.request.urlopen", return_value=response
    ) as mock_urlopen:
        downloader._download_file_with_resume("https://example.com/f", dest)

    call_args = mock_urlopen.call_args
    request = call_args[0][0]
    assert request.get_header("Range") == "bytes=100-"


def test_fresh_download_when_server_returns_200(tmp_path):
    """服务器返回 200 时重新下载整个文件（忽略已有内容）。"""
    downloader = _make_downloader(tmp_path)
    full_data = b"FRESH" * 200

    dest = tmp_path / "model.bin"
    dest.write_bytes(b"old data that will be overwritten")

    response = _make_http_response(full_data, status=200)

    with patch("subtap.core.models.urllib.request.urlopen", return_value=response):
        downloader._download_file_with_resume("https://example.com/f", dest)

    assert dest.read_bytes() == full_data


# --- download: full orchestration with retry ---


def test_download_sha256_mismatch_triggers_retry(tmp_path):
    """SHA256 校验失败时自动重试，最终抛出 RuntimeError。"""
    downloader = _make_downloader(tmp_path)
    bad_content = b"corrupt data"
    correct_hash = hashlib.sha256(b"correct data").hexdigest()

    model_name = "asr_0.6b"
    info = MODEL_REGISTRY[model_name]

    # Mock get_sha256 to return a hash that won't match bad_content
    with (
        patch.object(downloader, "_download_file_with_resume"),
        patch("subtap.core.models.ModelRegistry") as MockRegistry,
    ):
        mock_reg_instance = MockRegistry.return_value
        mock_reg_instance.get_sha256.return_value = correct_hash

        # Make dest file exist with bad content after each "download"
        def fake_download(url, dest, progress=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(bad_content)

        downloader._download_file_with_resume.side_effect = fake_download

        with pytest.raises(RuntimeError, match="SHA256"):
            downloader.download(model_name, max_retries=2)

        assert mock_reg_instance.get_sha256.call_count == len(info["required_files"])


def test_download_cleans_model_dir_on_failure(tmp_path):
    """下载失败后清理 model_dir（生产代码行为：shutil.rmtree）。"""
    downloader = _make_downloader(tmp_path)
    model_name = "asr_0.6b"
    info = MODEL_REGISTRY[model_name]
    model_dir = downloader.root / info["subdir"]

    with (
        patch.object(
            downloader, "_download_file_with_resume", side_effect=IOError("网络错误")
        ),
        patch("subtap.core.models.ModelRegistry") as MockRegistry,
    ):
        MockRegistry.return_value.get_sha256.return_value = "0" * 64
        with pytest.raises(IOError, match="网络错误"):
            downloader.download(model_name, max_retries=1)

    assert not model_dir.exists()


def test_download_success_returns_model_dir(tmp_path):
    """下载成功后返回 model_dir 路径。"""
    downloader = _make_downloader(tmp_path)
    model_name = "asr_0.6b"
    info = MODEL_REGISTRY[model_name]
    expected_dir = downloader.root / info["subdir"]

    file_content = b"model weights"

    with (
        patch.object(downloader, "_download_file_with_resume") as mock_dl,
        patch("subtap.core.models.ModelRegistry") as MockRegistry,
    ):
        MockRegistry.return_value.get_sha256.return_value = hashlib.sha256(
            file_content
        ).hexdigest()

        def fake_download(url, dest, progress=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(file_content)

        mock_dl.side_effect = fake_download

        result = downloader.download(model_name, max_retries=1)

    assert result == expected_dir
    assert expected_dir.exists()
