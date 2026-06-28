"""Manual review sample picker based on quality signals."""

from __future__ import annotations

from typing import Any


def _cps(item: dict[str, Any]) -> float:
    duration = float(item.get("end_sec", 0.0)) - float(item.get("start_sec", 0.0))
    return len(str(item.get("text", ""))) / duration if duration > 0 else 0.0


def pick_manual_review_segments(
    subtitles: list[dict[str, Any]],
    slow_chunks: list[dict[str, Any]] | None = None,
    *,
    max_items: int = 10,
) -> list[dict[str, Any]]:
    """Pick deterministic manual review samples from real quality signals."""
    slow_ids = {
        item.get("subtitle_id", item.get("chunk_id"))
        for item in (slow_chunks or [])
        if item.get("subtitle_id", item.get("chunk_id")) is not None
    }
    samples: list[dict[str, Any]] = []

    def add(item: dict[str, Any], reason: str) -> None:
        samples.append(
            {
                "subtitle_id": item.get("subtitle_id"),
                "start_sec": item.get("start_sec"),
                "end_sec": item.get("end_sec"),
                "text": item.get("text", ""),
                "reason": reason,
            }
        )

    for item in subtitles:
        if (
            item.get("alignment_confidence") is not None
            and float(item["alignment_confidence"]) < 0.7
        ):
            add(item, "低置信片段")
        if item.get("subtitle_id") in slow_ids:
            add(item, "慢速片段")
        if float(item.get("end_sec", 0.0)) <= float(item.get("start_sec", 0.0)):
            add(item, "时间轴异常片段")
        if _cps(item) > 20 or len(str(item.get("text", ""))) > 42:
            add(item, "CPS 过高片段")

    return samples[:max_items]
