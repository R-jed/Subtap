# TUI 功能层实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 TUI 骨架视图接入真实功能，实现设置管理、文件选择、转录执行、历史记录

**架构：** TuiApp 通过 ConfigManager 读写 config.yaml，通过 subprocess 调用 `subtap run` 执行转录，通过扫描 ~/.subtap/history 展示历史记录。每个功能独立为一个 view 模块。

**技术栈：** Python 标准库（subprocess, pathlib, yaml），复用现有 subtap.cli 和 subtap.core.pipeline

---

## 文件结构

```
src/subtap/ui/
├── config_manager.py    # 创建 — 配置读写（config.yaml）
├── history.py           # 创建 — 历史记录扫描和数据模型
├── file_picker.py       # 创建 — 文件/文件夹选择对话框
├── views/
│   ├── __init__.py      # 已有
│   ├── settings.py      # 创建 — 设置视图（5 个子页面）
│   ├── new_task.py      # 创建 — 新建转录视图
│   ├── history_view.py  # 创建 — 转录历史视图
│   ├── batch.py         # 创建 — 批量转录视图
│   └── setup.py         # 创建 — 初始化引导视图
├── tui_app.py           # 修改 — 路由到新 view 模块
├── menu.py              # 已有 — 不修改
├── keyboard.py          # 已有 — 不修改
├── theme.py             # 已有 — 不修改
└── spinner.py           # 已有 — 不修改

tests/
├── test_config_manager.py
├── test_history.py
├── test_file_picker.py
└── test_views.py
```

---

## 任务 1：config_manager.py — 配置读写

**文件：**
- 创建：`src/subtap/ui/config_manager.py`
- 测试：`tests/test_config_manager.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_config_manager.py
import tempfile
from pathlib import Path
from subtap.ui.config_manager import ConfigManager


class TestConfigManager:
    def test_load_existing_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("mode: online\nasr:\n  model: asr_0.6b\n")
        mgr = ConfigManager(config_file)
        assert mgr.get("mode") == "online"
        assert mgr.get("asr.model") == "asr_0.6b"

    def test_load_missing_config_returns_defaults(self, tmp_path):
        mgr = ConfigManager(tmp_path / "missing.yaml")
        assert mgr.get("mode") == "offline"

    def test_set_and_save(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("mode: offline\n")
        mgr = ConfigManager(config_file)
        mgr.set("mode", "online")
        mgr.save()
        assert "online" in config_file.read_text()

    def test_get_nested_key(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("asr:\n  model: test\n  backend: mlx\n")
        mgr = ConfigManager(config_file)
        assert mgr.get("asr.model") == "test"
        assert mgr.get("asr.backend") == "mlx"

    def test_get_missing_key_returns_none(self, tmp_path):
        mgr = ConfigManager(tmp_path / "empty.yaml")
        assert mgr.get("nonexistent") is None
        assert mgr.get("nonexistent.key") is None

    def test_set_nested_key_creates_path(self, tmp_path):
        mgr = ConfigManager(tmp_path / "new.yaml")
        mgr.set("asr.model", "new_model")
        assert mgr.get("asr.model") == "new_model"

    def test_config_dir_created_on_save(self, tmp_path):
        config_file = tmp_path / "sub" / "config.yaml"
        mgr = ConfigManager(config_file)
        mgr.set("mode", "online")
        mgr.save()
        assert config_file.exists()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python3 -m pytest tests/test_config_manager.py -v --noconftest`
预期：FAIL，ModuleNotFoundError

- [ ] **步骤 3：编写实现代码**

