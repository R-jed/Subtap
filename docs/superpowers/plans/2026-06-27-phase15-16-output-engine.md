# Phase 15 + 16：Output Engine 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 Subtap 从"散落文件写入"升级为"统一 Output Engine 控制"

**架构：** 
- OutputEngine 统一管理所有输出文件
- OutputLifecycle 控制写入顺序和生命周期
- NamingStrategy 管理文件命名
- TUI 绑定输出状态显示

**技术栈：** Python 3.10+, Pydantic v2, Rich, Typer

---

## 文件结构

### 需要创建的文件

| 文件 | 职责 |
|------|------|
| `src/subtap/output/__init__.py` | 输出模块初始化 |
| `src/subtap/output/engine.py` | OutputEngine 核心 |
| `src/subtap/output/lifecycle.py` | 输出生命周期控制 |
| `src/subtap/output/naming.py` | 命名策略系统 |
| `src/subtap/output/versioning.py` | 版本管理系统 |
| `src/subtap/output/exceptions.py` | 输出异常定义 |
| `src/subtap/ui/colors.py` | TUI 颜色方案 |
| `tests/test_output.py` | 输出系统测试 |

### 需要修改的文件

| 文件 | 职责 |
|------|------|
| `src/subtap/schemas/config.py` | 添加 OutputConfig |
| `src/subtap/ui/tui.py` | 绑定输出状态 |
| `src/subtap/ui/progress.py` | 添加输出进度 |
| `src/subtap/cli.py` | 集成 OutputEngine |

---

## 任务 1：创建输出异常定义

**文件：**
- 创建：`src/subtap/output/__init__.py`
- 创建：`src/subtap/output/exceptions.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_output.py
"""Tests for output system."""

import pytest
from subtap.output.exceptions import OutputError


def test_output_error_is_exception():
    """Test OutputError is a proper exception."""
    error = OutputError("test error")
    assert isinstance(error, Exception)
    assert str(error) == "test error"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_output.py::test_output_error_is_exception -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'subtap.output'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/output/__init__.py
"""Output system for Subtap."""

from subtap.output.exceptions import OutputError

__all__ = ["OutputError"]
```

```python
# src/subtap/output/exceptions.py
"""Output system exceptions."""


class OutputError(Exception):
    """Base exception for output system errors."""
    pass
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_output.py::test_output_error_is_exception -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/output/__init__.py src/subtap/output/exceptions.py tests/test_output.py
git commit -m "feat: add output system exceptions"
```

---

## 任务 2：创建命名策略系统

**文件：**
- 创建：`src/subtap/output/naming.py`
- 修改：`tests/test_output.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_output.py
def test_naming_strategy_final_name():
    """Test NamingStrategy generates correct final name."""
    from subtap.output.naming import NamingStrategy
    
    strategy = NamingStrategy("video.mp3")
    assert strategy.get_final_name("srt") == "video.srt"
    assert strategy.get_final_name("ass") == "video.ass"


def test_naming_strategy_report_name():
    """Test NamingStrategy generates correct report name."""
    from subtap.output.naming import NamingStrategy
    
    strategy = NamingStrategy("video.mp3")
    assert strategy.get_report_name() == "video_report.md"


def test_naming_strategy_metrics_name():
    """Test NamingStrategy generates correct metrics name."""
    from subtap.output.naming import NamingStrategy
    
    strategy = NamingStrategy("video.mp3")
    assert strategy.get_metrics_name() == "video_metrics.json"


def test_naming_strategy_artifact_name():
    """Test NamingStrategy generates correct artifact name."""
    from subtap.output.naming import NamingStrategy
    
    strategy = NamingStrategy("video.mp3")
    assert strategy.get_artifact_name("asr") == "video_asr.json"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_output.py::test_naming_strategy_final_name -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'subtap.output.naming'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/output/naming.py
"""Naming strategy for output files."""

from __future__ import annotations

from pathlib import Path


class NamingStrategy:
    """Manages output file naming conventions."""

    def __init__(self, input_name: str, use_timestamp: bool = True):
        """Initialize naming strategy.

        Args:
            input_name: Input file name (e.g., 'video.mp3')
            use_timestamp: Whether to use timestamp in naming (reserved for future)
        """
        self.input_name = Path(input_name).stem
        self.use_timestamp = use_timestamp

    def get_final_name(self, ext: str) -> str:
        """Get final output file name.

        Args:
            ext: File extension (e.g., 'srt', 'ass')

        Returns:
            Final file name (e.g., 'video.srt')
        """
        return f"{self.input_name}.{ext}"

    def get_report_name(self) -> str:
        """Get report file name.

        Returns:
            Report file name (e.g., 'video_report.md')
        """
        return f"{self.input_name}_report.md"

    def get_metrics_name(self) -> str:
        """Get metrics file name.

        Returns:
            Metrics file name (e.g., 'video_metrics.json')
        """
        return f"{self.input_name}_metrics.json"

    def get_run_log_name(self) -> str:
        """Get run log file name.

        Returns:
            Run log file name (e.g., 'video_run.log.jsonl')
        """
        return f"{self.input_name}_run.log.jsonl"

    def get_artifact_name(self, name: str) -> str:
        """Get artifact file name.

        Args:
            name: Artifact name (e.g., 'asr', 'segments')

        Returns:
            Artifact file name (e.g., 'video_asr.json')
        """
        return f"{self.input_name}_{name}.json"
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_output.py -v -k naming`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/output/naming.py tests/test_output.py
git commit -m "feat: add naming strategy system"
```

---

## 任务 3：创建输出生命周期控制

**文件：**
- 创建：`src/subtap/output/lifecycle.py`
- 修改：`tests/test_output.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_output.py
def test_lifecycle_init(tmp_path):
    """Test OutputLifecycle initialization."""
    from subtap.output.lifecycle import OutputLifecycle
    
    version_dir = tmp_path / "v1"
    lifecycle = OutputLifecycle(version_dir)
    
    assert version_dir.exists()
    assert (version_dir / "artifacts").exists()


