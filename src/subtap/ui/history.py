"""转录历史记录扫描。"""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HistoryRecord:
    timestamp: str
    input_path: str
    duration_sec: float
    output_path: str
    status: str
    input_name: str
    duration_str: str

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"


def format_duration(seconds: float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class HistoryScanner:
    def __init__(self, history_dir: Path):
        self.history_dir = history_dir

    def scan(self) -> list[HistoryRecord]:
        if not self.history_dir.exists():
            return []
        records: list[HistoryRecord] = []
        for entry in sorted(self.history_dir.iterdir(), reverse=True):
            if not entry.is_dir():
                continue
            meta_file = entry / "meta.json"
            if not meta_file.exists():
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                input_path = meta.get("input_path", "")
                records.append(HistoryRecord(
                    timestamp=entry.name,
                    input_path=input_path,
                    duration_sec=meta.get("duration_sec", 0),
                    output_path=meta.get("output_path", ""),
                    status=meta.get("status", "unknown"),
                    input_name=Path(input_path).name if input_path else "未知",
                    duration_str=format_duration(meta.get("duration_sec", 0)),
                ))
            except (json.JSONDecodeError, KeyError):
                continue
        return records
