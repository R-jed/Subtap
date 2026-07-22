"""Model download recovery tests — calls actual ModelDownloader production code."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from subtap.core.models import ModelDownloader, MODEL_REGISTRY
from subtap.schemas.config import SubtapConfig


def _make_downloader(tmp_path: Path) -> ModelDownloader:
    """Create a ModelDownloader with a temporary model root."""
    config = SubtapConfig()
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
        headers={"content-range": "bytes 500-999/1000"},
    )

    with patch("subtap.core.models.urllib.request.urlopen", return_value=response):
        downloader._download_file_with_resume("https://example.com/model.bin", dest)

    assert dest.read_bytes() == total_data


def test_resume_sends_range_header(tmp_path):
    """断点续传：请求头包含 Range 字段。"""
    downloader = _make_downloader(tmp_path)
    dest = tmp_path / "model.bin"
    dest.write_bytes(b"X" * 100)

    response = _make_http_response(
        b"Y" * 50,
        status=206,
        headers={"content-range": "bytes 100-149/150"},
    )

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


def test_resume_rejects_wrong_content_range_before_appending(tmp_path):
    """服务器返回错误续传位置时必须拒绝拼接损坏文件。"""
    downloader = _make_downloader(tmp_path)
    dest = tmp_path / "model.bin"
    dest.write_bytes(b"A" * 500)
    response = _make_http_response(
        b"B" * 500,
        status=206,
        headers={"content-range": "bytes 0-499/1000"},
    )

    with (
        patch("subtap.core.models.urllib.request.urlopen", return_value=response),
        pytest.raises(RuntimeError, match="续传位置不一致"),
    ):
        downloader._download_file_with_resume("https://example.com/f", dest)

    assert dest.read_bytes() == b""


def test_resume_rejects_truncated_partial_response(tmp_path):
    """续传响应提前结束时必须失败，且保留已收到内容供下次续传。"""
    downloader = _make_downloader(tmp_path)
    dest = tmp_path / "model.bin"
    dest.write_bytes(b"A" * 500)
    response = _make_http_response(
        b"B" * 100,
        status=206,
        headers={"content-range": "bytes 500-999/1000"},
    )

    with (
        patch("subtap.core.models.urllib.request.urlopen", return_value=response),
        pytest.raises(RuntimeError, match="续传响应不完整"),
    ):
        downloader._download_file_with_resume("https://example.com/f", dest)

    assert dest.stat().st_size == 600


def test_resume_never_writes_beyond_declared_range(tmp_path):
    """续传层不得把服务端越界返回的字节写入模型文件。"""
    downloader = _make_downloader(tmp_path)
    dest = tmp_path / "model.bin"
    dest.write_bytes(b"A" * 500)
    response = _make_http_response(
        b"B" * 600,
        status=206,
        headers={"content-range": "bytes 500-999/1000"},
    )

    with patch("subtap.core.models.urllib.request.urlopen", return_value=response):
        downloader._download_file_with_resume("https://example.com/f", dest)

    assert dest.stat().st_size == 1000


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
        patch(
            "subtap.core.models.ModelRegistry.get_sha256",
            return_value=correct_hash,
        ) as mock_get_sha256,
    ):
        # Make dest file exist with bad content after each "download"
        def fake_download(url, dest, progress=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(bad_content)

        downloader._download_file_with_resume.side_effect = fake_download

        with pytest.raises(RuntimeError, match="SHA256"):
            downloader.download(model_name, max_retries=2)

        assert mock_get_sha256.call_count == len(info["required_files"])


def test_download_preserves_partial_model_dir_for_resume(tmp_path):
    """网络失败后保留已下载内容，让下一次下载可以断点续传。"""
    downloader = _make_downloader(tmp_path)
    model_name = "asr_0.6b"
    info = MODEL_REGISTRY[model_name]
    model_dir = downloader.root / info["subdir"]

    with (
        patch.object(
            downloader, "_download_file_with_resume", side_effect=IOError("网络错误")
        ),
        patch("subtap.core.models.ModelRegistry.get_sha256", return_value="0" * 64),
    ):
        with pytest.raises(IOError, match="网络错误"):
            downloader.download(model_name, max_retries=1)

    assert model_dir.exists()


def test_download_success_returns_model_dir(tmp_path):
    """下载成功后返回 model_dir 路径。"""
    downloader = _make_downloader(tmp_path)
    model_name = "asr_0.6b"
    info = MODEL_REGISTRY[model_name]
    expected_dir = downloader.root / info["subdir"]

    file_content = b"model weights"

    with (
        patch.object(downloader, "_download_file_with_resume") as mock_dl,
        patch(
            "subtap.core.models.ModelRegistry.get_sha256",
            return_value=hashlib.sha256(file_content).hexdigest(),
        ),
    ):

        def fake_download(url, dest, progress=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(file_content)

        mock_dl.side_effect = fake_download

        result = downloader.download(model_name, max_retries=1)

    assert result == expected_dir
    assert expected_dir.exists()


def test_download_retry_skips_files_that_already_match_hash(tmp_path):
    """重试部分模型时不再次请求已完成并通过哈希的文件。"""
    downloader = _make_downloader(tmp_path)
    model_name = "asr_0.6b"
    info = MODEL_REGISTRY[model_name]
    model_dir = downloader.root / info["subdir"]
    model_dir.mkdir(parents=True)
    completed = model_dir / info["required_files"][0]
    completed.write_bytes(b"complete")
    requested = []

    def fake_download(url, dest, progress=None):
        requested.append(dest.name)
        dest.write_bytes(b"downloaded")

    with (
        patch.object(
            downloader, "_download_file_with_resume", side_effect=fake_download
        ),
        patch("subtap.core.models.ModelRegistry.get_sha256", return_value="expected"),
        patch("subtap.core.models.ModelRegistry.get_size_bytes", return_value=0),
        patch.object(
            downloader,
            "_verify_sha256",
            side_effect=lambda path, expected, **kwargs: path.exists(),
        ),
    ):
        downloader.download(model_name, max_retries=1)

    assert completed.name not in requested


def test_hash_failure_preserves_other_verified_files(tmp_path):
    """单个文件损坏时，只删除坏文件，不破坏已完成文件。"""
    downloader = _make_downloader(tmp_path)
    model_name = "asr_0.6b"
    info = MODEL_REGISTRY[model_name]
    model_dir = downloader.root / info["subdir"]
    model_dir.mkdir(parents=True)
    completed = model_dir / info["required_files"][0]
    damaged = model_dir / info["required_files"][1]
    completed.write_bytes(b"verified")

    def fake_download(url, dest, progress=None):
        dest.write_bytes(b"corrupt")

    def fake_verify(path, expected, *, cancelled=None):
        return path == completed and path.read_bytes() == b"verified"

    with (
        patch.object(
            downloader, "_download_file_with_resume", side_effect=fake_download
        ),
        patch("subtap.core.models.ModelRegistry.get_sha256", return_value="expected"),
        patch("subtap.core.models.ModelRegistry.get_size_bytes", return_value=0),
        patch.object(downloader, "_verify_sha256", side_effect=fake_verify),
    ):
        with pytest.raises(RuntimeError, match="SHA256"):
            downloader.download(model_name, max_retries=1)

    assert completed.read_bytes() == b"verified"
    assert not damaged.exists()


def test_full_size_corrupt_file_is_replaced_instead_of_resumed(tmp_path):
    """完整大小但哈希错误的文件必须删掉重下，不能从 EOF 续传。"""
    correct = b"good"
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(f"""version: '1'
models:
  test:
    description: test
    subdir: test
    hf_repo: owner/repo
    required_files:
      - name: model.bin
        size_bytes: {len(correct)}
        sha256: {hashlib.sha256(correct).hexdigest()}
