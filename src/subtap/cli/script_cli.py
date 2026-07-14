"""文稿匹配子命令组."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from subtap.cli._utils import _handle_error

script_app = typer.Typer(help="文稿匹配")


@script_app.command("match")
def script_match(
    timeline: Path = typer.Option(..., "--timeline", help="已有时间轴 JSONL"),
    script: Path = typer.Option(..., "--script", help="文稿文本文件"),
    output: Path = typer.Option(..., "--output", "-o", help="输出 JSONL"),
    follow_script_lines: bool = typer.Option(
        False,
        "--follow-script-lines/--keep-subtitle-lines",
        help="按文稿行数重排；默认保持原字幕段数和时间轴",
    ),
) -> None:
    """按顺序用文稿替换已有时间轴文本。"""
    from subtap.script.match import match_script_lines

    if not timeline.exists():
        _handle_error(f"时间轴文件不存在：{timeline}")
    if not script.exists():
        _handle_error(f"文稿文件不存在：{script}")

    segments = [
        json.loads(line)
        for line in timeline.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    script_text = script.read_text(encoding="utf-8")
    mode = "follow_script" if follow_script_lines else "correct_only"
    matched, report = match_script_lines(segments, script_text, mode=mode)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in matched) + "\n",
        encoding="utf-8",
    )
    report_path = output.with_name("matched_report.md")
    report_lines = [
        "# 文稿匹配报告",
        "",
        f"- 匹配模式：{mode}",
        f"- 已匹配：{report.matched}",
        f"- 已纠错：{report.corrected}",
        f"- 跳过：{report.skipped}",
        f"- 输出条数：{len(matched)}",
        "",
        report.message,
    ]
    if report.warnings:
        report_lines.append("")
        report_lines.append("## 警告")
        for w in report.warnings:
            report_lines.append(f"- {w}")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    typer.echo(f"✓ 已输出：{output}")
    typer.echo(f"▸ 文稿匹配报告：{report_path}")


@script_app.command("format")
def script_format(
    script: Path = typer.Option(..., "--script", help="文稿文本文件"),
) -> None:
    """清理文稿空行、标题和备注后输出到终端。"""
    from subtap.script.formatter import format_script

    if not script.exists():
        _handle_error(f"文稿文件不存在：{script}")
    for line in format_script(script.read_text(encoding="utf-8")):
        typer.echo(line)
