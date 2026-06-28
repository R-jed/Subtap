"""Phase 24: TUI performance state."""

from subtap.metrics.events import EventBus
from subtap.metrics.profiler import PipelineProfiler
from subtap.ui.dashboard import PipelineDashboard


def test_tui_performance_panel_state_updates():
    """Dashboard should store key performance metrics for display."""
    bus = EventBus()
    dashboard = PipelineDashboard(bus, PipelineProfiler(bus))

    dashboard.update_performance_metrics(
        {
            "rtf": 0.72,
            "total_runtime_sec": 7.2,
            "asr_runtime_sec": 3.0,
            "align_runtime_sec": 2.0,
            "enhancement_runtime_sec": 1.0,
            "slow_chunks": [{"chunk_id": 1}],
            "asr_model": "asr_0.6b",
            "quantization": "q8",
        }
    )

    assert dashboard.performance_state["rtf"] == 0.72
    assert dashboard.performance_state["slow_chunks_total"] == 1
    assert dashboard.performance_state["model"] == "asr_0.6b"
    assert dashboard.performance_state["quantization"] == "q8"