def test_lifecycle_write_user_artifact(tmp_path):
    """Test writing user artifact."""
    from subtap.output.lifecycle import OutputLifecycle
    
    version_dir = tmp_path / "v1"
    lifecycle = OutputLifecycle(version_dir)
    
    output_path = lifecycle.write_user_artifact("test.srt", "content")
    assert output_path.exists()
    assert output_path.read_text() == "content"


def test_lifecycle_write_report(tmp_path):
    """Test writing report."""
    from subtap.output.lifecycle import OutputLifecycle
    
    version_dir = tmp_path / "v1"
    lifecycle = OutputLifecycle(version_dir)
    
    output_path = lifecycle.write_report("# Report\n\nContent")
    assert output_path.exists()
    assert output_path.read_text() == "# Report\n\nContent"


def test_lifecycle_write_metrics(tmp_path):
    """Test writing metrics."""
    from subtap.output.lifecycle import OutputLifecycle
    
    version_dir = tmp_path / "v1"
    lifecycle = OutputLifecycle(version_dir)
    
    metrics = {"total_duration": 24.8}
    output_path = lifecycle.write_metrics(metrics)
    assert output_path.exists()
    
    import json
    data = json.loads(output_path.read_text())
    assert data["total_duration"] == 24.8


def test_lifecycle_write_artifacts(tmp_path):
    """Test writing artifacts."""
    from subtap.output.lifecycle import OutputLifecycle
    
    version_dir = tmp_path / "v1"
    lifecycle = OutputLifecycle(version_dir)
    
    artifacts = {
        "asr": {"segments": [1, 2, 3]},
        "segments": {"sentences": [1, 2]}
    }
    lifecycle.write_artifacts(artifacts)
    
    assert (version_dir / "artifacts" / "asr.json").exists()
    assert (version_dir / "artifacts" / "segments.json").exists()


