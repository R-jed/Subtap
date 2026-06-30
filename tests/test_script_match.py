"""End-to-end tests for script matching."""
from pathlib import Path
from subtap.script.match import match_script_lines, MatchReport

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
