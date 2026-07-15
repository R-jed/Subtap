"""Phase 24: TUI performance state."""

import pytest

pytest.importorskip("textual", reason="textual is optional UI dependency")

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
            "chunk_timing_available": True,
            "asr_model": "asr_0.6b",
            "quantization": "q8",
        }
    )

    assert dashboard.performance_state["rtf"] == 0.72
    assert dashboard.performance_state["slow_chunks_total"] == 1
    assert dashboard.performance_state["model"] == "asr_0.6b"
    assert dashboard.performance_state["quantization"] == "q8"


def test_tui_marks_uncollected_chunk_timings_as_unknown():
    bus = EventBus()
    dashboard = PipelineDashboard(bus, PipelineProfiler(bus))

    dashboard.update_performance_metrics(
        {
            "slow_chunks": [],
            "chunk_timing_available": False,
        }
    )

    assert dashboard.performance_state["slow_chunks_total"] is None