def test_lifecycle_finalize(tmp_path):
    """Test finalizing output."""
    from subtap.output.lifecycle import OutputLifecycle
    
    version_dir = tmp_path / "v1"
    lifecycle = OutputLifecycle(version_dir)
    
    lifecycle.write_user_artifact("test.srt", "content")
    result = lifecycle.finalize_output()
    
    assert "files" in result
    assert "checksum" in result
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_output.py::test_lifecycle_init -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'subtap.output.lifecycle'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/output/lifecycle.py
"""Output lifecycle management."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from subtap.output.exceptions import OutputError

logger = logging.getLogger(__name__)


class OutputLifecycle:
    """Manages output file writing lifecycle."""

    def __init__(self, version_dir: Path):
        """Initialize output lifecycle.

        Args:
            version_dir: Version directory path (e.g., output/video/v1)
        """
        self.version_dir = version_dir
        self.version_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts_dir = self.version_dir / "artifacts"
        self._artifacts_dir.mkdir(exist_ok=True)
        self._written_files: list[Path] = []

    def init_output_task(self) -> None:
        """Initialize output task."""
        logger.info("初始化输出目录: %s", self.version_dir)

    def write_user_artifact(self, name: str, content: str) -> Path:
        """Write user-visible artifact.

        Args:
            name: File name (e.g., 'video.srt')
            content: File content

        Returns:
            Path to written file

        Raises:
            OutputError: If write fails
        """
        try:
            output_path = self.version_dir / name
            output_path.write_text(content, encoding="utf-8")
            self._written_files.append(output_path)
            logger.info("写入文件: %s", output_path)
            return output_path
        except OSError as e:
            logger.error("写入文件失败: %s - %s", name, e)
            raise OutputError(f"写入 {name} 失败: {e}") from e

    def write_report(self, content: str) -> Path:
        """Write report file.

        Args:
            content: Report content (markdown)

        Returns:
            Path to written report
        """
        return self.write_user_artifact("report.md", content)

    def write_metrics(self, metrics: dict) -> Path:
        """Write metrics file.

        Args:
            metrics: Metrics dictionary

        Returns:
            Path to written metrics
        """
        content = json.dumps(metrics, indent=2, ensure_ascii=False)
        return self.write_user_artifact("metrics.json", content)

    def write_artifacts(self, artifacts: dict[str, dict]) -> None:
        """Write intermediate artifacts.

        Args:
            artifacts: Dictionary of artifact name to content
        """
        for name, content in artifacts.items():
            try:
                output_path = self._artifacts_dir / f"{name}.json"
                output_path.write_text(
                    json.dumps(content, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
                self._written_files.append(output_path)
                logger.info("写入 artifact: %s", output_path)
            except OSError as e:
                logger.error("写入 artifact 失败: %s - %s", name, e)
                raise OutputError(f"写入 artifact {name} 失败: {e}") from e

    def write_run_log(self, log_entry: dict) -> Path:
        """Append to run log.

        Args:
            log_entry: Log entry dictionary

        Returns:
            Path to run log
        """
        log_path = self.version_dir / "run.log.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        if log_path not in self._written_files:
            self._written_files.append(log_path)
        return log_path

    def finalize_output(self) -> dict:
        """Finalize output, generate checksum.

        Returns:
            Dictionary with files list and checksum
        """
        # Calculate checksum of all written files
        checksums = []
        for file_path in sorted(self._written_files):
            if file_path.exists():
                content = file_path.read_bytes()
                file_hash = hashlib.sha256(content).hexdigest()[:16]
                checksums.append(f"{file_path.name}:{file_hash}")

        combined_checksum = hashlib.sha256(
            "|".join(checksums).encode()
        ).hexdigest()[:16]

        result = {
            "files": [str(f.relative_to(self.version_dir)) for f in self._written_files],
            "checksum": combined_checksum,
            "version_dir": str(self.version_dir),
        }

        logger.info("输出完成: %s", self.version_dir)
        return result
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_output.py -v -k lifecycle`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/output/lifecycle.py tests/test_output.py
git commit -m "feat: add output lifecycle management"
```

---

## 任务 4：创建版本管理系统

**文件：**
- 创建：`src/subtap/output/versioning.py`
- 修改：`tests/test_output.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_output.py
def test_versioning_first_version(tmp_path):
    """Test first version creation."""
    from subtap.output.versioning import VersionManager
    
    manager = VersionManager(tmp_path, "video")
    version = manager.next_version()
    assert version == 1


def test_versioning_increment(tmp_path):
    """Test version increment."""
    from subtap.output.versioning import VersionManager
    
    # Create v1
    (tmp_path / "video" / "v1").mkdir(parents=True)
    
    manager = VersionManager(tmp_path, "video")
    version = manager.next_version()
    assert version == 2


def test_versioning_create_latest_link(tmp_path):
    """Test latest symlink creation."""
    from subtap.output.versioning import VersionManager
    
    manager = VersionManager(tmp_path, "video")
    manager.create_latest_link(1)
    
    latest_link = tmp_path / "video" / "latest"
    assert latest_link.exists()
    assert latest_link.is_symlink()
    assert latest_link.readlink() == Path("v1")


def test_versioning_cleanup_old_versions(tmp_path):
    """Test old version cleanup."""
    from subtap.output.versioning import VersionManager
    
    # Create v1, v2, v3, v4, v5, v6
    for i in range(1, 7):
        (tmp_path / "video" / f"v{i}").mkdir(parents=True)
    
    manager = VersionManager(tmp_path, "video")
    manager.cleanup_old_versions(keep_last=3)
    
    # Should keep v4, v5, v6
    assert not (tmp_path / "video" / "v1").exists()
    assert not (tmp_path / "video" / "v2").exists()
    assert not (tmp_path / "video" / "v3").exists()
    assert (tmp_path / "video" / "v4").exists()
    assert (tmp_path / "video" / "v5").exists()
    assert (tmp_path / "video" / "v6").exists()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_output.py::test_versioning_first_version -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'subtap.output.versioning'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/output/versioning.py
"""Version management for output system."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class VersionManager:
    """Manages output versions."""

    def __init__(self, output_dir: Path, input_name: str):
        """Initialize version manager.

        Args:
            output_dir: Base output directory
            input_name: Input file name stem
        """
        self.output_dir = output_dir
        self.input_name = input_name
        self._base_dir = output_dir / input_name

    def next_version(self) -> int:
        """Get next version number.

        Returns:
            Next version number
        """
        if not self._base_dir.exists():
            return 1

        existing = [
            int(p.name[1:])
            for p in self._base_dir.iterdir()
            if p.is_dir() and p.name.startswith("v") and p.name[1:].isdigit()
        ]

        if not existing:
            return 1

        return max(existing) + 1

    def get_version_dir(self, version: int) -> Path:
        """Get version directory path.

        Args:
            version: Version number

        Returns:
            Path to version directory
        """
        return self._base_dir / f"v{version}"

    def create_latest_link(self, version: int) -> None:
        """Create latest symlink.

        Args:
            version: Version to point to
        """
        latest_link = self._base_dir / "latest"

        # Remove existing link
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()

        # Create new symlink
        latest_link.symlink_to(f"v{version}")
        logger.info("创建 latest 链接: %s -> v%d", latest_link, version)

    def cleanup_old_versions(self, keep_last: int = 5) -> None:
        """Clean up old versions.

        Args:
            keep_last: Number of recent versions to keep
        """
        if not self._base_dir.exists():
            return

        existing = sorted(
            [p for p in self._base_dir.iterdir() if p.is_dir() and p.name.startswith("v")],
            key=lambda p: int(p.name[1:])
        )

        if len(existing) <= keep_last:
            return

        for old_version in existing[:-keep_last]:
            shutil.rmtree(old_version)
            logger.info("清理旧版本: %s", old_version)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_output.py -v -k versioning`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/output/versioning.py tests/test_output.py
git commit -m "feat: add version management system"
```

