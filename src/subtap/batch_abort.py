"""Batch abort mechanism — signal capture + abort file."""

from __future__ import annotations

import signal
import sys
from datetime import datetime, timezone
from pathlib import Path


class AbortController:
    """Controls batch task abortion via signal and file-based mechanism."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.abort_file = output_dir / ".abort"
        self._aborted = False
        self._original_handler = None

    def is_aborted(self) -> bool:
        """Check if abort has been requested."""
        if self._aborted:
            return True
        # Check abort file
        if self.abort_file.exists():
            self._aborted = True
            return True
        return False

    def abort(self) -> None:
        """Request abort."""
        self._aborted = True
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.abort_file.write_text(
            datetime.now(timezone.utc).isoformat(),
            encoding="utf-8",
        )

    def cleanup(self) -> None:
        """Remove abort file."""
        if self.abort_file.exists():
            self.abort_file.unlink(missing_ok=True)

    def install_signal_handler(self) -> None:
        """Install SIGINT handler for graceful abort."""
        def handler(signum, frame):
            self.abort()
            # Don't exit immediately — let pipeline check flag

        self._original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, handler)

    def restore_signal_handler(self) -> None:
        """Restore original signal handler."""
        if self._original_handler is not None:
            signal.signal(signal.SIGINT, self._original_handler)
