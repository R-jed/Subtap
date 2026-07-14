"""Tests for batch module — manifest v2 structure."""

from __future__ import annotations

import json
from pathlib import Path


from subtap.batch import (
    build_manifest,
    make_item,
    parse_files,
    write_manifest,
    load_manifest,
    get_pending_items,
    get_failed_items,
)


class TestParseFiles:
    """Test parse_files function."""

    def test_parse_single_file(self):
        paths = parse_files("video.mp4")
        assert len(paths) == 1
        assert paths[0] == Path("video.mp4")

    def test_parse_multiple_files(self):
        paths = parse_files("a.mp4,b.mp4,c.mp4")
        assert len(paths) == 3
        assert paths == [Path("a.mp4"), Path("b.mp4"), Path("c.mp4")]

    def test_parse_with_spaces(self):
        paths = parse_files("a.mp4, b.mp4 , c.mp4")
        assert len(paths) == 3

    def test_parse_empty(self):
        paths = parse_files("")
        assert paths == []

    def test_parse_whitespace_only(self):
        paths = parse_files("  ,  ,  ")
        assert paths == []


class TestMakeItem:
    """Test make_item function."""

    def test_basic_item(self, tmp_path):
        item = make_item(Path("video.mp4"), tmp_path)
        assert item["input_path"] == "video.mp4"
        assert item["output_dir"] == str(tmp_path / "video_mp4")
        assert item["status"] == "pending"
        assert "stages" in item
        assert "duration" in item

    def test_item_with_stages(self, tmp_path):
        item = make_item(Path("video.mp4"), tmp_path)
        stages = item["stages"]
        assert "prepare" in stages
        assert "chunk" in stages
        assert "asr" in stages
        assert "clean" in stages
        assert "segment" in stages
        assert "align" in stages
        assert "export" in stages
        for stage in stages.values():
            assert stage["status"] == "pending"

    def test_filename_conflict(self, tmp_path):
        item1 = make_item(Path("a.mp4"), tmp_path)
        item2 = make_item(Path("a.wav"), tmp_path)
        assert item1["output_dir"] != item2["output_dir"]
        assert "a_mp4" in item1["output_dir"]
        assert "a_wav" in item2["output_dir"]


class TestBuildManifest:
    """Test build_manifest function."""

    def test_basic_manifest(self, tmp_path):
        items = [make_item(Path("a.mp4"), tmp_path)]
        manifest = build_manifest(tmp_path, "fast", items)
        assert manifest["version"] == 2
        # Pending items mean not all succeeded
        assert manifest["ok"] is False
        assert manifest["total"] == 1
        assert manifest["succeeded"] == 0
        assert manifest["failed"] == 0
        assert manifest["interrupted"] == 0
        assert manifest["mode"] == "fast"
        assert "params" in manifest
        assert "created_at" in manifest
        assert "items" in manifest

    def test_manifest_with_params(self, tmp_path):
        items = []
        params = {"enhance": "local", "translate_to": "en"}
        manifest = build_manifest(tmp_path, "fast", items, params=params)
        assert manifest["params"]["enhance"] == "local"
        assert manifest["params"]["translate_to"] == "en"

    def test_manifest_counts(self, tmp_path):
        items = [
            {"status": "succeeded"},
            {"status": "failed"},
            {"status": "interrupted"},
            {"status": "pending"},
        ]
        manifest = build_manifest(tmp_path, "fast", items)
        assert manifest["total"] == 4
        assert manifest["succeeded"] == 1
        assert manifest["failed"] == 1
        assert manifest["interrupted"] == 1
        assert manifest["ok"] is False


class TestWriteLoadManifest:
    """Test write_manifest and load_manifest functions."""

    def test_write_and_load(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        items = [make_item(Path("a.mp4"), tmp_path)]
        manifest = build_manifest(tmp_path, "fast", items)
        write_manifest(manifest_path, manifest)
        loaded = load_manifest(manifest_path)
        assert loaded["version"] == 2
        assert loaded["total"] == 1

    def test_atomic_write(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        items = [make_item(Path("a.mp4"), tmp_path)]
        manifest = build_manifest(tmp_path, "fast", items)
        write_manifest(manifest_path, manifest)
        assert manifest_path.exists()
        # No temp file should remain
        assert not list(tmp_path.glob("*.tmp"))


class TestResumeAndRetry:
    """Test resume and retry functionality."""

    def test_filter_pending_items(self, tmp_path):
        """Test filtering items for resume."""
        items = [
            {"input_path": "a.mp4", "status": "succeeded"},
            {"input_path": "b.mp4", "status": "failed"},
            {"input_path": "c.mp4", "status": "pending"},
        ]
        pending = get_pending_items(items)
        assert len(pending) == 2
        assert pending[0]["input_path"] == "b.mp4"
        assert pending[1]["input_path"] == "c.mp4"

    def test_filter_failed_items(self, tmp_path):
        """Test filtering items for retry-failed."""
        items = [
            {"input_path": "a.mp4", "status": "succeeded"},
            {"input_path": "b.mp4", "status": "failed"},
            {"input_path": "c.mp4", "status": "interrupted"},
        ]
        failed = get_failed_items(items)
        assert len(failed) == 1
        assert failed[0]["input_path"] == "b.mp4"

    def test_resume_manifest(self, tmp_path):
        """Test loading manifest for resume."""
        manifest_path = tmp_path / "manifest.json"
        manifest = {
            "version": 2,
            "items": [
                {
                    "input_path": "a.mp4",
                    "status": "succeeded",
                    "output_dir": str(tmp_path / "a_mp4"),
                },
                {
                    "input_path": "b.mp4",
                    "status": "failed",
                    "output_dir": str(tmp_path / "b_mp4"),
                },
            ],
        }
        manifest_path.write_text(json.dumps(manifest))
        loaded = load_manifest(manifest_path)
        pending = get_pending_items(loaded["items"])
        assert len(pending) == 1