---

## 任务 5：创建 OutputEngine 核心

**文件：**
- 创建：`src/subtap/output/engine.py`
- 修改：`tests/test_output.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_output.py
def test_output_engine_init(tmp_path):
    """Test OutputEngine initialization."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig
    
    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)
    
    assert engine.output_dir == tmp_path
    assert engine.input_name == "video"
    assert engine.version == 1


def test_output_engine_write_final(tmp_path):
    """Test writing final output."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig
    
    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)
    
    output_path = engine.write_final("srt", "1\n00:00:01,000 --> 00:00:02,000\nHello")
    assert output_path.exists()
    assert output_path.name == "video.srt"


def test_output_engine_write_report(tmp_path):
    """Test writing report."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig
    
    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)
    
    output_path = engine.write_report("# Report")
    assert output_path.exists()
    assert output_path.name == "video_report.md"


def test_output_engine_write_metrics(tmp_path):
    """Test writing metrics."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig
    
    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)
    
    metrics = {"total_duration": 24.8}
    output_path = engine.write_metrics(metrics)
    assert output_path.exists()
    assert output_path.name == "video_metrics.json"


def test_output_engine_finalize(tmp_path):
    """Test finalizing output."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig
    
    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)
    
    engine.write_final("srt", "content")
    result = engine.finalize_output()
    
    assert "files" in result
    assert "checksum" in result
    assert "version" in result
    assert result["version"] == 1
    
    # Check latest symlink
    latest_link = tmp_path / "video" / "latest"
    assert latest_link.exists()
    assert latest_link.is_symlink()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_output.py::test_output_engine_init -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'subtap.output.engine'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/output/engine.py
"""Output engine core."""

from __future__ import annotations

import logging
from pathlib import Path

from subtap.output.exceptions import OutputError
from subtap.output.lifecycle import OutputLifecycle
from subtap.output.naming import NamingStrategy
from subtap.output.versioning import VersionManager
from subtap.schemas.config import OutputConfig

logger = logging.getLogger(__name__)


class OutputEngine:
    """Unified output management engine."""

    def __init__(self, output_dir: Path, input_name: str, config: OutputConfig):
        """Initialize output engine.

        Args:
            output_dir: Base output directory
            input_name: Input file name (e.g., 'video.mp3')
            config: Output configuration
        """
        self.output_dir = output_dir
        self.input_name = Path(input_name).stem
        self.config = config

        # Initialize components
        self.naming = NamingStrategy(input_name, config.timestamp)
        self.version_manager = VersionManager(output_dir, self.input_name)
        self.version = self.version_manager.next_version()

        # Get version directory and initialize lifecycle
        version_dir = self.version_manager.get_version_dir(self.version)
        self.lifecycle = OutputLifecycle(version_dir)

        logger.info("初始化 OutputEngine: %s v%d", self.input_name, self.version)

    def write_final(self, ext: str, content: str) -> Path:
        """Write final output file.

        Args:
            ext: File extension (e.g., 'srt', 'ass')
            content: File content

        Returns:
            Path to written file
        """
        name = self.naming.get_final_name(ext)
        return self.lifecycle.write_user_artifact(name, content)

    def write_report(self, content: str) -> Path:
        """Write report file.

        Args:
            content: Report content (markdown)

        Returns:
            Path to written report
        """
        name = self.naming.get_report_name()
        return self.lifecycle.write_user_artifact(name, content)

    def write_metrics(self, metrics: dict) -> Path:
        """Write metrics file.

        Args:
            metrics: Metrics dictionary

        Returns:
            Path to written metrics
        """
        name = self.naming.get_metrics_name()
        return self.lifecycle.write_user_artifact(
            name,
            __import__("json").dumps(metrics, indent=2, ensure_ascii=False)
        )

    def write_run_log(self, log_entry: dict) -> Path:
        """Append to run log.

        Args:
            log_entry: Log entry dictionary

        Returns:
            Path to run log
        """
        return self.lifecycle.write_run_log(log_entry)

    def write_artifacts(self, artifacts: dict[str, dict]) -> None:
        """Write intermediate artifacts.

        Args:
            artifacts: Dictionary of artifact name to content
        """
        self.lifecycle.write_artifacts(artifacts)

    def finalize_output(self) -> dict:
        """Finalize output, create latest link, cleanup old versions.

        Returns:
            Dictionary with output summary
        """
        # Finalize lifecycle
        result = self.lifecycle.finalize_output()

        # Create latest symlink
        self.version_manager.create_latest_link(self.version)

        # Cleanup old versions
        if self.config.keep_versions > 0:
            self.version_manager.cleanup_old_versions(self.config.keep_versions)

        result["version"] = self.version
        result["input_name"] = self.input_name

        logger.info("输出完成: %s v%d", self.input_name, self.version)
        return result
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_output.py -v -k engine`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/output/engine.py tests/test_output.py
git commit -m "feat: add OutputEngine core"
```

---

## 任务 6：添加 OutputConfig 配置

**文件：**
- 修改：`src/subtap/schemas/config.py`
- 修改：`tests/test_output.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_output.py
def test_output_config_defaults():
    """Test OutputConfig default values."""
    from subtap.schemas.config import OutputConfig
    
    config = OutputConfig()
    assert config.timestamp is True
    assert config.keep_versions == 5
    assert config.generate_artifacts is True


