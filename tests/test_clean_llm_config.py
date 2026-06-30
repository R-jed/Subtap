"""Tests for clean stage using independent llm_proofread/llm_hotword config."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from subtap.core.clean import run_clean
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.glossary import Glossary, GlossaryTerm
from subtap.schemas.models import ASRSegment


class MockLLMBackend:
    """Mock LLM backend that tracks which methods were called."""

    def __init__(self):
        self.select_suspicious_segments_called = False
        self.repair_segments_called = False
        self.replace_hotwords_called = False
        self._selected_ids = []

    def select_suspicious_segments(self, segments):
        self.select_suspicious_segments_called = True
        # Return some IDs to trigger repair
        self._selected_ids = [0] if segments else []
        return self._selected_ids

    def repair_segments(self, segments):
        self.repair_segments_called = True
        return {s["i"]: s["t"] + " [fixed]" for s in segments}

    def replace_hotwords(self, segments, hotword_payload):
        self.replace_hotwords_called = True
        return {s["i"]: s["t"] + " [hotword]" for s in segments}


def _make_asr_jsonl(ws: Workspace, texts: list[str]) -> None:
    """Write mock ASR segments to asr.jsonl."""
    ws.asr_dir.mkdir(parents=True, exist_ok=True)
    with open(ws.asr_jsonl, "w") as f:
        for i, text in enumerate(texts):
            seg = ASRSegment(
                chunk_id=i,
                segment_id=i,
                start_sec=float(i),
                end_sec=float(i + 1),
                text=text,
            )
            f.write(seg.model_dump_json() + "\n")


@pytest.fixture
def workspace(tmp_path):
    """Create a test workspace with mock ASR data."""
    config = SubtapConfig()
    ws = Workspace(config, base_dir=tmp_path / "work")
    ws.ensure_dirs()
    _make_asr_jsonl(ws, ["hello world", "test segment"])
    return ws


def test_run_clean_uses_llm_proofread_config(workspace):
    """run_clean 应使用 llm_proofread 配置项"""
    config = SubtapConfig()
    config.llm_proofread = True
    config.llm_hotword = False

    mock_llm = MockLLMBackend()

    with patch("subtap.core.clean.get_llm_backend", return_value=mock_llm):
        result = run_clean(workspace, config)

    # 验证 LLM 校对被调用
    assert mock_llm.select_suspicious_segments_called is True
    assert mock_llm.repair_segments_called is True
    # 验证热词替换未被调用（因为 llm_hotword=False）
    assert mock_llm.replace_hotwords_called is False


def test_run_clean_uses_llm_hotword_config(workspace):
    """run_clean 应使用 llm_hotword 配置项"""
    config = SubtapConfig()
    config.llm_proofread = False
    config.llm_hotword = True

    mock_llm = MockLLMBackend()

    # 创建 glossary 以提供 hotword_payload
    mock_glossary = Glossary(
        terms=[GlossaryTerm(canonical="test", aliases=["Test"])]
    )

    with patch("subtap.core.clean.get_llm_backend", return_value=mock_llm), \
         patch("subtap.core.clean.load_glossary", return_value=mock_glossary):
        result = run_clean(workspace, config)

    # 验证 LLM 校对未被调用（因为 llm_proofread=False）
    assert mock_llm.select_suspicious_segments_called is False
    assert mock_llm.repair_segments_called is False
    # 验证热词替换被调用
    assert mock_llm.replace_hotwords_called is True


def test_run_clean_skips_llm_when_both_disabled(workspace):
    """run_clean 应在两个开关都关闭时跳过 LLM"""
    config = SubtapConfig()
    config.llm_proofread = False
    config.llm_hotword = False

    mock_llm = MockLLMBackend()

    with patch("subtap.core.clean.get_llm_backend", return_value=mock_llm):
        result = run_clean(workspace, config)

    # 验证 LLM 未被调用
    assert mock_llm.select_suspicious_segments_called is False
    assert mock_llm.repair_segments_called is False
    assert mock_llm.replace_hotwords_called is False


def test_run_clean_both_enabled(workspace):
    """run_clean 应在两个开关都开启时同时调用校对和热词"""
    config = SubtapConfig()
    config.llm_proofread = True
    config.llm_hotword = True

    mock_llm = MockLLMBackend()

    # 创建 glossary 以提供 hotword_payload
    mock_glossary = Glossary(
        terms=[GlossaryTerm(canonical="test", aliases=["Test"])]
    )

    with patch("subtap.core.clean.get_llm_backend", return_value=mock_llm), \
         patch("subtap.core.clean.load_glossary", return_value=mock_glossary):
        result = run_clean(workspace, config)

    # 验证两个功能都被调用
    assert mock_llm.select_suspicious_segments_called is True
    assert mock_llm.repair_segments_called is True
    assert mock_llm.replace_hotwords_called is True


def test_run_clean_enhance_mode_off_overrides_config(workspace):
    """enhance_mode='off' 应覆盖独立配置项，禁用所有 LLM 功能"""
    config = SubtapConfig()
    config.llm_proofread = True
    config.llm_hotword = True

    mock_llm = MockLLMBackend()

    with patch("subtap.core.clean.get_llm_backend", return_value=mock_llm):
        result = run_clean(workspace, config, enhance_mode="off")

    # enhance_mode="off" 应该禁用所有 LLM 功能
    assert mock_llm.select_suspicious_segments_called is False
    assert mock_llm.repair_segments_called is False
    assert mock_llm.replace_hotwords_called is False


def test_run_clean_llm_backend_name_off_overrides_config(workspace):
    """llm_backend_name='off' 应覆盖独立配置项，禁用所有 LLM 功能"""
    config = SubtapConfig()
    config.llm_proofread = True
    config.llm_hotword = True

    mock_llm = MockLLMBackend()

    with patch("subtap.core.clean.get_llm_backend", return_value=mock_llm):
        result = run_clean(workspace, config, llm_backend_name="off")

    # llm_backend_name="off" 应该禁用所有 LLM 功能
    assert mock_llm.select_suspicious_segments_called is False
    assert mock_llm.repair_segments_called is False
    assert mock_llm.replace_hotwords_called is False
