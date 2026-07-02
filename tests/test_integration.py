"""集成测试：验证完整 pipeline 流程中 LLM 功能的调用。"""

from __future__ import annotations

import pytest

from helpers import MockLLMBackend
from subtap.core.pipeline import Pipeline
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.glossary import Glossary, GlossaryTerm
from subtap.schemas.models import AlignedSegment, ASRSegment

# ── Helpers ──


def prepare_test_audio(tmp_path):
    """准备测试用的 workspace 和 mock 数据。"""
    config = SubtapConfig()
    config.workspace.root = str(tmp_path / "work")

    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()

    # 写入 mock ASR 数据
    asr_segments = [
        ASRSegment(
            chunk_id=0,
            segment_id=0,
            start_sec=0.0,
            end_sec=1.5,
            text="这是第一句话",
        ),
        ASRSegment(
            chunk_id=0,
            segment_id=1,
            start_sec=1.5,
            end_sec=3.0,
            text="这是第二句话",
        ),
    ]
    workspace.asr_dir.mkdir(parents=True, exist_ok=True)
    with open(workspace.asr_jsonl, "w") as f:
        for seg in asr_segments:
            f.write(seg.model_dump_json() + "\n")

    # 写入 mock aligned 数据（供翻译测试使用）
    aligned_segments = [
        AlignedSegment(
            sentence_id=0,
            start_sec=0.0,
            end_sec=1.5,
            text="这是第一句话",
            words=[],
        ),
        AlignedSegment(
            sentence_id=1,
            start_sec=1.5,
            end_sec=3.0,
            text="这是第二句话",
            words=[],
        ),
    ]
    with open(workspace.aligned_jsonl, "w") as f:
        for seg in aligned_segments:
            f.write(seg.model_dump_json() + "\n")

    return config, workspace


def run_pipeline(config, workspace):
    """运行 pipeline 的 clean 和 translate 阶段。"""
    pipeline = Pipeline(config, work_dir=workspace.root)

    # 运行 clean 阶段
    clean_kwargs = {
        "enhance_mode": "local",
    }

    # 根据配置决定是否启用 LLM
    if config.llm_proofread or config.llm_hotword:
        clean_kwargs["enhance_mode"] = None  # 让配置项生效

    pipeline.run_stage("clean", **clean_kwargs)

    # 如果配置了翻译，运行 translate 阶段
    if config.translate_to:
        pipeline.run_stage("translate", target_language=config.translate_to)

    return {"success": True}


# ── Tests ──


def test_full_pipeline_with_llm_proofread(tmp_path):
    """完整 pipeline 测试：开启 AI 校对。"""
    config, workspace = prepare_test_audio(tmp_path)

    config.llm_proofread = True
    config.llm_hotword = False
    config.translate_to = ""

    mock_llm = MockLLMBackend()

    with pytest.MonkeyPatch.context() as m:
        m.setattr("subtap.core.clean.get_llm_backend", lambda *a, **k: mock_llm)
        result = run_pipeline(config, workspace)

    assert result["success"] is True
    assert mock_llm.select_suspicious_segments_called is True
    assert mock_llm.repair_segments_called is True
    assert mock_llm.replace_hotwords_called is False


def test_full_pipeline_with_llm_hotword(tmp_path):
    """完整 pipeline 测试：开启 AI 热词替换。"""
    config, workspace = prepare_test_audio(tmp_path)

    config.llm_proofread = False
    config.llm_hotword = True
    config.translate_to = ""

    mock_llm = MockLLMBackend()
    mock_glossary = Glossary(terms=[GlossaryTerm(canonical="test", aliases=["Test"])])

    with pytest.MonkeyPatch.context() as m:
        m.setattr("subtap.core.clean.get_llm_backend", lambda *a, **k: mock_llm)
        m.setattr("subtap.core.clean.load_glossary", lambda *a, **k: mock_glossary)
        result = run_pipeline(config, workspace)

    assert result["success"] is True
    assert mock_llm.select_suspicious_segments_called is False
    assert mock_llm.replace_hotwords_called is True


def test_full_pipeline_with_translation(tmp_path):
    """完整 pipeline 测试：开启翻译。"""
    config, workspace = prepare_test_audio(tmp_path)

    config.llm_proofread = False
    config.llm_hotword = False
    config.translate_to = "zh"

    mock_llm = MockLLMBackend()

    with pytest.MonkeyPatch.context() as m:
        m.setattr("subtap.core.translate.get_llm_backend", lambda *a, **k: mock_llm)
        result = run_pipeline(config, workspace)

    assert result["success"] is True
    assert mock_llm.translate_srt_called is True


def test_full_pipeline_with_both_llm_features(tmp_path):
    """完整 pipeline 测试：同时开启 AI 校对和热词替换。"""
    config, workspace = prepare_test_audio(tmp_path)

    config.llm_proofread = True
    config.llm_hotword = True
    config.translate_to = ""

    mock_llm = MockLLMBackend()
    mock_glossary = Glossary(terms=[GlossaryTerm(canonical="test", aliases=["Test"])])

    with pytest.MonkeyPatch.context() as m:
        m.setattr("subtap.core.clean.get_llm_backend", lambda *a, **k: mock_llm)
        m.setattr("subtap.core.clean.load_glossary", lambda *a, **k: mock_glossary)
        result = run_pipeline(config, workspace)

    assert result["success"] is True
    assert mock_llm.select_suspicious_segments_called is True
    assert mock_llm.repair_segments_called is True
    assert mock_llm.replace_hotwords_called is True


def test_full_pipeline_with_llm_disabled(tmp_path):
    """完整 pipeline 测试：LLM 全部关闭，无翻译。"""
    config, workspace = prepare_test_audio(tmp_path)

    config.llm_proofread = False
    config.llm_hotword = False
    config.translate_to = ""

    # 不需要 mock LLM——不应被调用
    result = run_pipeline(config, workspace)

    assert result["success"] is True