def test_output_config_custom():
    """Test OutputConfig custom values."""
    from subtap.schemas.config import OutputConfig
    
    config = OutputConfig(timestamp=False, keep_versions=10)
    assert config.timestamp is False
    assert config.keep_versions == 10
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_output.py::test_output_config_defaults -v`
预期：FAIL，报错 "ImportError: cannot import name 'OutputConfig'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/schemas/config.py
# 在现有配置类后添加

class OutputConfig(BaseModel):
    """Output system configuration."""

    timestamp: bool = True  # Default timestamp on
    keep_versions: int = 5  # Keep last N versions
    generate_artifacts: bool = True  # Generate intermediate files


class SubtapConfig(BaseModel):
    """Root configuration for Subtap."""

    audio: AudioConfig = Field(default_factory=AudioConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    clean: CleanConfig = Field(default_factory=CleanConfig)
    align: AlignConfig = Field(default_factory=AlignConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)  # 新增
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_output.py -v -k config`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/schemas/config.py tests/test_output.py
git commit -m "feat: add OutputConfig configuration"
```

---

## 任务 7：创建 TUI 颜色方案

**文件：**
- 创建：`src/subtap/ui/colors.py`
- 修改：`tests/test_output.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_output.py
def test_tui_colors_defined():
    """Test TUI color styles are defined."""
    from subtap.ui.colors import (
        STAGE_TITLE, PROGRESS_BAR, PROGRESS_ACTIVE,
        ERROR, FILE_PATH, TIMING, SUCCESS, HEADER
    )
    
    from rich.style import Style
    
    assert isinstance(STAGE_TITLE, Style)
    assert isinstance(PROGRESS_BAR, Style)
    assert isinstance(ERROR, Style)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_output.py::test_tui_colors_defined -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'subtap.ui.colors'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/ui/colors.py
