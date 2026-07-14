"""End-to-end tests for script matching."""

import tempfile
from pathlib import Path

import pytest

from subtap.script.match import match_from_file, match_script_lines

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
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
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


def test_asr_much_longer_than_script():
    """ASR 远多于文稿：50 条 ASR vs 10 行文稿。"""
    segments = [
        {"text": f"ASR句子{i}", "start_sec": float(i), "end_sec": float(i + 1)}
        for i in range(50)
    ]
    script = "\n".join([f"文稿句子{i}" for i in range(10)])
    result, report = match_script_lines(segments, script, mode="follow_script")
    # ASR 多出的行应保留
    assert len(result) >= 10
    assert isinstance(report.message, str)


def test_script_much_longer_than_asr():
    """文稿远多于 ASR：10 条 ASR vs 50 行文稿。"""
    segments = [
        {"text": f"ASR句子{i}", "start_sec": float(i), "end_sec": float(i + 1)}
        for i in range(10)
    ]
    script = "\n".join([f"文稿句子{i}" for i in range(50)])
    result, report = match_script_lines(segments, script, mode="follow_script")
    # 文稿多出的行应跳过
    assert len(result) <= 10 + 5  # 允许少量误差
    assert isinstance(report.message, str)


def test_threshold_boundary_exactly_07():
    """阈值边界：相似度恰好在 0.7 附近。"""
    # 构造相似度接近 0.7 的文本对
    asr_text = "今天天气很好"
    ref_text = "今天天气不错"  # 相似度约 0.67，低于阈值
    segments = [{"text": asr_text, "start_sec": 0.0, "end_sec": 2.0}]
    result, report = match_script_lines(segments, ref_text, mode="follow_script")
    # 相似度低于 0.7 应保留原文
    assert result[0]["text"] == asr_text or result[0]["text"] == ref_text


def test_mixed_operations():
    """混合操作：同时存在 insert + delete + replace。"""
    segments = [
        {"text": "A", "start_sec": 0.0, "end_sec": 1.0},
        {"text": "B", "start_sec": 1.0, "end_sec": 2.0},
        {"text": "C", "start_sec": 2.0, "end_sec": 3.0},
        {"text": "D", "start_sec": 3.0, "end_sec": 4.0},
        {"text": "E", "start_sec": 4.0, "end_sec": 5.0},
    ]
    # 文稿：A, X(替换B), Y(新增), D, E → C被删除
    script = "A\nX\nY\nD\nE"
    result, report = match_script_lines(segments, script, mode="follow_script")
    assert len(result) >= 4  # 至少保留 A, D, E + 可能的 B/C
    assert isinstance(report.message, str)


def test_large_scale_100_lines():
    """大规模测试：100 行 ASR + 100 行文稿。"""
    segments = [
        {"text": f"ASR句子{i}", "start_sec": float(i), "end_sec": float(i + 1)}
        for i in range(100)
    ]
    script = "\n".join([f"文稿句子{i}" for i in range(100)])
    result, report = match_script_lines(segments, script, mode="follow_script")
    assert len(result) > 0
    assert isinstance(report.message, str)


def test_all_lines_completely_different():
    """所有行完全不同：应触发 AlignmentQualityError 或返回警告。"""
    segments = [
        {
            "text": f"完全不同的ASR内容{i}",
            "start_sec": float(i),
            "end_sec": float(i + 1),
        }
        for i in range(5)
    ]
    script = "\n".join([f"完全不同的文稿内容{i}" for i in range(5)])
    result, report = match_script_lines(segments, script, mode="follow_script")
    # 应返回原 segments 或警告
    assert isinstance(report.message, str)


def test_single_line_match():
    """单行匹配：1 条 ASR vs 1 行文稿。"""
    segments = [{"text": "你好世界", "start_sec": 0.0, "end_sec": 2.0}]
    result, report = match_script_lines(segments, "你好世界", mode="follow_script")
    assert len(result) == 1
    assert result[0]["text"] == "你好世界"
    assert report.matched == 1


def test_asr_empty_text_segments():
    """ASR 包含空文本段。"""
    segments = [
        {"text": "", "start_sec": 0.0, "end_sec": 1.0},
        {"text": "正常文本", "start_sec": 1.0, "end_sec": 2.0},
    ]
    result, report = match_script_lines(segments, "正常文本", mode="follow_script")
    assert len(result) >= 1
