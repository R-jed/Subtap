"""Script formatting and simple sequential matching."""

from __future__ import annotations


def _is_note_line(line: str) -> bool:
    return (
        line.startswith("#")
        or line.startswith("//")
        or (line.startswith("【") and line.endswith("】"))
        or (line.startswith("[") and line.endswith("]"))
    )


def format_script(text: str, remove_notes: bool = True) -> list[str]:
    """Return non-empty script lines in order."""
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if remove_notes and _is_note_line(line):
            continue
        lines.append(line)
    return lines


def match_script_lines(
    segments: list[dict],
    lines: list[str],
    mode: str = "keep_subtitle",
) -> list[dict]:
    """Replace segment text with script lines by order while preserving timing."""
    if mode not in {"keep_subtitle", "follow_script"}:
        raise ValueError(f"未知文稿匹配模式：{mode}")

    if mode == "follow_script":
        if not segments:
            return []
        result = []
        for index, line in enumerate(lines):
            source = segments[index] if index < len(segments) else segments[-1]
            item = dict(source)
            item["text"] = line
            result.append(item)
        return result

    result = []
    for index, segment in enumerate(segments):
        item = dict(segment)
        if index < len(lines):
            item["text"] = lines[index]
        result.append(item)
    return result


def build_match_report(
    *,
    segments_total: int,
    script_lines_total: int,
    output_total: int,
    mode: str,
) -> str:
    """Build a small user-facing manuscript match report."""
    matched = min(segments_total, script_lines_total)
    remaining_script = max(0, script_lines_total - segments_total)
    remaining_segments = max(0, segments_total - script_lines_total)
    return "\n".join(
        [
            "# 文稿匹配报告",
            "",
            f"- 匹配模式：{mode}",
            f"- 原时间轴条数：{segments_total}",
            f"- 文稿有效行数：{script_lines_total}",
            f"- 输出条数：{output_total}",
            f"- 已匹配：{matched}",
            f"- 剩余文稿行：{remaining_script}",
            f"- 剩余字幕段：{remaining_segments}",
            "",
        ]
    )