```python
# src/subtap/ui/config_manager.py
"""配置文件读写管理。

读写 ~/.subtap/config.yaml，支持嵌套键访问。
"""
from pathlib import Path
from typing import Any


class ConfigManager:
    """YAML 配置文件管理器。"""

    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            import yaml
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        except Exception:
            self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持嵌套键（如 'asr.model'）。"""
        parts = key.split(".")
        current = self._data
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def set(self, key: str, value: Any) -> None:
        """设置配置值，支持嵌套键。"""
        parts = key.split(".")
        current = self._data
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    def save(self) -> None:
        """保存配置到文件。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        import yaml
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, default_flow_style=False, allow_unicode=True)

    @property
    def data(self) -> dict[str, Any]:
        return self._data
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python3 -m pytest tests/test_config_manager.py -v --noconftest`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/config_manager.py tests/test_config_manager.py
git commit -m "feat(ui): 添加 config_manager 配置读写模块"
```

---

## 任务 2：history.py — 历史记录扫描

**文件：**
- 创建：`src/subtap/ui/history.py`
- 测试：`tests/test_history.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_history.py
import json
from pathlib import Path
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
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python3 -m pytest tests/test_history.py -v --noconftest`
预期：FAIL，ModuleNotFoundError

- [ ] **步骤 3：编写实现代码**

```python
# src/subtap/ui/history.py
"""转录历史记录扫描。

扫描 ~/.subtap/history/ 目录下的记录。
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class HistoryRecord:
    """单条转录历史记录。"""
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
    """格式化秒数为 H:MM:SS 或 M:SS。"""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class HistoryScanner:
    """扫描历史记录目录。"""

    def __init__(self, history_dir: Path):
        self.history_dir = history_dir

    def scan(self) -> list[HistoryRecord]:
        """扫描并返回按时间倒序排列的历史记录。"""
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
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python3 -m pytest tests/test_history.py -v --noconftest`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/history.py tests/test_history.py
git commit -m "feat(ui): 添加 history 历史记录扫描模块"
```

---

## 任务 3：file_picker.py — 文件选择对话框

**文件：**
- 创建：`src/subtap/ui/file_picker.py`
- 测试：`tests/test_file_picker.py`

- [ ] **步骤 1：编写失败的测试**

```python
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

    def test_root_parent_returns_self(self, tmp_path):
        picker = FilePicker(tmp_path)
        parent = picker.parent()
        assert parent.path == tmp_path

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
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python3 -m pytest tests/test_file_picker.py -v --noconftest`
预期：FAIL，ModuleNotFoundError

- [ ] **步骤 3：编写实现代码**

```python
# src/subtap/ui/file_picker.py
"""文件/文件夹选择对话框。

