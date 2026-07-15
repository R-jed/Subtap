"""Public offline performance gate tests."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_performance.py"


def _write_metrics(path: Path, *, rtf: float = 0.18) -> None:
    path.write_text(
        json.dumps(
            {
                "metrics_schema_version": 2,
                "audio_duration_sec": 100.0,
                "total_runtime_sec": rtf * 100.0,
                "rtf": rtf,
                "asr_runtime_sec": 12.0,
                "align_runtime_sec": 4.0,
                "asr_model_load_time_sec": 2.0,
                "aligner_model_load_time_sec": 1.0,
            }
        ),
        encoding="utf-8",
    )


def test_performance_gate_accepts_expected_rtf(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    _write_metrics(metrics)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(metrics), "--max-rtf", "0.25"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "RTF=0.1800" in result.stdout


def test_performance_gate_rejects_regression(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    _write_metrics(metrics, rtf=0.31)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(metrics), "--max-rtf", "0.25"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "RTF=0.3100" in result.stdout


def test_performance_gate_rejects_value_just_above_threshold(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    _write_metrics(metrics, rtf=0.2549)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(metrics), "--max-rtf", "0.25"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "RTF=0.2549" in result.stdout


def test_performance_gate_rejects_inconsistent_metrics(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    _write_metrics(metrics)
    payload = json.loads(metrics.read_text(encoding="utf-8"))
    payload["total_runtime_sec"] = 50.0
    metrics.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(metrics), "--max-rtf", "0.25"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "inconsistent" in result.stderr


def test_performance_gate_rejects_zero_model_load_time(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    _write_metrics(metrics)
    payload = json.loads(metrics.read_text(encoding="utf-8"))
    payload["asr_model_load_time_sec"] = 0.0
    metrics.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(metrics), "--max-rtf", "0.25"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "asr_model_load_time_sec must be greater than zero" in result.stderr
