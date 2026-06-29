"""Tests for batch abort mechanism."""

from __future__ import annotations

import signal
import os
from pathlib import Path

import pytest

from subtap.batch_abort import AbortController


class TestAbortController:
    """Test AbortController class."""

    def test_initial_state(self, tmp_path):
        controller = AbortController(tmp_path)
        assert controller.is_aborted() is False

    def test_abort(self, tmp_path):
        controller = AbortController(tmp_path)
        controller.abort()
        assert controller.is_aborted() is True
        assert controller.abort_file.exists()

    def test_abort_file_content(self, tmp_path):
        controller = AbortController(tmp_path)
        controller.abort()
        content = controller.abort_file.read_text()
        assert len(content) > 0

    def test_cleanup(self, tmp_path):
        controller = AbortController(tmp_path)
        controller.abort()
        assert controller.abort_file.exists()
        controller.cleanup()
        assert not controller.abort_file.exists()

    def test_check_existing_abort(self, tmp_path):
        # Create abort file manually
        abort_file = tmp_path / ".abort"
        abort_file.write_text("manual abort")
        controller = AbortController(tmp_path)
        assert controller.is_aborted() is True

    def test_signal_handler(self, tmp_path):
        controller = AbortController(tmp_path)
        controller.install_signal_handler()
        # Simulate SIGINT
        os.kill(os.getpid(), signal.SIGINT)
        # Should not raise, should set abort flag
        assert controller.is_aborted() is True
        # Restore handler
        controller.restore_signal_handler()
