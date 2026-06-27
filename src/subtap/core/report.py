"""Report generator for subtitle quality analysis."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def generate_report(
    quality_score: float,
    error_count: int,
    fixable_count: int,
    fixed_count: int,
    segment_count: int,
    timings: dict[str, float],
    mode: str,
    input_file: Path,
    output_format: str,
    glossary_terms: int = 0,
    glossary_replacements: int = 0,
) -> str:
    """Generate a Markdown report for subtitle quality analysis.

    Args:
        quality_score: Overall quality score (0-100).
        error_count: Total errors detected.
        fixable_count: Errors that could be auto-fixed.
        fixed_count: Errors actually fixed.
        segment_count: Total subtitle segments.
        timings: Stage execution times.
        mode: Execution mode (fast/quality/hybrid).
        input_file: Input media file path.
        output_format: Output format (srt/vtt/json).
        glossary_terms: Number of glossary terms used.
        glossary_replacements: Number of replacements applied.

    Returns:
        Markdown report string.
    """
    total_time = sum(timings.values())

    # Quality rating
    if quality_score >= 90:
        quality_rating = "优秀"
    elif quality_score >= 80:
        quality_rating = "良好"
    elif quality_score >= 70:
        quality_rating = "一般"
    else:
        quality_rating = "需要优化"

    # Mode description
    mode_desc = {
        "fast": "快速模式（跳过清洗和对齐）",
        "quality": "质量模式（完整流程 + 大模型）",
        "hybrid": "混合模式（平衡速度和质量）",
    }.get(mode, mode)

    report = f"""# Subtap 字幕生成报告

## 任务信息
- **输入文件**：{input_file.name}
- **执行模式**：{mode_desc}
- **输出格式**：{output_format.upper()}
- **总耗时**：{total_time:.1f}s
- **生成时间**：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 质量评分：{quality_score:.0f}/100（{quality_rating}）

## 字幕统计
- **总字幕数**：{segment_count} 条
- **错误总数**：{error_count} 个
- **可修复**：{fixable_count} 个
- **已修复**：{fixed_count} 个

## 阶段耗时
"""

    # Add timing details
    stage_names = {
        "prepare": "音频准备",
        "chunk": "音频切分",
        "asr": "语音识别",
        "clean": "文本清洗",
        "segment": "智能断句",
        "align": "时间轴对齐",
        "export": "字幕导出",
    }

    for stage, duration in timings.items():
        stage_cn = stage_names.get(stage, stage)
        report += f"- {stage_cn}：{duration:.1f}s\n"

    # Glossary section
    if glossary_terms > 0:
        report += f"""
## 术语表使用
- **术语数量**：{glossary_terms} 个
- **替换次数**：{glossary_replacements} 次
"""

    # Optimization suggestions
    report += """
## 优化建议
"""

    if quality_score < 80:
        report += "- 质量评分较低，建议使用 `--mode quality` 重新生成\n"

    if error_count > fixed_count:
        report += f"- 有 {error_count - fixed_count} 个错误未能自动修复，建议手动检查\n"

    if mode == "fast":
        report += "- 当前使用快速模式，切换到 `--mode hybrid` 可提升质量\n"

    if quality_score >= 90:
        report += "- 质量优秀，可直接用于剪辑软件\n"

    report += """
---
*由 Subtap 自动生成*
"""

    return report
