from __future__ import annotations

from subtap.core.subtitle_quality import validate_srt_delivery


def test_rejects_empty_srt():
    report = validate_srt_delivery("")

    assert report.ok is False
    assert report.cues == 0


def test_rejects_overlapping_cues():
    srt = """1
00:00:01,000 --> 00:00:02,000
第一句

2
00:00:01,900 --> 00:00:03,000
第二句
"""

    report = validate_srt_delivery(srt)

    assert report.ok is False
    assert report.overlaps == 1


def test_rejects_zero_duration_cues():
    srt = """1
00:00:01,000 --> 00:00:01,000
第一句
"""

    report = validate_srt_delivery(srt)

    assert report.ok is False
    assert report.zero_duration == 1


def test_rejects_duplicate_or_nonsequential_cue_numbers():
    srt = """1
00:00:01,000 --> 00:00:02,000
第一句

1
00:00:02,100 --> 00:00:03,000
第二句
"""

    report = validate_srt_delivery(srt)

    assert report.ok is False
    assert report.parse_errors == 1


def test_rejects_cue_without_text():
    srt = """1
00:00:01,000 --> 00:00:02,000

"""

    report = validate_srt_delivery(srt)

    assert report.ok is False
    assert report.parse_errors == 1


def test_reports_readability_without_blocking():
    srt = """1
00:00:01,000 --> 00:00:02,000
这是一句非常非常非常非常非常非常长的字幕
"""

    report = validate_srt_delivery(srt, max_cps=8, max_line_chars=10)

    assert report.ok is True
    assert report.high_cps == 1
    assert report.long_lines == 1


def test_line_length_uses_visible_characters():
    srt = """1
00:00:01,000 --> 00:00:03,000
Highlight Diffusion Filter
"""

    report = validate_srt_delivery(srt, max_line_chars=24)

    assert report.long_lines == 0


def test_accepts_clean_short_srt():
    srt = """1
00:00:01,000 --> 00:00:02,500
第一句字幕

2
00:00:02,600 --> 00:00:04,000
第二句字幕
"""

    report = validate_srt_delivery(srt)

    assert report.ok is True
    assert report.cues == 2
