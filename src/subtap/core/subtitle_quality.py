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


@dataclass(frozen=True)
class SRTCue:
    """Structurally valid SRT cue."""

    index: int
    start: float
    end: float
    text_lines: tuple[str, ...]

    @property
    def text(self) -> str:
        return "".join(self.text_lines).strip()


_TIME_RE = re.compile(r"(\d\d:\d\d:\d\d,\d\d\d) --> (\d\d:\d\d:\d\d,\d\d\d)")


def _parse_time(value: str) -> float:
    h, m, rest = value.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _parse_srt(content: str) -> tuple[list[str], list[SRTCue], int]:
    blocks = [
        block.strip()
        for block in re.split(r"\r?\n\r?\n", content.strip())
        if block.strip()
    ]
    cues: list[SRTCue] = []
    parse_errors = 0
    for expected_index, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        match = _TIME_RE.fullmatch(lines[1].strip()) if len(lines) >= 2 else None
        text_lines = tuple(lines[2:]) if len(lines) >= 3 else ()
        invalid = (
            not lines
            or lines[0].strip() != str(expected_index)
            or match is None
            or not any(line.strip() for line in text_lines)
        )
        if invalid:
            parse_errors += 1
        if match is None or not any(line.strip() for line in text_lines):
            continue
        cues.append(
            SRTCue(
                index=expected_index,
                start=_parse_time(match.group(1)),
                end=_parse_time(match.group(2)),
                text_lines=text_lines,
            )
        )
    return blocks, cues, parse_errors


def parse_srt_cues(content: str) -> list[SRTCue]:
    """Parse a structurally valid SRT document or fail explicitly."""
    blocks, cues, parse_errors = _parse_srt(content)
    if not blocks or parse_errors:
        raise ValueError(f"SRT 结构无效：{parse_errors or 1} 个错误")
    return cues


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
    blocks, cues, parse_errors = _parse_srt(content)
    previous_end = -1.0
    overlaps = 0
    reversed_ranges = 0
    zero_duration = 0
    high_cps = 0
    long_lines = 0
    for cue in cues:
        duration = cue.end - cue.start

        if cue.start < previous_end:
            overlaps += 1
        if duration < 0:
            reversed_ranges += 1
        if duration <= 0:
            zero_duration += 1
        if duration > 0 and len(cue.text.replace(" ", "")) / duration > max_cps:
            high_cps += 1
        if any(len(line) > max_line_chars for line in cue.text_lines):
            long_lines += 1

        previous_end = max(previous_end, cue.end)

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
