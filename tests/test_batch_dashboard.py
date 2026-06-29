"""Tests for batch dashboard."""

from __future__ import annotations

import pytest

from subtap.batch_dashboard import (
    BatchDashboard,
    BatchItem,
    BatchState,
)


class TestBatchItem:
    """Test BatchItem class."""

    def test_default_item(self):
        item = BatchItem(
            input_path="/path/to/video.mp4",
            output_dir="/path/to/output",
        )
        assert item.status == "pending"
        assert item.progress == 0
        assert item.duration == 0.0

    def test_item_status(self):
        item = BatchItem(input_path="/path/to/video.mp4")
        item.status = "running"
        item.progress = 50
        assert item.status == "running"
        assert item.progress == 50


class TestBatchState:
    """Test BatchState class."""

    def test_initial_state(self):
        state = BatchState(total=5)
        assert state.total == 5
        assert state.current_index == 0
        assert state.current_file is None

    def test_state_progress(self):
        state = BatchState(total=5)
        state.current_index = 2
        state.current_file = "video.mp4"
        assert state.current_index == 2
        assert state.current_file == "video.mp4"


class TestBatchDashboard:
    """Test BatchDashboard class."""

    def test_dashboard_creation(self):
        dashboard = BatchDashboard()
        assert dashboard is not None
