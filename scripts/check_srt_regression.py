#!/usr/bin/env python3
"""Compare a generated SRT with a manually reviewed reference."""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from subtap.core.subtitle_quality import parse_srt_cues, validate_srt_delivery


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def _normalize(text: str) -> str:
    return "".join(character.lower() for character in text if character.isalnum())


def _load(path: Path) -> list[Cue]:
    content = path.read_text(encoding="utf-8-sig")
    report = validate_srt_delivery(content)
    if not report.ok:
        raise ValueError(f"SRT 交付检查失败：{path}: {report}")

    return [
        Cue(start=cue.start, end=cue.end, text=_normalize(cue.text))
        for cue in parse_srt_cues(content)
    ]


def _metrics(actual: list[Cue], reference: list[Cue]) -> tuple[float, float, float]:
    actual_text = "".join(cue.text for cue in actual)
    reference_text = "".join(cue.text for cue in reference)
    cer = Levenshtein.distance(actual_text, reference_text) / max(
        len(reference_text), 1
    )

    actual_by_text: dict[str, deque[Cue]] = defaultdict(deque)
    for cue in actual:
        actual_by_text[cue.text].append(cue)

    timing_errors: list[float] = []
    matched = 0
    for reference_cue in reference:
        matches = actual_by_text[reference_cue.text]
        if not matches:
            continue
        actual_cue = matches.popleft()
        matched += 1
        timing_errors.extend(
            (
                abs(actual_cue.start - reference_cue.start),
                abs(actual_cue.end - reference_cue.end),
            )
        )

    cue_match = matched / max(len(reference), 1)
    timing_mae = (
        sum(timing_errors) / len(timing_errors) if timing_errors else float("inf")
    )
    return cer, cue_match, timing_mae


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("actual", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--max-cer", type=float, default=0.03)
    parser.add_argument("--min-cue-match", type=float, default=0.80)
    parser.add_argument("--max-timing-mae", type=float, default=0.50)
    parser.add_argument("--required-cues", type=Path)
    args = parser.parse_args(argv)

    actual = _load(args.actual)
    cer, cue_match, timing_mae = _metrics(actual, _load(args.reference))
    required = (
        {
            normalized
            for line in args.required_cues.read_text(encoding="utf-8").splitlines()
            if (normalized := _normalize(line))
        }
        if args.required_cues
        else set()
    )
    missing_required = len(required - {cue.text for cue in actual})
    print(
        f"CER={cer:.4f} cue_match={cue_match:.4f} "
        f"timing_mae={timing_mae:.4f} missing_required={missing_required}"
    )
    return int(
        cer > args.max_cer
        or cue_match < args.min_cue_match
        or timing_mae > args.max_timing_mae
        or missing_required
    )


if __name__ == "__main__":
    raise SystemExit(main())