""")
    config = SubtapConfig()
    config.models.root = str(tmp_path / "models")
    config.models.manifest_path = str(manifest)
    downloader = ModelDownloader(config)
    dest = tmp_path / "models" / "test" / "model.bin"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"baad")

    def fresh_download(url, path, progress=None):
        assert not path.exists()
        path.write_bytes(correct)

    with patch.object(
        downloader, "_download_file_with_resume", side_effect=fresh_download
    ):
        downloader.download("test", max_retries=1)

    assert dest.read_bytes() == correct


def test_download_reuses_hash_result_from_current_setup_scan(tmp_path):
    """同一次首次安装扫描已验证的文件，不应在下载阶段重复哈希。"""
    content = b"good"
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(f"""version: '1'
models:
  test:
    description: test
    subdir: test
    hf_repo: owner/repo
    required_files:
      - name: model.bin
        size_bytes: {len(content)}
        sha256: {hashlib.sha256(content).hexdigest()}
""")
    config = SubtapConfig()
    config.models.root = str(tmp_path / "models")
    config.models.manifest_path = str(manifest)
    downloader = ModelDownloader(config)
    dest = tmp_path / "models" / "test" / "model.bin"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(content)

    with (
        patch.object(
            downloader,
            "_verify_sha256",
            side_effect=AssertionError("不应重复哈希"),
        ),
        patch.object(
            downloader,
            "_download_file_with_resume",
            side_effect=AssertionError("不应重复下载"),
        ),
    ):
        downloader.download("test", verified_files={"model.bin"})

    assert dest.read_bytes() == content
