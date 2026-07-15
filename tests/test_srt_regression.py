"""Public subtitle regression gate tests."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_srt_regression.py"


def _write_srt(path: Path, cues: list[tuple[str, str, str]]) -> None:
    blocks = [
        f"{index}\n{start} --> {end}\n{text}"
        for index, (start, end, text) in enumerate(cues, start=1)
    ]
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def test_matching_reviewed_subtitle_passes(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.srt"
    actual = tmp_path / "actual.srt"
    cues = [
        ("00:00:00,000", "00:00:01,000", "一直是一机难求的状态"),
        ("00:00:01,100", "00:00:02,000", "它叫做理光GR4"),
    ]
    _write_srt(reviewed, cues)
    _write_srt(actual, cues)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(actual), str(reviewed)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "CER=0.0000" in result.stdout
    assert "cue_match=1.0000" in result.stdout
    assert "timing_mae=0.0000" in result.stdout


def test_missing_required_reviewed_cue_fails(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.srt"
    actual = tmp_path / "actual.srt"
    required = tmp_path / "required.txt"
    cues = [("00:00:00,000", "00:00:01,000", "它叫做理光GR四")]
    _write_srt(reviewed, cues)
    _write_srt(actual, cues)
    required.write_text("它叫做理光GR4\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(actual),
            str(reviewed),
            "--required-cues",
            str(required),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "missing_required=1" in result.stdout


def test_recognition_regression_fails(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.srt"
    actual = tmp_path / "actual.srt"
    _write_srt(
        reviewed,
        [("00:00:00,000", "00:00:01,000", "它叫做理光GR4")],
    )
    _write_srt(
        actual,
        [("00:00:00,000", "00:00:01,000", "完全错误的字幕")],
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(actual), str(reviewed)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1


def test_timing_regression_fails(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.srt"
    actual = tmp_path / "actual.srt"
    _write_srt(
        reviewed,
        [("00:00:00,000", "00:00:01,000", "它叫做理光GR4")],
    )
    _write_srt(
        actual,
        [("00:00:00,600", "00:00:01,600", "它叫做理光GR4")],
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(actual), str(reviewed)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "timing_mae=0.6000" in result.stdout
