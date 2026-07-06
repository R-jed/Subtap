"""文件/文件夹选择对话框。"""
from dataclasses import dataclass
from pathlib import Path


AUDIO_VIDEO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma",
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
}


@dataclass
class FileItem:
    name: str
    path: Path
    is_dir: bool


class FilePicker:
    def __init__(self, path: Path, extensions: set[str] | None = None, show_dirs: bool = True, show_hidden: bool = False):
        self.path = path
        self.extensions = extensions or AUDIO_VIDEO_EXTENSIONS
        self.show_dirs = show_dirs
        self.show_hidden = show_hidden

    def list_items(self) -> list[FileItem]:
        items: list[FileItem] = []
        if not self.path.exists():
            return items
        for entry in sorted(self.path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if not self.show_hidden and entry.name.startswith("."):
                continue
            if entry.is_dir():
                if self.show_dirs:
                    items.append(FileItem(name=entry.name, path=entry, is_dir=True))
            elif entry.suffix.lower() in self.extensions:
                items.append(FileItem(name=entry.name, path=entry, is_dir=False))
        return items

    def parent(self) -> "FilePicker":
        parent = self.path.parent
        if parent == self.path:
            return self
        return FilePicker(parent, self.extensions, self.show_dirs, self.show_hidden)

    def enter(self, name: str) -> "FilePicker":
        return FilePicker(self.path / name, self.extensions, self.show_dirs, self.show_hidden)
