"""Phase 25: report output and sampling sections."""

from subtap.core.report import format_output_contract_summary


def test_report_contains_privacy_performance_outputs_and_review_samples():
    """Report summary should include outputs and manual review samples."""
    report = format_output_contract_summary(
        output_files=["final.srt", "final.vtt", "final.json", "final.tsv"],
        manual_review_samples=[
            {"subtitle_id": 1, "reason": "CPS 过高", "text": "很长的字幕文本"}
        ],
    )

    assert "输出文件列表" in report
    assert "final.srt" in report
    assert "建议人工抽检片段" in report
    assert "CPS 过高" in report
