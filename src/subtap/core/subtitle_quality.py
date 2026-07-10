"""Subtitle delivery quality checks."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SubtitleQualityReport:
    """Summary of SRT delivery checks."""

    ok: bool
    cues: int
    overlaps: int = 0
    reversed_ranges: int = 0
    zero_duration: int = 0
    high_cps: int = 0
    long_lines: int = 0
    parse_errors: int = 0


_TIME_RE = re.compile(r"(\d\d:\d\d:\d\d,\d\d\d) --> (\d\d:\d\d:\d\d,\d\d\d)")


def _parse_time(value: str) -> float:
    h, m, rest = value.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def validate_srt_delivery(
    content: str,
    *,
    max_cps: float = 18.0,
    max_line_chars: int = 25,
) -> SubtitleQualityReport:
    """Validate SRT timing invariants and readability signals.

    Hard failures are parse errors, reversed ranges, zero duration, and overlaps.
    CPS and line length are reported for delivery review but do not block export yet.
    """
    blocks = [block.strip() for block in content.strip().split("\n\n") if block.strip()]
    previous_end = -1.0
    overlaps = 0
    reversed_ranges = 0
    zero_duration = 0
    high_cps = 0
    long_lines = 0
    parse_errors = 0

    for block in blocks:
        lines = block.splitlines()
        time_line = next((line for line in lines if "-->" in line), "")
        match = _TIME_RE.fullmatch(time_line.strip())
        if match is None:
            parse_errors += 1
            continue

        start = _parse_time(match.group(1))
        end = _parse_time(match.group(2))
        text_lines = [
            line for line in lines if "-->" not in line and not line.strip().isdigit()
        ]
        text = "".join(text_lines).strip()
        duration = end - start

        if start < previous_end:
            overlaps += 1
        if duration < 0:
            reversed_ranges += 1
        if duration <= 0:
            zero_duration += 1
        if duration > 0 and len(text.replace(" ", "")) / duration > max_cps:
            high_cps += 1
        if any(len(line) > max_line_chars for line in text_lines):
            long_lines += 1

        previous_end = max(previous_end, end)

    ok = bool(blocks) and not any(
        (parse_errors, overlaps, reversed_ranges, zero_duration)
    )
    return SubtitleQualityReport(
        ok=ok,
        cues=len(blocks),
        overlaps=overlaps,
        reversed_ranges=reversed_ranges,
        zero_duration=zero_duration,
        high_cps=high_cps,
        long_lines=long_lines,
        parse_errors=parse_errors,
    )
