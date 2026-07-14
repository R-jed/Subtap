"""Tests for the script_match pipeline stage."""

from __future__ import annotations

import json

import pytest


def test_script_match_stage_skips_without_script_path(tmp_path):
    """script_match 应在无 script_path 时跳过。"""
    from subtap.core.pipeline import Pipeline
    from subtap.schemas.config import SubtapConfig

    config = SubtapConfig()
    config.output.script_path = None
    workspace_dir = tmp_path / "work"
    workspace_dir.mkdir()

    pipeline = Pipeline(config=config, work_dir=workspace_dir)
    result = pipeline.run_stage("script_match")
    assert result == {"skipped": True}


def test_script_match_stage_corrects_asr_with_script(tmp_path):
    """script_match 应用文稿校正 ASR 文本。"""
    from subtap.core.pipeline import Pipeline
    from subtap.schemas.config import SubtapConfig

    # 创建 work 目录和 sentences.jsonl
    workspace_dir = tmp_path / "work"
    workspace_dir.mkdir()

    sentences = [
        {"sentence_id": 0, "text": "达文西是画家", "start_sec": 0.0, "end_sec": 2.0},
        {
            "sentence_id": 1,
            "text": "苹果公司发布了新产品",
            "start_sec": 2.0,
            "end_sec": 4.0,
        },
    ]
    sentences_path = workspace_dir / "sentences.jsonl"
    sentences_path.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in sentences) + "\n",
        encoding="utf-8",
    )

    # 创建文稿文件
    script_path = tmp_path / "script.txt"
    script_path.write_text("达芬奇是画家\n苹果公司发布了新产品\n", encoding="utf-8")

    config = SubtapConfig()
    config.output.script_path = str(script_path)
    config.output.script_mode = "follow_script"

    pipeline = Pipeline(config=config, work_dir=workspace_dir)
    result = pipeline.run_stage("script_match")

    assert result["matched"] >= 1
    assert result["corrected"] >= 1


def test_script_match_stage_handles_missing_script_file(tmp_path):
    """script_match 应在文稿文件不存在时抛出异常。"""
    from subtap.core.pipeline import Pipeline
    from subtap.schemas.config import SubtapConfig

    config = SubtapConfig()
    config.output.script_path = "/nonexistent/script.txt"

    workspace_dir = tmp_path / "work"
    workspace_dir.mkdir()

    pipeline = Pipeline(config=config, work_dir=workspace_dir)
    with pytest.raises(ValueError, match="文稿文件不存在"):
        pipeline.run_stage("script_match")
