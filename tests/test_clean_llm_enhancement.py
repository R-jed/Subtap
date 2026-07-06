from __future__ import annotations

from pathlib import Path

import pytest

from subtap.core.clean import run_clean
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import ASRSegment


class FakeLLM:
    def __init__(
        self, suspicious: list[int], repairs: dict[int, str], hotwords: dict[int, str]
    ):
        self.suspicious = suspicious
        self.repairs = repairs
        self.hotwords = hotwords
        self.calls: list[str] = []
        self.glossaries: list[dict | None] = []

    def select_suspicious_segments(self, segments: list[dict]) -> list[int]:
        self.calls.append("select")
        return self.suspicious

    def repair_segments(self, segments: list[dict]) -> dict[int, str]:
        self.calls.append("repair")
        return self.repairs

    def replace_hotwords(
        self, segments: list[dict], glossary: dict | None
    ) -> dict[int, dict]:
        self.calls.append("hotword")
        self.glossaries.append(glossary)
        return {idx: {"text": text, "ops": []} for idx, text in self.hotwords.items()}


def _workspace(tmp_path: Path, texts: list[str] | None = None) -> Workspace:
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    rows = [
        ASRSegment(
            chunk_id=0,
            segment_id=index,
            start_sec=float(index),
            end_sec=float(index + 1),
            text=text,
        )
        for index, text in enumerate(texts or ["正常句子", "李光机亚四"])
    ]
    workspace.asr_jsonl.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows),
        encoding="utf-8",
    )
    return workspace


def _cleaned_texts(workspace: Workspace) -> list[str]:
    return [
        line
        for line in workspace.cleaned_jsonl.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_enhance_local_does_not_request_llm(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)

    def fail_get_backend(*_args, **_kwargs):
        raise AssertionError("local 模式不应创建 LLM")

    monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_get_backend)

    result = run_clean(workspace, SubtapConfig(), enhance_mode="local")

    assert result["segment_count"] == 2
    assert len(_cleaned_texts(workspace)) == 2


def test_enhance_mode_local_disables_llm(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)

    def fail_get_backend(*_args, **_kwargs):
        raise AssertionError("local 模式不应创建 LLM")

    monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_get_backend)

    result = run_clean(workspace, SubtapConfig(), enhance_mode="local")

    assert result["segment_count"] == 2


def test_enhance_local_ignores_user_home_hotwords_without_explicit_dir(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    glossary_dir = home / ".subtap" / "glossary"
    glossary_dir.mkdir(parents=True)
    (glossary_dir / "hotwords_zh.txt").write_text(
        "Big Apple=New York\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    workspace = _workspace(tmp_path, ["New York"])

    run_clean(workspace, SubtapConfig(), enhance_mode="local")

    payload = workspace.cleaned_jsonl.read_text(encoding="utf-8")
    assert "New York" in payload
    assert "Big Apple" not in payload


def test_enhance_local_uses_explicit_hotword_glossary_dir(tmp_path):
    glossary_dir = tmp_path / "glossary"
    glossary_dir.mkdir()
    (glossary_dir / "hotwords_zh.txt").write_text(
        "Big Apple=New York\n",
        encoding="utf-8",
    )
    workspace = _workspace(tmp_path, ["New York"])

    run_clean(
        workspace,
        SubtapConfig(),
        enhance_mode="local",
        hotword_glossary_dir=str(glossary_dir),
    )

    payload = workspace.cleaned_jsonl.read_text(encoding="utf-8")
    assert "Big Apple" in payload


def test_enhance_api_selects_and_repairs_only_suspicious_segments(
    tmp_path, monkeypatch
):
    workspace = _workspace(tmp_path)
    llm = FakeLLM(suspicious=[1], repairs={1: "理光 GR4"}, hotwords={})
    monkeypatch.setattr("subtap.core.clean.get_llm_backend", lambda *_a, **_k: llm)

    run_clean(workspace, SubtapConfig(), enhance_mode="api")

    assert llm.calls == ["select", "repair", "hotword"]
    payload = workspace.cleaned_jsonl.read_text(encoding="utf-8")
    assert "正常句子" in payload
    assert "理光 GR4" in payload


def test_enhance_api_skips_repair_when_qc_returns_empty(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    llm = FakeLLM(suspicious=[], repairs={}, hotwords={})
    monkeypatch.setattr("subtap.core.clean.get_llm_backend", lambda *_a, **_k: llm)

    run_clean(workspace, SubtapConfig(), enhance_mode="api")

    assert llm.calls == ["select", "hotword"]


def test_enhance_api_runs_hotwords_when_glossary_empty(tmp_path, monkeypatch):
    """AI 热词应在本地热词为空时自主发现领域专有名词。"""
    workspace = _workspace(tmp_path)
    llm = FakeLLM(suspicious=[], repairs={}, hotwords={1: "理光 GR4"})
    monkeypatch.setattr("subtap.core.clean.get_llm_backend", lambda *_a, **_k: llm)

    run_clean(workspace, SubtapConfig(), enhance_mode="api")

    assert llm.calls == ["select", "hotword"]


def test_enhance_api_passes_hotword_payload_when_glossary_exists(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    glossary_path = tmp_path / "glossary.yaml"
    glossary_path.write_text(
        """
terms:
  - canonical: 理光 GR4
    aliases: [李光 GR4]
replacements:
  - find: 李光机亚四
    replace: 理光 GR4
""",
        encoding="utf-8",
    )
    llm = FakeLLM(suspicious=[], repairs={}, hotwords={1: "理光 GR4"})
    monkeypatch.setattr("subtap.core.clean.get_llm_backend", lambda *_a, **_k: llm)

    run_clean(
        workspace,
        SubtapConfig(),
        glossary_path=str(glossary_path),
        enhance_mode="api",
    )

    assert llm.calls == ["select", "hotword"]
    assert llm.glossaries == [{"理光 GR4": ["李光 GR4", "李光机亚四"]}]
    payload = workspace.cleaned_jsonl.read_text(encoding="utf-8")
    assert "理光 GR4" in payload


def test_enhance_api_propagates_llm_errors(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)

    class BrokenLLM:
        def select_suspicious_segments(self, _segments):
            raise ValueError("LLM JSON 非法")

    monkeypatch.setattr(
        "subtap.core.clean.get_llm_backend", lambda *_a, **_k: BrokenLLM()
    )

    with pytest.raises(ValueError, match="LLM JSON 非法"):
        run_clean(workspace, SubtapConfig(), enhance_mode="api")
