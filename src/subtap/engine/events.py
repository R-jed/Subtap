"""Event logging system for pipeline execution observability."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional


class EventLogger:
    """Event-based logger that writes structured JSONL for pipeline observability."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = log_dir / "event.log.jsonl"
        self._events: list[dict] = []

    def log(
        self,
        stage: str,
        state: str,
        *,
        duration: float = 0.0,
        error: str = "",
        retry_count: int = 0,
        extra: Optional[dict] = None,
        git_commit_hash: str = "",
        workspace_clean: bool = True,
    ) -> None:
        """Log a pipeline event."""
        event = {
            "stage": stage,
            "state": state,
            "timestamp": time.time(),
            "duration": round(duration, 3),
            "error": error,
            "retry_count": retry_count,
            "git_commit_hash": git_commit_hash,
            "workspace_clean": workspace_clean,
        }
        if extra:
            event.update(extra)

        self._events.append(event)

        # Append to file
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def log_stage_start(self, stage: str) -> None:
        self.log(stage, "start")

    def log_stage_success(self, stage: str, duration: float, result: dict) -> None:
        self.log(
            stage,
            "success",
            duration=duration,
            extra={"result_keys": list(result.keys())},
        )

    def log_stage_failed(self, stage: str, error: str, retry_count: int = 0) -> None:
        self.log(stage, "failed", error=error, retry_count=retry_count)

    def log_stage_retry(self, stage: str, retry_count: int) -> None:
        self.log(stage, "retrying", retry_count=retry_count)

    def log_stage_skipped(self, stage: str, reason: str = "") -> None:
        self.log(stage, "skipped", extra={"reason": reason})

    def get_events(self, stage: Optional[str] = None) -> list[dict]:
        """Read events, optionally filtered by stage."""
        if not self.log_path.exists():
            return []
        events = []
        for line in self.log_path.read_text().strip().split("\n"):
            if line:
                event = json.loads(line)
                if stage is None or event.get("stage") == stage:
                    events.append(event)
        return events

    def clear(self) -> None:
        """Clear all events."""
        self._events.clear()
        if self.log_path.exists():
            self.log_path.unlink()
