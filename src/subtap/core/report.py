"""Report generator for subtitle quality analysis."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def format_performance_summary(performance_metrics: dict) -> str:
    """Format user-readable performance and privacy summary."""
    external_text = "是" if performance_metrics["external_text_sent"] else "否"
    external_audio = "是" if performance_metrics["external_audio_sent"] else "否"
    return f"""
## 性能与隐私
- **RTF**：{performance_metrics["rtf"]:.2f}（RTF = 总处理耗时 / 音频时长，越低越快）
- **音频时长**：{performance_metrics["audio_duration_sec"]:.1f}s
- **总处理耗时**：{performance_metrics["total_runtime_sec"]:.1f}s
- **ASR 耗时**：{performance_metrics["asr_runtime_sec"]:.1f}s
- **对齐耗时**：{performance_metrics["align_runtime_sec"]:.1f}s
- **LLM 增强耗时**：{performance_metrics["enhancement_runtime_sec"]:.1f}s
- **慢速片段数量**：{len(performance_metrics["slow_chunks"])} 个
- **是否使用外部 LLM**：{external_text}
- **音频是否发送外部：{external_audio}**
- **文本是否发送外部：{external_text}**
- **模型策略**：任务结束后不会常驻模型，也不会默认预热。
"""


def format_output_contract_summary(
    output_files: list[str],
    manual_review_samples: list[dict],
) -> str:
    """Format output list and manual review suggestions for report.md."""
    lines = ["## 输出文件列表"]
    lines.extend(f"- {name}" for name in output_files)
    lines.append("")
    lines.append("## 建议人工抽检片段")
    if not manual_review_samples:
        lines.append("- 暂无需要优先抽检的片段。")
    else:
        for item in manual_review_samples:
            lines.append(
                f"- #{item.get('subtitle_id')}：{item.get('reason')}，"
                f"{item.get('start_sec', '')}-{item.get('end_sec', '')}s，"
                f"{item.get('text', '')}"
            )
    return "\n".join(lines) + "\n"


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
    performance_metrics: dict | None = None,
) -> str:
    """Generate a Markdown report for subtitle quality analysis.

    Args:
        quality_score: Overall quality score (0-100).
        error_count: Total errors detected.
        fixable_count: Errors that could be auto-fixed.
        fixed_count: Errors actually fixed.
        segment_count: Total subtitle segments.
        timings: Stage execution times.
        mode: Execution mode (fast/quality).
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

    if performance_metrics:
        report += format_performance_summary(performance_metrics)

    # Optimization suggestions
    report += """
## 优化建议
"""

    if quality_score < 80:
        report += "- 质量评分较低，建议使用 `--mode quality` 重新生成\n"

    if error_count > fixed_count:
        report += f"- 有 {error_count - fixed_count} 个错误未能自动修复，建议手动检查\n"

    if mode == "fast":
        report += "- 当前使用快速模式，切换到 `--mode quality` 可提升质量\n"

    if quality_score >= 90:
        report += "- 质量优秀，可直接用于剪辑软件\n"

    report += """
---
*由 Subtap 自动生成*
"""

    return report