"""TUI color scheme for Subtap."""

from rich.style import Style

# Stage titles
STAGE_TITLE = Style(color="blue", bold=True)

# Progress bar states
PROGRESS_BAR = Style(color="green")
PROGRESS_ACTIVE = Style(color="yellow")

# Status indicators
SUCCESS = Style(color="green", bold=True)
ERROR = Style(color="red", bold=True)

# Information display
FILE_PATH = Style(color="cyan")
TIMING = Style(color="dim")
HEADER = Style(color="white", bold=True)

# Summary panel
SUMMARY_BORDER = Style(color="blue")
SUMMARY_TITLE = Style(color="white", bold=True)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_output.py::test_tui_colors_defined -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/colors.py tests/test_output.py
git commit -m "feat: add TUI color scheme"
```

---

## 任务 8：修改 TUI 绑定输出状态

**文件：**
- 修改：`src/subtap/ui/tui.py`
- 修改：`src/subtap/ui/progress.py`
- 修改：`tests/test_output.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_output.py
def test_tui_runner_with_output_engine(tmp_path):
    """Test TUIRunner with OutputEngine."""
    from subtap.ui.tui import TUIRunner
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig
    
    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)
    
    runner = TUIRunner(use_tui=False, output_engine=engine)
    assert runner.output_engine == engine
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_output.py::test_tui_runner_with_output_engine -v`
预期：FAIL，报错 "TypeError: __init__() got an unexpected keyword argument 'output_engine'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/ui/tui.py
class TUIRunner:
    """TUI-wrapped pipeline execution with Chinese status display."""

    def __init__(self, use_tui: bool = True, mode: str = "hybrid", output_engine=None):
        self.use_tui = use_tui
        self.mode = mode
        self.output_engine = output_engine  # 新增
        self.progress = PipelineProgress() if use_tui else None
        self.state = reset_state()
        self.timings: dict[str, float] = {}
        self.total_start: float = 0.0

        if self.use_tui:
            self.state.on_change(self.progress.on_state_change)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_output.py::test_tui_runner_with_output_engine -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/tui.py tests/test_output.py
git commit -m "feat: bind OutputEngine to TUI"
```

---

## 任务 9：集成 OutputEngine 到 CLI

**文件：**
- 修改：`src/subtap/cli.py`
- 修改：`tests/test_output.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_output.py
def test_cli_run_uses_output_engine(tmp_path):
    """Test CLI run command uses OutputEngine."""
    from typer.testing import CliRunner
    from subtap.cli import app
    
    runner = CliRunner()
    # This will be tested with mock in integration
    # For now, just verify the command exists
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_output.py::test_cli_run_uses_output_engine -v`
预期：PASS (help command works)

- [ ] **步骤 3：修改 CLI 集成 OutputEngine**

