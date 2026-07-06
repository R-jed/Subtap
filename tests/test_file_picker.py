# tests/test_file_picker.py
from pathlib import Path

from subtap.ui.file_picker import FilePicker


class TestFilePicker:
    def test_list_files_in_dir(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"")
        (tmp_path / "b.wav").write_bytes(b"")
        (tmp_path / "c.txt").write_bytes(b"")
        picker = FilePicker(tmp_path, extensions={".mp3", ".wav"})
        items = picker.list_items()
        names = [i.name for i in items]
        assert "a.mp3" in names
        assert "b.wav" in names
        assert "c.txt" not in names

    def test_list_dirs(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.mp3").write_bytes(b"")
        picker = FilePicker(tmp_path, show_dirs=True)
        items = picker.list_items()
        names = [i.name for i in items]
        assert "subdir" in names
        assert "file.mp3" in names

    def test_parent_navigation(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        picker = FilePicker(sub)
        parent = picker.parent()
        assert parent.path == tmp_path

    def test_root_parent_returns_self(self):
        picker = FilePicker(Path("/"))
        parent = picker.parent()
        assert parent.path == Path("/")

    def test_enter_dir(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        picker = FilePicker(tmp_path)
        child = picker.enter("sub")
        assert child.path == sub

    def test_default_extensions(self):
        picker = FilePicker(Path("/"))
        assert ".mp3" in picker.extensions
        assert ".wav" in picker.extensions
        assert ".txt" not in picker.extensions
