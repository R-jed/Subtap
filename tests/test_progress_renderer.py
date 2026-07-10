"""Tests for ANSI pipeline progress renderer."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from subtap.ui.progress_renderer import PipelineProgressRenderer, _model_display_name


def test_parse_stage_start_event():
    """解析 STAGE_START 事件。"""
    renderer = PipelineProgressRenderer(stderr=MagicMock())
    event = {
        "event_type": "stage_start",
        "data": {"stage": "asr", "message_zh": "语音识别"},
    }
    renderer._handle_event(event)
    assert renderer._current_stage == "asr"
    assert renderer._current_stage_cn == "语音识别"
    assert renderer._stage_index == 3


def test_parse_stage_end_event():
    renderer = PipelineProgressRenderer(stderr=MagicMock())
    renderer._handle_event({"event_type": "stage_start", "data": {"stage": "prepare"}})
    renderer._handle_event({"event_type": "stage_end", "data": {"stage": "prepare"}})
    assert renderer._completed_stages == 1


def test_parse_progress_event():
    renderer = PipelineProgressRenderer(stderr=MagicMock())
    renderer._handle_event({"event_type": "stage_start", "data": {"stage": "asr"}})
    renderer._handle_event(
        {
            "event_type": "asr_draft_ready",
            "data": {"stage": "asr", "chunk_id": 5, "progress": 50},
        }
    )
    assert renderer._stage_progress == 50.0


def test_parse_model_load_event():
    renderer = PipelineProgressRenderer(stderr=MagicMock())
    renderer._handle_event(
        {"event_type": "model_load_start", "data": {"model": "asr_0.6b"}}
    )
    assert renderer._model_name == "asr_0.6b"


def test_model_display_name_mapping():
    assert _model_display_name("asr_0.6b") == "快速"
    assert _model_display_name("asr_1.7b") == "高质量"
    assert _model_display_name("aligner_0.6b") == "对齐"
    assert _model_display_name("unknown_model") == "unknown_model"


def test_render_line_contains_stage_info():
    renderer = PipelineProgressRenderer(stderr=MagicMock())
    renderer._handle_event(
        {
            "event_type": "stage_start",
            "data": {"stage": "asr", "message_zh": "语音识别"},
        }
    )
    renderer._handle_event(
        {"event_type": "model_load_start", "data": {"model": "asr_0.6b"}}
    )
    renderer._handle_event(
        {
            "event_type": "asr_draft_ready",
            "data": {"stage": "asr", "chunk_id": 3, "progress": 60},
        }
    )
    lines = renderer._build_lines()
    assert any("语音识别" in line for line in lines)
    assert any("60%" in line for line in lines)
    assert any("快速" in line for line in lines)


def test_render_contains_colors():
    renderer = PipelineProgressRenderer(stderr=MagicMock())
    renderer._handle_event(
        {
            "event_type": "stage_start",
            "data": {"stage": "asr", "message_zh": "语音识别"},
        }
    )
    renderer._handle_event(
        {"event_type": "asr_draft_ready", "data": {"stage": "asr", "progress": 50}}
    )
    lines = renderer._build_lines()
    combined = "\n".join(lines)
    assert "\033[" in combined
    assert "\033[32m" in combined
    assert "\033[35;1m" in combined


def test_read_jsonl_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(
            json.dumps({"event_type": "stage_start", "data": {"stage": "prepare"}})
            + "\n"
        )
        f.write(
            json.dumps({"event_type": "stage_end", "data": {"stage": "prepare"}}) + "\n"
        )
        f.write(
            json.dumps({"event_type": "stage_start", "data": {"stage": "chunk"}}) + "\n"
        )
        path = Path(f.name)
    renderer = PipelineProgressRenderer(stderr=MagicMock())
    events = renderer._read_new_events(path)
    assert len(events) == 3
    with open(path, "a") as f:
        f.write(
            json.dumps({"event_type": "stage_end", "data": {"stage": "chunk"}}) + "\n"
        )
    events = renderer._read_new_events(path)
    assert len(events) == 1
    path.unlink()


def test_build_progress_bar():
    renderer = PipelineProgressRenderer(stderr=MagicMock())
    bar = renderer._build_bar(60.0, width=20)
    assert "█" in bar
    assert "░" in bar
    assert bar.count("█") == 12
    assert bar.count("░") == 8


def test_final_result_lines():
    renderer = PipelineProgressRenderer(stderr=MagicMock())
    renderer._completed_stages = 7
    renderer._total_stages = 7
    renderer._total_time = 42.5
    lines = renderer._build_result_lines(success=True, output_path="/tmp/test.srt")
    assert any("完成" in line for line in lines)
    assert any("42" in line for line in lines)
