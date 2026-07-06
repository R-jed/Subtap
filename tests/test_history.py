# tests/test_history.py
import json
from subtap.ui.history import HistoryScanner, HistoryRecord


class TestHistoryScanner:
    def test_scan_empty_dir(self, tmp_path):
        scanner = HistoryScanner(tmp_path)
        records = scanner.scan()
        assert records == []

    def test_scan_with_records(self, tmp_path):
        record_dir = tmp_path / "2026-07-06_14-30-00"
        record_dir.mkdir()
        meta = {
            "input_path": "/test/audio.mp3",
            "duration_sec": 1920,
            "output_path": "/test/output.srt",
            "status": "completed",
        }
        (record_dir / "meta.json").write_text(json.dumps(meta))
        scanner = HistoryScanner(tmp_path)
        records = scanner.scan()
        assert len(records) == 1
        assert records[0].input_name == "audio.mp3"
        assert records[0].duration_str == "32:00"

    def test_scan_ignores_non_dirs(self, tmp_path):
        (tmp_path / "file.txt").write_text("not a record")
        scanner = HistoryScanner(tmp_path)
        assert scanner.scan() == []

    def test_scan_ignores_dirs_without_meta(self, tmp_path):
        (tmp_path / "no-meta").mkdir()
        scanner = HistoryScanner(tmp_path)
        assert scanner.scan() == []

    def test_scan_sorts_by_time_desc(self, tmp_path):
        for ts in ["2026-07-04_10-00-00", "2026-07-06_14-00-00", "2026-07-05_12-00-00"]:
            d = tmp_path / ts
            d.mkdir()
            (d / "meta.json").write_text(json.dumps({
                "input_path": f"/test/{ts}.mp3",
                "duration_sec": 60,
                "output_path": "/test/out.srt",
                "status": "completed",
            }))
        scanner = HistoryScanner(tmp_path)
        records = scanner.scan()
        assert records[0].timestamp > records[-1].timestamp

    def test_duration_format(self, tmp_path):
        d = tmp_path / "2026-07-06_14-00-00"
        d.mkdir()
        (d / "meta.json").write_text(json.dumps({
            "input_path": "/test/a.mp3",
            "duration_sec": 3725,
            "output_path": "/test/out.srt",
            "status": "completed",
        }))
        scanner = HistoryScanner(tmp_path)
        records = scanner.scan()
        assert records[0].duration_str == "1:02:05"


class TestHistoryRecord:
    def test_failed_status(self):
        r = HistoryRecord(
            timestamp="2026-07-06_14-00-00",
            input_path="/test/a.mp3",
            duration_sec=60,
            output_path="",
            status="failed",
            input_name="a.mp3",
            duration_str="1:00",
        )
        assert r.is_failed
        assert not r.is_completed
