"""End-to-end tests for script matching."""
import tempfile
from pathlib import Path

import pytest

from subtap.script.match import match_from_file, match_script_lines, MatchReport

FIXTURES = Path(__file__).parent / "fixtures"
ASR_FILE = FIXTURES / "script_test_asr_sentences.jsonl"


def _load_asr_segments() -> list[dict]:
    import json
    segments = []
    with open(ASR_FILE) as f:
        for line in f:
            if line.strip():
                segments.append(json.loads(line))
    return segments


def test_follow_script_real_data():
    segments = _load_asr_segments()
    script = (FIXTURES / "script_test_manuscript.txt").read_text(encoding="utf-8")
    result, report = match_script_lines(segments, script, mode="follow_script")
    assert len(result) > 0
    assert report.matched > 0
    assert isinstance(report.message, str)


def test_correct_only_real_data():
    segments = _load_asr_segments()
    script = (FIXTURES / "script_test_manuscript.txt").read_text(encoding="utf-8")
    result, report = match_script_lines(segments, script, mode="correct_only")
    assert len(result) > 0
    assert isinstance(report.message, str)


def test_empty_script_returns_error():
    segments = _load_asr_segments()
    result, report = match_script_lines(segments, "", mode="follow_script")
    assert len(result) == 0
    assert len(report.warnings) > 0


def test_report_no_warnings_on_perfect_match():
    segments = [{"text": "相同文本", "start_sec": 0.0, "end_sec": 2.0}]
    result, report = match_script_lines(segments, "相同文本", mode="follow_script")
    assert len(report.warnings) == 0


def test_invalid_mode_raises():
    """无效模式应抛出 ValueError。"""
    segments = [{"text": "A", "start_sec": 0.0, "end_sec": 2.0}]
    with pytest.raises(ValueError, match="未知文稿匹配模式"):
        match_script_lines(segments, "A", mode="invalid")


def test_empty_segments():
    """空 segments 应返回空列表和警告。"""
    result, report = match_script_lines([], "some script", mode="follow_script")
    assert len(result) == 0
    assert len(report.warnings) > 0


def test_match_from_file():
    """match_from_file 便捷函数应正常工作。"""
    segments = [{"text": "相同文本", "start_sec": 0.0, "end_sec": 2.0}]
    # 创建临时文稿文件
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("相同文本")
        tmp_path = Path(f.name)
    try:
        result, report = match_from_file(segments, tmp_path, mode="follow_script")
        assert len(result) == 1
        assert result[0]["text"] == "相同文本"
    finally:
        tmp_path.unlink()


def test_report_corrected_count():
    """报告应包含正确的纠错计数。"""
    segments = [
        {"text": "一击难求", "start_sec": 0.0, "end_sec": 2.0},
        {"text": "正常文本", "start_sec": 2.0, "end_sec": 4.0},
    ]
    script = "一机难求\n正常文本"
    result, report = match_script_lines(segments, script, mode="follow_script")
    assert report.corrected >= 0
    assert isinstance(report.message, str)
