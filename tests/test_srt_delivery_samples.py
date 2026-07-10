"""Tests for the SRT delivery check CLI."""

from __future__ import annotations

from pathlib import Path

from scripts.check_srt_delivery import main


def test_check_srt_delivery_accepts_clean_file(tmp_path: Path):
    srt = tmp_path / "clean.srt"
    srt.write_text(
        "1\n"
        "00:00:00,000 --> 00:00:01,000\n"
        "你好世界\n\n"
        "2\n"
        "00:00:01,100 --> 00:00:02,000\n"
        "继续测试\n",
        encoding="utf-8",
    )

    assert main([str(srt)]) == 0


def test_check_srt_delivery_rejects_overlapping_file(tmp_path: Path):
    srt = tmp_path / "overlap.srt"
    srt.write_text(
        "1\n"
        "00:00:00,000 --> 00:00:01,000\n"
        "你好世界\n\n"
        "2\n"
        "00:00:00,900 --> 00:00:02,000\n"
        "继续测试\n",
        encoding="utf-8",
    )

    assert main([str(srt)]) == 1


def test_check_srt_delivery_rejects_empty_file(tmp_path: Path):
    srt = tmp_path / "empty.srt"
    srt.write_text("", encoding="utf-8")

    assert main([str(srt)]) == 1
