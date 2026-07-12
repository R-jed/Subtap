"""Task 6: ManuscriptIndex 文稿索引测试."""

from __future__ import annotations

from subtap.core.manuscript_index import ManuscriptIndex


def test_manuscript_index_add_and_list(tmp_path):
    idx = ManuscriptIndex(tmp_path / "manuscripts" / "index.json")
    idx.add("讲稿.docx", "/Users/test/讲稿.docx")
    items = idx.list_all()
    assert len(items) == 1
    assert items[0]["name"] == "讲稿.docx"


def test_manuscript_index_updates_recent_use(tmp_path):
    idx = ManuscriptIndex(tmp_path / "manuscripts" / "index.json")
    idx.add("讲稿.docx", "/Users/test/讲稿.docx")
    idx.touch("讲稿.docx")
    items = idx.list_all()
    assert items[0]["recent_use_time"] is not None


def test_manuscript_index_removes(tmp_path):
    idx = ManuscriptIndex(tmp_path / "manuscripts" / "index.json")
    idx.add("讲稿.docx", "/Users/test/讲稿.docx")
    idx.remove("讲稿.docx")
    assert len(idx.list_all()) == 0


def test_manuscript_index_checks_file_exists(tmp_path):
    idx = ManuscriptIndex(tmp_path / "manuscripts" / "index.json")
    idx.add("讲稿.docx", "/nonexistent/讲稿.docx")
    items = idx.list_all()
    assert items[0]["exists"] is False


def test_manuscript_index_remove_nonexistent_returns_false(tmp_path):
    idx = ManuscriptIndex(tmp_path / "manuscripts" / "index.json")
    assert idx.remove("ghost.docx") is False


def test_manuscript_index_touch_nonexistent_raises(tmp_path):
    import pytest

    idx = ManuscriptIndex(tmp_path / "manuscripts" / "index.json")
    with pytest.raises(KeyError):
        idx.touch("ghost.docx")


def test_manuscript_index_persists_to_disk(tmp_path):
    path = tmp_path / "manuscripts" / "index.json"
    idx = ManuscriptIndex(path)
    idx.add("讲稿.docx", "/Users/test/讲稿.docx")

    # Reload from disk
    idx2 = ManuscriptIndex(path)
    items = idx2.list_all()
    assert len(items) == 1
    assert items[0]["name"] == "讲稿.docx"


def test_manuscript_index_add_duplicate_overwrites(tmp_path):
    idx = ManuscriptIndex(tmp_path / "manuscripts" / "index.json")
    idx.add("讲稿.docx", "/Users/test/讲稿.docx")
    idx.add("讲稿.docx", "/Users/test/other/讲稿.docx")
    items = idx.list_all()
    assert len(items) == 1
    assert items[0]["path"] == "/Users/test/other/讲稿.docx"
