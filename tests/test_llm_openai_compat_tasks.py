from __future__ import annotations

import pytest

from subtap.backends.llm.openai_compat import OpenAICompatibleLLM
from subtap.schemas.config import RemoteAPIConfig


class FakeResponse:
    def __init__(self, payload: dict, status_error: Exception | None = None):
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self) -> None:
        if self.status_error:
            raise self.status_error

    def json(self) -> dict:
        return self.payload


class FakeClient:
    def __init__(self, response: FakeResponse, calls: list[dict]):
        self.response = response
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, headers: dict, json: dict):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self.response


def _client(monkeypatch, payload: dict):
    calls: list[dict] = []
    response = FakeResponse(payload)

    def make_client(*_args, **_kwargs):
        return FakeClient(response, calls)

    monkeypatch.setattr("subtap.backends.llm.openai_compat.httpx.Client", make_client)
    return calls


def _llm(monkeypatch, payload: dict) -> tuple[OpenAICompatibleLLM, list[dict]]:
    calls = _client(monkeypatch, payload)
    remote = RemoteAPIConfig(
        provider="openai-compatible",
        base_url="https://api.example.test/v1",
        api_key_env="SUBTAP_TEST_KEY",
        model="qwen-plus",
        timeout_sec=10,
    )
    monkeypatch.setenv("SUBTAP_TEST_KEY", "test-key")
    return OpenAICompatibleLLM(remote_api=remote), calls


def test_select_suspicious_segments_returns_only_input_indexes(monkeypatch):
    llm, calls = _llm(
        monkeypatch,
        {"choices": [{"message": {"content": '{"segments":[{"i":1}]}'}}]},
    )
    indexes = llm.select_suspicious_segments(
        [{"i": 0, "t": "正常句子"}, {"i": 1, "t": "李光机亚四"}]
    )

    assert indexes == [1]
    assert calls[0]["url"] == "https://api.example.test/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"


def test_select_suspicious_segments_rejects_unknown_index(monkeypatch):
    llm, _calls = _llm(
        monkeypatch,
        {"choices": [{"message": {"content": '{"segments":[{"i":99}]}'}}]},
    )

    with pytest.raises(ValueError, match="非法索引"):
        llm.select_suspicious_segments([{"i": 0, "t": "字幕"}])


def test_repair_segments_updates_only_returned_indexes(monkeypatch):
    llm, _calls = _llm(
        monkeypatch,
        {"choices": [{"message": {"content": '{"segments":[{"i":1,"t":"理光 GR4"}]}'}}]},
    )

    result = llm.repair_segments([{"i": 1, "t": "李光机亚四"}])

    assert result == {1: "理光 GR4"}


def test_repair_segments_rejects_empty_text(monkeypatch):
    llm, _calls = _llm(
        monkeypatch,
        {"choices": [{"message": {"content": '{"segments":[{"i":1,"t":"  "}]}'}}]},
    )

    with pytest.raises(ValueError, match="空文本"):
        llm.repair_segments([{"i": 1, "t": "李光机亚四"}])


def test_parse_segments_json_rejects_non_object_json(monkeypatch):
    llm, _calls = _llm(
        monkeypatch,
        {"choices": [{"message": {"content": "[]"}}]},
    )

    with pytest.raises(ValueError, match="合法 JSON 对象"):
        llm.select_suspicious_segments([{"i": 0, "t": "字幕"}])


def test_replace_hotwords_returns_updates_and_sends_glossary(monkeypatch):
    llm, calls = _llm(
        monkeypatch,
        {"choices": [{"message": {"content": '{"segments":[{"i":0,"t":"理光 GR4"}]}'}}]},
    )

    result = llm.replace_hotwords(
        [{"i": 0, "t": "李光机亚四"}],
        {"理光 GR4": ["李光机亚四"]},
    )

    prompt = calls[0]["json"]["messages"][1]["content"]
    assert result == {0: "理光 GR4"}
    assert "理光 GR4" in prompt
    assert "李光机亚四" in prompt


def test_translate_srt_returns_raw_srt(monkeypatch):
    content = "1\n00:00:01,000 --> 00:00:02,000\nHello\n"
    llm, _calls = _llm(
        monkeypatch,
        {"choices": [{"message": {"content": content}}]},
    )

    assert llm.translate_srt(content, "en") == content


def test_missing_api_key_fails(monkeypatch):
    remote = RemoteAPIConfig(
        provider="openai-compatible",
        base_url="https://api.example.test/v1",
        api_key_env="SUBTAP_MISSING_KEY",
        model="qwen-plus",
        timeout_sec=10,
    )
    monkeypatch.delenv("SUBTAP_MISSING_KEY", raising=False)

    with pytest.raises(ValueError, match="API key"):
        OpenAICompatibleLLM(remote_api=remote)
