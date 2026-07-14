"""Tests for remote ASR / LLM API configuration."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

import subtap.backends.asr.http_asr as http_asr
from subtap.backends.asr.http_asr import HttpASRBackend
from subtap.backends.llm import get_llm_backend
from subtap.backends.llm.openai_compat import OpenAICompatibleLLM
from subtap.schemas.config import ASRConfig, CleanConfig, RemoteAPIConfig
from subtap.schemas.models import Chunk, RawCleanSegment


class _Response:
    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._data


def test_http_asr_uses_remote_api_config(tmp_path: Path, monkeypatch):
    """HTTP ASR posts chunks to the configured OpenAI-compatible endpoint."""
    calls: list[dict] = []

    class Client:
        def __init__(self, timeout: int):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url: str, **kwargs):
            calls.append({"url": url, "timeout": self.timeout, **kwargs})
            return _Response({"text": "远程转录文本"})

    monkeypatch.setenv("SUBTAP_TEST_API_KEY", "test-key")
    monkeypatch.setattr(
        http_asr, "httpx", SimpleNamespace(Client=Client), raising=False
    )

    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFF")
    remote = RemoteAPIConfig(
        base_url="https://api.example.test/v1",
        api_key_env="SUBTAP_TEST_API_KEY",
        model="asr-test",
        timeout_sec=7,
    )
    backend = HttpASRBackend(ASRConfig(backend="http-asr"), remote)

    result = backend.transcribe(
        [Chunk(chunk_id=3, start_sec=1.0, end_sec=2.0, path=str(audio))],
        language="zh",
        hotwords=["Subtap"],
    )

    assert result[0].text == "远程转录文本"
    assert result[0].chunk_id == 3
    assert calls[0]["url"] == "https://api.example.test/v1/audio/transcriptions"
    assert calls[0]["timeout"] == 7
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert calls[0]["data"]["model"] == "asr-test"
    assert calls[0]["data"]["language"] == "zh"
    assert calls[0]["data"]["prompt"] == "Subtap"


def test_http_asr_anthropic_provider_uses_messages_format(tmp_path: Path, monkeypatch):
    """HTTP ASR can call Anthropic-compatible Messages endpoints."""
    calls: list[dict] = []

    class Client:
        def __init__(self, timeout: int):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url: str, **kwargs):
            calls.append({"url": url, "timeout": self.timeout, **kwargs})
            return _Response({"content": [{"type": "text", "text": "Messages 转录"}]})

    monkeypatch.setenv("SUBTAP_TEST_API_KEY", "test-key")
    monkeypatch.setattr(
        http_asr, "httpx", SimpleNamespace(Client=Client), raising=False
    )

    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFF")
    remote = RemoteAPIConfig(
        provider="anthropic",
        base_url="https://asr.example.test/v1",
        api_key_env="SUBTAP_TEST_API_KEY",
        model="asr-messages",
    )
    backend = HttpASRBackend(ASRConfig(backend="http-asr"), remote)

    result = backend.transcribe(
        [Chunk(chunk_id=4, start_sec=2.0, end_sec=3.0, path=str(audio))]
    )

    assert result[0].text == "Messages 转录"
    assert calls[0]["url"] == "https://asr.example.test/v1/messages"
    assert calls[0]["headers"]["x-api-key"] == "test-key"
    assert calls[0]["json"]["model"] == "asr-messages"


def test_llm_factory_accepts_remote_api_config(monkeypatch):
    """OpenAI-compatible LLM can be configured by Subtap remote_api."""
    monkeypatch.setenv("SUBTAP_TEST_API_KEY", "llm-key")
    remote = RemoteAPIConfig(
        base_url="https://llm.example.test/v1",
        api_key_env="SUBTAP_TEST_API_KEY",
        model="llm-test",
        timeout_sec=9,
    )

    llm = get_llm_backend(CleanConfig(backend="openai:ignored"), remote)

    assert llm.base_url == "https://llm.example.test/v1"
    assert llm.api_key == "llm-key"
    assert llm.model == "llm-test"
    assert llm.timeout_sec == 9


def test_llm_anthropic_provider_uses_messages_format(monkeypatch):
    """Anthropic-compatible provider posts Messages payload."""
    calls: list[dict] = []

    class Client:
        def __init__(self, timeout: int):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url: str, **kwargs):
            calls.append({"url": url, "timeout": self.timeout, **kwargs})
            return _Response({"content": [{"type": "text", "text": "[0] 修正文本"}]})

    monkeypatch.setenv("SUBTAP_TEST_API_KEY", "anthropic-key")
    monkeypatch.setattr("subtap.backends.llm.openai_compat.httpx.Client", Client)

    remote = RemoteAPIConfig(
        provider="anthropic",
        base_url="https://anthropic.example.test/v1",
        api_key_env="SUBTAP_TEST_API_KEY",
        model="claude-test",
    )
    llm = get_llm_backend(CleanConfig(backend="openai:ignored"), remote)
    result = llm.clean_segments(
        [RawCleanSegment(segment_id=0, original_text="原文", cleaned_text="错文")]
    )

    assert result[0].cleaned_text == "修正文本"
    assert calls[0]["url"] == "https://anthropic.example.test/v1/messages"
    assert calls[0]["headers"]["x-api-key"] == "anthropic-key"
    assert calls[0]["json"]["model"] == "claude-test"


# ── 重试机制测试 ──────────────────────────────────────────────


def _make_llm(monkeypatch) -> OpenAICompatibleLLM:
    """构建一个用于测试的 LLM 实例。"""
    monkeypatch.setenv("RETRY_TEST_KEY", "test-key")
    remote = RemoteAPIConfig(
        base_url="https://retry.test/v1",
        api_key_env="RETRY_TEST_KEY",
        model="retry-model",
        timeout_sec=10,
    )
    return get_llm_backend(CleanConfig(backend="openai:ignored"), remote)


def _ok_response() -> _Response:
    return _Response({"choices": [{"message": {"content": "成功"}}]})


def test_chat_retries_on_timeout_then_succeeds(monkeypatch):
    """超时错误应重试，第 3 次成功后返回结果。"""
    llm = _make_llm(monkeypatch)
    call_count = 0

    def fake_post(self_client, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise httpx.ReadTimeout("连接超时")
        return _ok_response()

    class Client:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def post(self, url, **kwargs):
            return fake_post(self, url, **kwargs)

    monkeypatch.setattr("subtap.backends.llm.openai_compat.httpx.Client", Client)
    monkeypatch.setattr("subtap.backends.llm.openai_compat.time.sleep", lambda s: None)

    result = llm._chat("你好", "系统提示")
    assert result == "成功"
    assert call_count == 3


def test_chat_no_retry_on_400_error(monkeypatch):
    """400 错误不可重试，应直接抛出。"""
    llm = _make_llm(monkeypatch)
    call_count = 0

    class Client:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def post(self, url, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 400
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Bad Request",
                request=MagicMock(),
                response=resp,
            )
            return resp

    monkeypatch.setattr("subtap.backends.llm.openai_compat.httpx.Client", Client)

    with pytest.raises(httpx.HTTPStatusError):
        llm._chat("你好", "系统提示")
    assert call_count == 1  # 仅调用 1 次，无重试


def test_chat_retries_on_429_then_succeeds(monkeypatch):
    """429 限流应重试，第 2 次成功后返回结果。"""
    llm = _make_llm(monkeypatch)
    call_count = 0

    class Client:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def post(self, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                resp = MagicMock()
                resp.status_code = 429
                resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Too Many Requests",
                    request=MagicMock(),
                    response=resp,
                )
                return resp
            return _ok_response()

    monkeypatch.setattr("subtap.backends.llm.openai_compat.httpx.Client", Client)
    monkeypatch.setattr("subtap.backends.llm.openai_compat.time.sleep", lambda s: None)

    result = llm._chat("你好", "系统提示")
    assert result == "成功"
    assert call_count == 2