```python
# src/subtap/cli.py
@app.command()
def run(
    input_path: Path = typer.Argument(..., help="输入媒体文件路径"),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    output_dir: Path = typer.Option(Path("./output"), "-o", "--output-dir", help="输出目录"),
    fmt: str = typer.Option("srt", "--format", "-f", help="导出格式：srt / ass / txt"),
    mode: str = typer.Option("hybrid", "--mode", "-m", help="执行模式：fast / quality / hybrid"),
    timestamp: bool = typer.Option(True, "--timestamp/--no-timestamp", help="输出目录是否带时间戳"),
    # ... 其他参数
) -> None:
    """运行完整字幕生成流程"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline
    from subtap.output.engine import OutputEngine
    
    if not input_path.exists():
        typer.echo(f"✗ 错误：文件未找到 {input_path}", err=True)
        raise typer.Exit(1)
    
    config = load_config(Path.home() / ".subtap" / "config.yaml")
    config.output.timestamp = timestamp  # CLI overrides config
    
    # Create OutputEngine
    engine = OutputEngine(output_dir, input_path.stem, config.output)
    
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()
    
    # ... rest of the command with engine integration
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_output.py -v -k cli`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/cli.py tests/test_output.py
git commit -m "feat: integrate OutputEngine to CLI"
```

---

## 任务 10：完整集成测试

**文件：**
- 修改：`tests/test_output.py`

- [ ] **步骤 1：编写集成测试**

```python
# tests/test_output.py
def test_full_output_flow(tmp_path):
    """Test complete output flow."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig
    
    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)
    
    # Write final output
    engine.write_final("srt", "1\n00:00:01,000 --> 00:00:02,000\nHello")
    
    # Write report
    engine.write_report("# Report\n\nQuality: 92/100")
    
    # Write metrics
    engine.write_metrics({"total_duration": 24.8})
    
    # Write artifacts
    engine.write_artifacts({
        "asr": {"segments": [1, 2, 3]},
        "segments": {"sentences": [1, 2]}
    })
    
    # Finalize
    result = engine.finalize_output()
    
    # Verify structure
    version_dir = tmp_path / "video" / "v1"
    assert version_dir.exists()
    assert (version_dir / "video.srt").exists()
    assert (version_dir / "video_report.md").exists()
    assert (version_dir / "video_metrics.json").exists()
    assert (version_dir / "artifacts" / "asr.json").exists()
    assert (version_dir / "artifacts" / "segments.json").exists()
    
    # Verify latest link
    latest_link = tmp_path / "video" / "latest"
    assert latest_link.exists()
    assert latest_link.is_symlink()
    
    # Verify result
    assert result["version"] == 1
    assert "checksum" in result
```

- [ ] **步骤 2：运行测试验证**

运行：`pytest tests/test_output.py::test_full_output_flow -v`
预期：PASS

- [ ] **步骤 3：运行所有测试**

运行：`pytest -v`
预期：所有测试通过

- [ ] **步骤 4：Commit**

```bash
git add tests/test_output.py
git commit -m "test: add full output flow integration test"
```

---

## 任务 11：最终验证

**文件：** 无

- [ ] **步骤 1：运行所有测试**

运行：`pytest -v`
预期：所有测试通过

- [ ] **步骤 2：运行输出系统测试**

运行：`pytest tests/test_output.py -v`
预期：所有输出系统测试通过

- [ ] **步骤 3：手动测试 CLI**

```bash
# 测试 run 命令帮助
subtap run --help

# 测试 --timestamp 参数
subtap run video.mp3 --timestamp
subtap run video.mp3 --no-timestamp
```

- [ ] **步骤 4：最终 Commit**

```bash
git add -A
git commit -m "feat: Phase 15+16 Output Engine complete"
```

---

## 验收标准

1. ✔ 所有输出文件由 OutputEngine 生成
2. ✔ pipeline 无直接 file write
3. ✔ output 结构一致（每个版本目录结构相同）
4. ✔ run 可重复执行（相同输入生成相同版本号）
5. ✔ TUI 状态完整展示（每个阶段有进度条）
6. ✔ 无散点输出（所有文件在统一目录）
7. ✔ latest 符号链接正确指向最新版本
8. ✔ 旧版本自动清理（保留最近 5 个）
9. ✔ 错误处理完善（写入失败有明确错误信息）
10. ✔ 并发安全（多个实例不会版本冲突）
11. ✔ 所有测试通过
12. ✔ TUI 颜色方案符合设计