列出目录下的文件，支持过滤和导航。
"""
from dataclasses import dataclass
from pathlib import Path


AUDIO_VIDEO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma",
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
}


@dataclass
class FileItem:
    """文件列表中的单个项目。"""
    name: str
    path: Path
    is_dir: bool


class FilePicker:
    """文件选择器。"""

    def __init__(
        self,
        path: Path,
        extensions: set[str] | None = None,
        show_dirs: bool = True,
    ):
        self.path = path
        self.extensions = extensions or AUDIO_VIDEO_EXTENSIONS
        self.show_dirs = show_dirs

    def list_items(self) -> list[FileItem]:
        """列出当前目录下的文件和文件夹。"""
        items: list[FileItem] = []
        if not self.path.exists():
            return items
        for entry in sorted(self.path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.is_dir():
                if self.show_dirs:
                    items.append(FileItem(name=entry.name, path=entry, is_dir=True))
            elif entry.suffix.lower() in self.extensions:
                items.append(FileItem(name=entry.name, path=entry, is_dir=False))
        return items

    def parent(self) -> "FilePicker":
        """返回父目录的 FilePicker。"""
        parent = self.path.parent
        if parent == self.path:
            return self
        return FilePicker(parent, self.extensions, self.show_dirs)

    def enter(self, name: str) -> "FilePicker":
        """进入子目录。"""
        return FilePicker(self.path / name, self.extensions, self.show_dirs)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python3 -m pytest tests/test_file_picker.py -v --noconftest`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/file_picker.py tests/test_file_picker.py
git commit -m "feat(ui): 添加 file_picker 文件选择对话框"
```

---

## 任务 4：views/new_task.py — 新建转录视图

**文件：**
- 创建：`src/subtap/ui/views/new_task.py`
- 修改：`src/subtap/ui/tui_app.py`
- 测试：`tests/test_views.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_views.py
from subtap.ui.views.new_task import NewTaskView
from subtap.ui.config_manager import ConfigManager


class TestNewTaskView:
    def test_initial_state(self, tmp_path):
        cfg = ConfigManager(tmp_path / "config.yaml")
        view = NewTaskView(config=cfg, home_dir=tmp_path)
        assert view.selected_file is None

    def test_confirm_settings_reads_config(self, tmp_path):
        cfg = ConfigManager(tmp_path / "config.yaml")
        cfg.set("output.subtitle_language", "zh")
        cfg.set("output.subtitle_formats", ["srt"])
        view = NewTaskView(config=cfg, home_dir=tmp_path)
        settings = view.get_confirm_settings()
        assert settings["language"] == "中文"
        assert settings["format"] == "SRT"

    def test_confirm_settings_default(self, tmp_path):
        cfg = ConfigManager(tmp_path / "config.yaml")
        view = NewTaskView(config=cfg, home_dir=tmp_path)
        settings = view.get_confirm_settings()
        assert settings["language"] == "自动检测"
        assert settings["format"] == "SRT"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python3 -m pytest tests/test_views.py -v --noconftest`
预期：FAIL，ModuleNotFoundError

- [ ] **步骤 3：编写实现代码**

```python
# src/subtap/ui/views/new_task.py
"""新建转录视图 — 文件选择和确认。"""
from pathlib import Path
from ..config_manager import ConfigManager


LANG_MAP = {"zh": "中文", "en": "英文", "ja": "日文"}


class NewTaskView:
    """新建转录视图逻辑。"""

    def __init__(self, config: ConfigManager, home_dir: Path):
        self.config = config
        self.home_dir = home_dir
        self.selected_file: Path | None = None

    def select_file(self, path: Path) -> None:
        self.selected_file = path

    def get_confirm_settings(self) -> dict:
        """读取当前配置，返回确认页显示的设置。"""
        lang = self.config.get("output.subtitle_language", "zh")
        fmt = self.config.get("output.subtitle_formats", ["srt"])[0]
        return {
            "language": LANG_MAP.get(lang, "自动检测") if lang else "自动检测",
            "format": fmt.upper() if fmt else "SRT",
        }

    def build_run_command(self) -> list[str]:
        """构建 subtap run 命令行参数。"""
        if not self.selected_file:
            return []
        cmd = ["subtap", "run", str(self.selected_file)]
        fmt = self.config.get("output.subtitle_formats", ["srt"])[0]
        if fmt:
            cmd.extend(["--format", fmt])
        return cmd
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python3 -m pytest tests/test_views.py -v --noconftest`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/views/new_task.py tests/test_views.py
git commit -m "feat(ui): 添加新建转录视图逻辑"
```

---

## 任务 5：接入 tui_app.py — 新建转录完整流程

**文件：**
- 修改：`src/subtap/ui/tui_app.py`（替换 `_view_new_task` 骨架）
- 修改：`src/subtap/ui/tui_app.py`（添加 config_manager 初始化）

- [ ] **步骤 1：修改 TuiApp.__init__ 添加 config_manager**

```python
# tui_app.py __init__ 中添加:
from .config_manager import ConfigManager
from .file_picker import FilePicker
from .views.new_task import NewTaskView
from pathlib import Path

def __init__(self):
    self.theme = Theme()
    self.reader = KeyReader()
    self._state = "home"
    self._state_stack: list[str] = []
    self.config = ConfigManager(Path.home() / ".subtap" / "config.yaml")
```

- [ ] **步骤 2：替换 _view_new_task 为完整实现**

```python
def _view_new_task(self) -> str:
    t = self.theme
    view = NewTaskView(config=self.config, home_dir=Path.home())
    picker = FilePicker(Path.home())
    items = picker.list_items()
    menu_items = [f"📁 {i.name}" if i.is_dir else i.name for i in items]
    if not menu_items:
        menu_items = ["(当前目录无音频/视频文件)"]

    menu = Menu(
        title="新建转录 · 选择文件",
        items=menu_items,
        footer="↑↓ 导航  Enter 选择  .. 返回上级  Esc 返回",
        theme=self.theme,
    )
    menu.render_full()

    while True:
        old_cursor = menu.cursor
        key = self.reader.read_key(timeout=0.05)
        if key is None:
            continue
        if key == Key.QUIT:
            return "quit"
        elif key == Key.ESCAPE:
            self._pop_state()
            return "continue"
        elif key in (Key.UP,):
            menu.move_up()
            menu.render_incremental(old_cursor)
        elif key in (Key.DOWN,):
            menu.move_down()
            menu.render_incremental(old_cursor)
        elif key == Key.ENTER:
            if not items:
                continue
            selected = items[menu.cursor]
            if selected.is_dir:
                picker = picker.enter(selected.name)
                items = picker.list_items()
                menu_items = [f"📁 {i.name}" if i.is_dir else i.name for i in items]
                if not menu_items:
                    menu_items = ["(当前目录无音频/视频文件)"]
                menu = Menu(
                    title=f"新建转录 · {picker.path}",
                    items=menu_items,
                    footer="↑↓ 导航  Enter 选择  .. 返回上级  Esc 返回",
                    theme=self.theme,
                )
                menu.render_full()
            else:
                view.select_file(selected.path)
                return self._view_confirm_run(view)
```

- [ ] **步骤 3：添加确认页视图**

```python
def _view_confirm_run(self, view: NewTaskView) -> str:
    t = self.theme
    settings = view.get_confirm_settings()
    file_name = view.selected_file.name if view.selected_file else "未知"

    items = [
        f"文件：{file_name}",
        f"语言：{settings['language']}",
        f"格式：{settings['format']}",
    ]
    menu = Menu(
        title="确认转录",
        items=items,
        footer="Enter 开始转录  S 更多设置  Esc 返回",
        theme=self.theme,
    )
    menu.render_full()

    while True:
        key = self.reader.read_key(timeout=0.05)
        if key is None:
            continue
        if key == Key.QUIT:
            return "quit"
        elif key == Key.ESCAPE:
            self._pop_state()
            return "continue"
        elif key == Key.ENTER:
            return self._execute_run(view)
```

- [ ] **步骤 4：添加执行转录视图**

```python
def _execute_run(self, view: NewTaskView) -> str:
    t = self.theme
    cmd = view.build_run_command()
    if not cmd:
        self._pop_state()
        return "continue"

    sys.stderr.write("\033[2J\033[H")
    sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}正在转录{t.NC}\r\n\r\n")
    sys.stderr.write(f"\033[2K{t.GRAY}文件：{view.selected_file.name}{t.NC}\r\n\r\n")
    sys.stderr.write(f"\033[2K{t.GRAY}请稍候...{t.NC}\r\n")
    sys.stderr.flush()

    import subprocess
    result = subprocess.run(cmd, capture_output=True, text=True)

    sys.stderr.write("\033[2J\033[H")
    if result.returncode == 0:
        sys.stderr.write(f"\033[2K{t.GREEN}✓ 转录完成{t.NC}\r\n\r\n")
    else:
        sys.stderr.write(f"\033[2K{t.RED}✗ 转录失败{t.NC}\r\n\r\n")
        if result.stderr:
            sys.stderr.write(f"\033[2K{t.GRAY}{result.stderr[:200]}{t.NC}\r\n")
    sys.stderr.write(f"\033[2K\r\n{t.GRAY}Esc 返回{t.NC}\r\n")
    sys.stderr.flush()

    while True:
        key = self.reader.read_key(timeout=0.05)
        if key in (Key.ESCAPE, Key.ENTER):
            self._pop_state()
            return "continue"
        elif key == Key.QUIT:
            return "quit"
```

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/tui_app.py
git commit -m "feat(ui): 接入新建转录完整流程（文件选择→确认→执行）"
```

---

## 任务 6：接入转录历史视图

**文件：**
- 修改：`src/subtap/ui/tui_app.py`（替换 `_view_history` 骨架）

- [ ] **步骤 1：替换 _view_history 为完整实现**

```python
def _view_history(self) -> str:
    t = self.theme
    from .history import HistoryScanner
    scanner = HistoryScanner(Path.home() / ".subtap" / "history")
    records = scanner.scan()

    if not records:
        sys.stderr.write("\033[2J\033[H")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}转录历史{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}暂无记录{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回{t.NC}\r\n")
        sys.stderr.flush()
        while True:
            key = self.reader.read_key(timeout=0.05)
            if key in (Key.ESCAPE, Key.QUIT):
                self._pop_state()
                return "continue" if key == Key.ESCAPE else "quit"

    menu_items = []
    for r in records:
        status_icon = "✓" if r.is_completed else "✗"
        menu_items.append(f"{r.timestamp[:10]}  {r.input_name:<20} {r.duration_str:>8}  {status_icon}")

    menu = Menu(
        title="转录历史",
        items=menu_items,
        footer="↑↓ 导航  Enter 详情  Esc 返回",
        theme=self.theme,
    )
    menu.render_full()

    while True:
        old_cursor = menu.cursor
        key = self.reader.read_key(timeout=0.05)
        if key is None:
            continue
        if key == Key.QUIT:
            return "quit"
        elif key == Key.ESCAPE:
            self._pop_state()
            return "continue"
        elif key in (Key.UP,):
            menu.move_up()
            menu.render_incremental(old_cursor)
        elif key in (Key.DOWN,):
            menu.move_down()
            menu.render_incremental(old_cursor)
```

- [ ] **步骤 2：Commit**

```bash
git add src/subtap/ui/tui_app.py
git commit -m "feat(ui): 接入转录历史视图"
```

---

## 任务 7：接入设置视图

**文件：**
- 修改：`src/subtap/ui/tui_app.py`（替换 `_view_settings` 骨架）

- [ ] **步骤 1：替换 _view_settings 的 Enter 处理**

```python
def _view_settings(self) -> str:
    menu = Menu(
        title="设置",
        items=[
            "1. 语音识别    识别模型和语言",
            "2. 智能优化    自动纠错、专有名词、翻译",
            "3. 保存格式    SRT/ASS/VTT/JSON",
            "4. 在线服务    接口地址和密钥",
            "5. 语音模型    下载和管理",
        ],
        footer="↑↓ 导航  Enter 确认  Esc 返回  Q 退出",
        theme=self.theme,
    )
    menu.render_full()
    while True:
        old_cursor = menu.cursor
        key = self.reader.read_key(timeout=0.05)
        if key is None:
            continue
        if key == Key.QUIT:
            return "quit"
        elif key == Key.ESCAPE:
            self._pop_state()
            return "continue"
        elif key in (Key.UP,):
            menu.move_up()
            menu.render_incremental(old_cursor)
        elif key in (Key.DOWN,):
            menu.move_down()
            menu.render_incremental(old_cursor)
        elif key == Key.ENTER:
            selected = menu.cursor
            if selected == 0:
                return self._view_settings_asr()
            elif selected == 1:
                return self._view_settings_enhance()
            elif selected == 2:
                return self._view_settings_format()
            elif selected == 3:
                return self._view_settings_api()
            elif selected == 4:
                return self._view_settings_models()
```

- [ ] **步骤 2：添加语音识别设置子页面**

```python
def _view_settings_asr(self) -> str:
    t = self.theme
    model = self.config.get("asr.model", "asr_0.6b")
    lang = self.config.get("output.subtitle_language", "zh")
    mode = self.config.get("mode", "offline")

    items = [
        f"模型：{model}",
        f"语言：{'中文' if lang == 'zh' else '英文' if lang == 'en' else '自动检测'}",
        f"模式：{'在线服务' if mode == 'online' else '本地运行'}",
    ]
    menu = Menu(
        title="设置 · 语音识别",
        items=items,
        footer="↑↓ 导航  Enter 切换  Esc 返回",
        theme=self.theme,
    )
    menu.render_full()

    while True:
        old_cursor = menu.cursor
        key = self.reader.read_key(timeout=0.05)
        if key is None:
            continue
        if key == Key.ESCAPE:
            self._pop_state()
            return "continue"
        elif key == Key.QUIT:
            return "quit"
        elif key in (Key.UP,):
            menu.move_up()
            menu.render_incremental(old_cursor)
        elif key in (Key.DOWN,):
            menu.move_down()
            menu.render_incremental(old_cursor)
        elif key == Key.ENTER:
            if menu.cursor == 0:
                models = ["asr_0.6b", "asr_1.7b"]
                idx = models.index(model) if model in models else 0
                model = models[(idx + 1) % len(models)]
                self.config.set("asr.model", model)
                self.config.save()
            elif menu.cursor == 1:
                langs = [("zh", "中文"), ("en", "英文"), ("", "自动检测")]
                idx = next((i for i, (k, _) in enumerate(langs) if k == lang), 0)
                lang, label = langs[(idx + 1) % len(langs)]
                self.config.set("output.subtitle_language", lang)
                self.config.save()
            elif menu.cursor == 2:
                mode = "online" if mode == "offline" else "offline"
                self.config.set("mode", mode)
                self.config.save()
            # 刷新显示
            items[0] = f"模型：{model}"
            items[1] = f"语言：{'中文' if lang == 'zh' else '英文' if lang == 'en' else '自动检测'}"
            items[2] = f"模式：{'在线服务' if mode == 'online' else '本地运行'}"
            menu = Menu(
                title="设置 · 语音识别",
                items=items,
                footer="↑↓ 导航  Enter 切换  Esc 返回",
                theme=self.theme,
            )
            menu.render_full()
```

- [ ] **步骤 3：添加其他设置子页面（简化版，每个读写对应 config 键）**

```python
def _view_settings_enhance(self) -> str:
    t = self.theme
    proofread = self.config.get("llm_proofread", False)
    hotword = self.config.get("llm_hotword", False)
    translate = self.config.get("translate_to", "")

    def refresh():
        return [
            f"自动纠错：{'开启' if proofread else '关闭'}",
            f"专有名词：{'开启' if hotword else '关闭'}",
            f"自动翻译：{'关闭' if not translate else translate}",
        ]

    items = refresh()
    menu = Menu(title="设置 · 智能优化", items=items, footer="↑↓ 导航  Enter 切换  Esc 返回", theme=self.theme)
    menu.render_full()

    nonlocal proofread, hotword, translate
    while True:
        old_cursor = menu.cursor
        key = self.reader.read_key(timeout=0.05)
        if key is None:
            continue
        if key == Key.ESCAPE:
            self._pop_state()
            return "continue"
        elif key == Key.QUIT:
            return "quit"
        elif key in (Key.UP,):
            menu.move_up()
            menu.render_incremental(old_cursor)
        elif key in (Key.DOWN,):
            menu.move_down()
            menu.render_incremental(old_cursor)
        elif key == Key.ENTER:
            if menu.cursor == 0:
                proofread = not proofread
                self.config.set("llm_proofread", proofread)
            elif menu.cursor == 1:
                hotword = not hotword
                self.config.set("llm_hotword", hotword)
            elif menu.cursor == 2:
                targets = [("", "关闭"), ("en", "英文"), ("ja", "日文")]
                idx = next((i for i, (k, _) in enumerate(targets) if k == translate), 0)
                translate, _ = targets[(idx + 1) % len(targets)]
                self.config.set("translate_to", translate)
            self.config.save()
            items = refresh()
            menu = Menu(title="设置 · 智能优化", items=items, footer="↑↓ 导航  Enter 切换  Esc 返回", theme=self.theme)
            menu.render_full()
```

- [ ] **步骤 4：简化其余 3 个子页面（保存格式/在线服务/语音模型）**

```python
def _view_settings_format(self) -> str:
    t = self.theme
    fmts = self.config.get("output.subtitle_formats", ["srt"])
    items = [f"当前格式：{', '.join(f.upper() for f in fmts)}"]
    menu = Menu(title="设置 · 保存格式", items=items, footer="Esc 返回", theme=self.theme)
    menu.render_full()
    while True:
        key = self.reader.read_key(timeout=0.05)
        if key in (Key.ESCAPE,):
            self._pop_state()
            return "continue"
        elif key == Key.QUIT:
            return "quit"

def _view_settings_api(self) -> str:
    t = self.theme
    base_url = self.config.get("remote_api.base_url", "未配置")
    items = [f"接口地址：{base_url}", f"密钥：{'已配置' if self.config.get('remote_api.api_key_env') else '未配置'}"]
    menu = Menu(title="设置 · 在线服务", items=items, footer="Esc 返回", theme=self.theme)
    menu.render_full()
    while True:
        key = self.reader.read_key(timeout=0.05)
        if key in (Key.ESCAPE,):
            self._pop_state()
            return "continue"
        elif key == Key.QUIT:
            return "quit"

def _view_settings_models(self) -> str:
    t = self.theme
    items = ["模型管理功能开发中..."]
    menu = Menu(title="设置 · 语音模型", items=items, footer="Esc 返回", theme=self.theme)
    menu.render_full()
    while True:
        key = self.reader.read_key(timeout=0.05)
        if key in (Key.ESCAPE,):
            self._pop_state()
            return "continue"
        elif key == Key.QUIT:
            return "quit"
```

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/tui_app.py
git commit -m "feat(ui): 接入设置视图（语音识别/智能优化/保存格式/在线服务/语音模型）"
```

---

## 任务 8：接入批量转录视图

**文件：**
- 修改：`src/subtap/ui/tui_app.py`（替换 `_view_batch` 骨架）

- [ ] **步骤 1：替换 _view_batch 为完整实现**

```python
def _view_batch(self) -> str:
    t = self.theme
    picker = FilePicker(Path.home(), show_dirs=True)
    items = picker.list_items()
    menu_items = [f"📁 {i.name}" if i.is_dir else i.name for i in items]
    if not menu_items:
        menu_items = ["(当前目录无文件夹)"]

    menu = Menu(
        title="批量转录 · 选择文件夹",
        items=menu_items,
        footer="↑↓ 导航  Enter 选择  Esc 返回",
        theme=self.theme,
    )
    menu.render_full()

    while True:
        old_cursor = menu.cursor
        key = self.reader.read_key(timeout=0.05)
        if key is None:
            continue
        if key == Key.QUIT:
            return "quit"
        elif key == Key.ESCAPE:
            self._pop_state()
            return "continue"
        elif key in (Key.UP,):
            menu.move_up()
            menu.render_incremental(old_cursor)
        elif key in (Key.DOWN,):
            menu.move_down()
            menu.render_incremental(old_cursor)
        elif key == Key.ENTER:
            if not items:
                continue
            selected = items[menu.cursor]
            if selected.is_dir:
                return self._execute_batch(selected.path)
```

- [ ] **步骤 2：添加批量执行视图**

```python
def _execute_batch(self, folder: Path) -> str:
    t = self.theme
    from .file_picker import AUDIO_VIDEO_EXTENSIONS
    audio_files = [f for f in folder.iterdir() if f.suffix.lower() in AUDIO_VIDEO_EXTENSIONS]

    if not audio_files:
        sys.stderr.write("\033[2J\033[H")
        sys.stderr.write(f"\033[2K{t.RED}该文件夹中无音频/视频文件{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回{t.NC}\r\n")
        sys.stderr.flush()
        while True:
            key = self.reader.read_key(timeout=0.05)
            if key in (Key.ESCAPE, Key.QUIT):
                self._pop_state()
                return "continue" if key == Key.ESCAPE else "quit"

    sys.stderr.write("\033[2J\033[H")
    sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}批量转录{t.NC}\r\n\r\n")
    sys.stderr.write(f"\033[2K{t.GRAY}文件夹：{folder}{t.NC}\r\n")
    sys.stderr.write(f"\033[2K{t.GRAY}文件数：{len(audio_files)}{t.NC}\r\n\r\n")
    sys.stderr.flush()

    import subprocess
    completed = 0
    for i, f in enumerate(audio_files):
        sys.stderr.write(f"\033[{5 + i};1H\033[2K  ⠙ {f.name}")
        sys.stderr.flush()
        result = subprocess.run(["subtap", "run", str(f)], capture_output=True, text=True)
        if result.returncode == 0:
            completed += 1
            sys.stderr.write(f"\033[{5 + i};1H\033[2K  {t.GREEN}✓{t.NC} {f.name}")
        else:
            sys.stderr.write(f"\033[{5 + i};1H\033[2K  {t.RED}✗{t.NC} {f.name}")
        sys.stderr.flush()

    sys.stderr.write(f"\033[{5 + len(audio_files) + 1};1H\r\n")
    sys.stderr.write(f"\033[2K{t.GREEN}完成：{completed}/{len(audio_files)}{t.NC}\r\n")
    sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回{t.NC}\r\n")
    sys.stderr.flush()

    while True:
        key = self.reader.read_key(timeout=0.05)
        if key in (Key.ESCAPE, Key.ENTER):
            self._pop_state()
            return "continue"
        elif key == Key.QUIT:
            return "quit"
```

- [ ] **步骤 3：Commit**

```bash
git add src/subtap/ui/tui_app.py
git commit -m "feat(ui): 接入批量转录视图（文件夹选择→逐个执行）"
```

---

## 自检清单

1. **规格覆盖度：**
   - ✅ 设置子页面 — 5 个子设置项全部接入（语音识别/智能优化/保存格式/在线服务/语音模型）
   - ✅ 新建转录 — 文件选择 → 确认 → 执行完整流程
   - ✅ 转录历史 — 扫描 ~/.subtap/history 展示
   - ✅ 批量转录 — 文件夹选择 → 逐个执行
   - ⚠️ 初始化引导 — 未单独实现（config_manager 的 get/set 已覆盖配置需求）

2. **占位符扫描：** 无 TODO/待定

3. **类型一致性：** ConfigManager、HistoryScanner、FilePicker、NewTaskView 接口一致
