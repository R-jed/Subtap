#!/usr/bin/env python3
"""Validate pipeline measurements and reject offline performance regressions."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys


def _positive_number(payload: dict, key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{key} must be greater than zero")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metrics", type=Path)
    parser.add_argument("--max-rtf", type=float, required=True)
    args = parser.parse_args()

    if not math.isfinite(args.max_rtf) or args.max_rtf <= 0:
        parser.error("--max-rtf must be greater than zero")

    try:
        payload = json.loads(args.metrics.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("metrics must contain a JSON object")
        if payload.get("metrics_schema_version") != 2:
            raise ValueError("metrics_schema_version must be 2")
        audio_duration = _positive_number(payload, "audio_duration_sec")
        total_runtime = _positive_number(payload, "total_runtime_sec")
        rtf = _positive_number(payload, "rtf")
        asr_load = _positive_number(payload, "asr_model_load_time_sec")
        aligner_load = _positive_number(payload, "aligner_model_load_time_sec")
        asr_runtime = _positive_number(payload, "asr_runtime_sec")
        align_runtime = _positive_number(payload, "align_runtime_sec")
        if asr_load > asr_runtime or aligner_load > align_runtime:
            raise ValueError("model load time cannot exceed its stage runtime")
        calculated_rtf = total_runtime / audio_duration
        if abs(rtf - calculated_rtf) > 0.000001:
            raise ValueError(
                "metrics are inconsistent: rtf does not match runtime/audio duration"
            )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"performance check failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"RTF={calculated_rtf:.4f} max={args.max_rtf:.4f} "
        f"ASR_LOAD={asr_load:.2f}s ALIGN_LOAD={aligner_load:.2f}s"
    )
    return 0 if calculated_rtf <= args.max_rtf else 1


if __name__ == "__main__":
    raise SystemExit(main())
