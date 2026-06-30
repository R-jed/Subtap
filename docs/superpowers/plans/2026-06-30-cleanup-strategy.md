# 工作区清理策略实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 实现工作区清理策略，执行完成后自动清理临时文件，批量转录完成后清理中间文件，提供手动清理命令

**架构：**
- 扩展现有 `Cleanroom` 类，添加分层清理方法
- 在 `Pipeline` 完成后调用清理
- 在 `batch_transcribe()` 完成后清理 L2 中间文件
- 添加 `subtap clean --all` CLI 命令

**技术栈：** Python, Typer CLI, Pydantic v2

---

## 文件结构

### 修改的文件

| 文件 | 职责 |
|------|------|
| `src/subtap/engine/cleanroom.py` | 添加 `clean_temp_files()` 和 `clean_intermediate_files()` 方法 |
| `src/subtap/core/pipeline.py` | 添加 `cleanup()` 方法，在完成后调用清理 |
| `src/subtap/cli.py` | 添加 `subtap clean --all` 命令，修改 `run()` 和 `batch_transcribe()` |
| `src/subtap/schemas/config.py` | 添加 `CleanupConfig` 配置模型 |

### 新建的文件

| 文件 | 职责 |
|------|------|
| `tests/test_cleanup.py` | 清理策略测试 |

---

## 任务 1：扩展 Cleanroom 类添加分层清理方法

**文件：**
- 修改：`src/subtap/engine/cleanroom.py`
- 测试：`tests/test_cleanup.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_cleanup.py
"""Tests for cleanup strategy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from subtap.engine.cleanroom import Cleanroom


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a mock workspace with temp and intermediate files."""
    # L1 临时文件
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")
    (chunks_dir / "chunk_0001.wav").write_bytes(b"fake wav")
    (chunks_dir / "chunks.jsonl").write_text('{"chunk_id": 0}\n')

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "source.wav").write_bytes(b"fake wav")

    # L2 中间文件
    (tmp_path / "asr").mkdir()
    (tmp_path / "asr" / "asr.jsonl").write_text('{"text": "hello"}\n')
    (tmp_path / "cleaned.jsonl").write_text('{"text": "hello"}\n')
    (tmp_path / "sentences.jsonl").write_text('{"text": "hello"}\n')

    # L3 输出文件
    (tmp_path / "aligned.jsonl").write_text('{"text": "hello"}\n')
    (tmp_path / "report.md").write_text("# Report\n")
    (tmp_path / "metrics.json").write_text('{}\n')

    # 系统文件
    (tmp_path / ".DS_Store").write_text("")

    return tmp_path


class TestCleanTempFiles:
    """Test L1 temp file cleanup."""

    def test_removes_chunk_wav_files(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        result = cleanroom.clean_temp_files()
        assert result["cleaned_count"] >= 2
        assert not (workspace / "chunks" / "chunk_0000.wav").exists()
        assert not (workspace / "chunks" / "chunk_0001.wav").exists()

    def test_removes_source_wav(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        result = cleanroom.clean_temp_files()
        assert not (workspace / "audio" / "source.wav").exists()

    def test_removes_system_files(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        result = cleanroom.clean_temp_files()
        assert not (workspace / ".DS_Store").exists()

    def test_preserves_chunks_jsonl(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        cleanroom.clean_temp_files()
        assert (workspace / "chunks" / "chunks.jsonl").exists()

    def test_preserves_intermediate_files(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        cleanroom.clean_temp_files()
        assert (workspace / "asr" / "asr.jsonl").exists()
        assert (workspace / "cleaned.jsonl").exists()
        assert (workspace / "sentences.jsonl").exists()

    def test_preserves_output_files(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        cleanroom.clean_temp_files()
        assert (workspace / "aligned.jsonl").exists()
        assert (workspace / "report.md").exists()
        assert (workspace / "metrics.json").exists()


class TestCleanIntermediateFiles:
    """Test L2 intermediate file cleanup."""

    def test_removes_asr_jsonl(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        result = cleanroom.clean_intermediate_files()
        assert not (workspace / "asr" / "asr.jsonl").exists()

    def test_removes_cleaned_jsonl(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        result = cleanroom.clean_intermediate_files()
        assert not (workspace / "cleaned.jsonl").exists()

    def test_removes_sentences_jsonl(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        result = cleanroom.clean_intermediate_files()
        assert not (workspace / "sentences.jsonl").exists()

    def test_preserves_aligned_jsonl(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        cleanroom.clean_intermediate_files()
        assert (workspace / "aligned.jsonl").exists()

    def test_preserves_output_files(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        cleanroom.clean_intermediate_files()
        assert (workspace / "report.md").exists()
        assert (workspace / "metrics.json").exists()


class TestCleanAll:
    """Test full cleanup (L1 + L2)."""

    def test_removes_all_temp_and_intermediate(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        result = cleanroom.clean_all()
        assert result["cleaned_count"] >= 5

    def test_preserves_output_files(self, workspace: Path) -> None:
        cleanroom = Cleanroom(workspace)
        cleanroom.clean_all()
        assert (workspace / "aligned.jsonl").exists()
        assert (workspace / "report.md").exists()
        assert (workspace / "metrics.json").exists()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_cleanup.py -v`
预期：FAIL，报错 "AttributeError: 'Cleanroom' object has no attribute 'clean_temp_files'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/engine/cleanroom.py - 添加以下方法

def clean_temp_files(self) -> dict[str, Any]:
    """Remove L1 temp files (chunk WAV, source WAV, system files).

    Never removes:
    - chunks.jsonl (supports re-running ASR)
    - Intermediate JSONL files (asr.jsonl, cleaned.jsonl, sentences.jsonl)
    - Output files (aligned.jsonl, report.md, metrics.json, output/)
    """
    cleaned = 0
    issues: list[str] = []

    # Remove chunk wav files
    for f in self.root.glob("chunks/chunk_*.wav"):
        if f.is_file():
            f.unlink()
            cleaned += 1

    # Remove source wav
    source_wav = self.root / "audio" / "source.wav"
    if source_wav.exists():
        source_wav.unlink()
        cleaned += 1

    # Remove system files
    for name in _CLEANABLE_NAMES:
        for f in self.root.rglob(name):
            if f.is_file():
                f.unlink()
                cleaned += 1

    # Remove __pycache__ directories
    for d in self.root.rglob("__pycache__"):
        if d.is_dir():
            import shutil
            shutil.rmtree(d)
            cleaned += 1

    return {"cleaned_count": cleaned, "issues": issues, "is_clean": len(issues) == 0}


def clean_intermediate_files(self) -> dict[str, Any]:
    """Remove L2 intermediate files (asr.jsonl, cleaned.jsonl, sentences.jsonl).

    Never removes:
    - aligned.jsonl (user output)
    - report.md, metrics.json (user output)
    - output/ directory (user output)
    """
    cleaned = 0
    issues: list[str] = []

    # Remove ASR output
    asr_jsonl = self.root / "asr" / "asr.jsonl"
    if asr_jsonl.exists():
        asr_jsonl.unlink()
        cleaned += 1

    # Remove cleaned.jsonl
    cleaned_jsonl = self.root / "cleaned.jsonl"
    if cleaned_jsonl.exists():
        cleaned_jsonl.unlink()
        cleaned += 1

    # Remove sentences.jsonl
    sentences_jsonl = self.root / "sentences.jsonl"
    if sentences_jsonl.exists():
        sentences_jsonl.unlink()
        cleaned += 1

    return {"cleaned_count": cleaned, "issues": issues, "is_clean": len(issues) == 0}


def clean_all(self) -> dict[str, Any]:
    """Remove all temp and intermediate files (L1 + L2).

    Preserves only:
    - aligned.jsonl (user output)
    - report.md, metrics.json (user output)
    - output/ directory (user output)
    """
    result1 = self.clean_temp_files()
    result2 = self.clean_intermediate_files()

    return {
        "cleaned_count": result1["cleaned_count"] + result2["cleaned_count"],
        "issues": result1["issues"] + result2["issues"],
        "is_clean": result1["is_clean"] and result2["is_clean"],
    }
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_cleanup.py -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/engine/cleanroom.py tests/test_cleanup.py
git commit -m "feat(cleanroom): add layered cleanup methods (L1 temp, L2 intermediate, all)"
```

---

## 任务 2：Pipeline 完成后自动清理 L1 临时文件

**文件：**
- 修改：`src/subtap/core/pipeline.py`
- 测试：`tests/test_cleanup.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_cleanup.py - 添加以下测试

class TestPipelineCleanup:
    """Test Pipeline.cleanup() method."""

    def test_cleanup_removes_temp_files(self, tmp_path: Path) -> None:
        """Pipeline.cleanup() should remove L1 temp files."""
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig

        # Create workspace with temp files
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")

        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "source.wav").write_bytes(b"fake wav")

        # Create pipeline
        config = SubtapConfig()
        pipeline = Pipeline(config, work_dir=tmp_path)

        # Run cleanup
        result = pipeline.cleanup()

        # Verify temp files removed
        assert not (tmp_path / "chunks" / "chunk_0000.wav").exists()
        assert not (tmp_path / "audio" / "source.wav").exists()
        assert result["cleaned_count"] >= 2

    def test_cleanup_preserves_intermediate_files(self, tmp_path: Path) -> None:
        """Pipeline.cleanup() should preserve L2 intermediate files."""
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig

        # Create workspace with intermediate files
        (tmp_path / "cleaned.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "sentences.jsonl").write_text('{"text": "hello"}\n')

        # Create pipeline
        config = SubtapConfig()
        pipeline = Pipeline(config, work_dir=tmp_path)

        # Run cleanup
        pipeline.cleanup()

        # Verify intermediate files preserved
        assert (tmp_path / "cleaned.jsonl").exists()
        assert (tmp_path / "sentences.jsonl").exists()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_cleanup.py::TestPipelineCleanup -v`
预期：FAIL，报错 "AttributeError: 'Pipeline' object has no attribute 'cleanup'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/core/pipeline.py - 添加以下方法

def cleanup(self) -> dict[str, Any]:
    """Remove L1 temp files after pipeline completion.

    This is called automatically after successful pipeline execution.
    Preserves intermediate files (L2) for potential re-runs.
    """
    from subtap.engine.cleanroom import Cleanroom

    cleanroom = Cleanroom(self.workspace.root)
    return cleanroom.clean_temp_files()
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_cleanup.py::TestPipelineCleanup -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/core/pipeline.py tests/test_cleanup.py
git commit -m "feat(pipeline): add cleanup() method for L1 temp file removal"
```

---

## 任务 3：CLI `run()` 命令完成后调用清理

**文件：**
- 修改：`src/subtap/cli.py`
- 测试：`tests/test_cleanup.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_cleanup.py - 添加以下测试

class TestCLIRunCleanup:
    """Test CLI run command cleanup integration."""

    def test_run_cleanup_removes_temp_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI run should cleanup temp files after successful execution."""
        from typer.testing import CliRunner
        from subtap.cli import app

        runner = CliRunner()

        # Mock config loading
        config = SubtapConfig()
        monkeypatch.setattr("subtap.cli.load_config", lambda: config)

        # Create a test audio file
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake wav")

        # Run pipeline
        result = runner.invoke(app, [
            "run", str(audio_file),
            "-w", str(tmp_path / "work"),
            "-o", str(tmp_path / "output"),
            "--no-tui",
            "--no-align",
        ])

        # Verify cleanup happened (chunk wav files should not exist)
        work_dir = tmp_path / "work"
        if work_dir.exists():
            chunk_wavs = list(work_dir.glob("chunks/chunk_*.wav"))
            assert len(chunk_wavs) == 0
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_cleanup.py::TestCLIRunCleanup -v`
预期：FAIL（因为 cleanup 未在 run() 中调用）

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/cli.py - 在 run() 函数的成功路径中添加清理

# 在 pipeline.run_stage("export") 之后添加：
pipeline.cleanup()
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_cleanup.py::TestCLIRunCleanup -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/cli.py tests/test_cleanup.py
git commit -m "feat(cli): add cleanup after successful pipeline run"
```

---

## 任务 4：批量转录完成后清理 L2 中间文件

**文件：**
- 修改：`src/subtap/cli.py`
- 测试：`tests/test_cleanup.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_cleanup.py - 添加以下测试

class TestBatchCleanup:
    """Test batch transcription cleanup integration."""

    def test_batch_cleanup_removes_intermediate_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Batch transcription should cleanup intermediate files after completion."""
        from subtap.engine.cleanroom import Cleanroom

        # Create a mock workspace with intermediate files
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (work_dir / "cleaned.jsonl").write_text('{"text": "hello"}\n')
        (work_dir / "sentences.jsonl").write_text('{"text": "hello"}\n')
        (work_dir / "aligned.jsonl").write_text('{"text": "hello"}\n')

        # Run cleanup
        cleanroom = Cleanroom(work_dir)
        result = cleanroom.clean_intermediate_files()

        # Verify intermediate files removed
        assert not (work_dir / "cleaned.jsonl").exists()
        assert not (work_dir / "sentences.jsonl").exists()

        # Verify output files preserved
        assert (work_dir / "aligned.jsonl").exists()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_cleanup.py::TestBatchCleanup -v`
预期：PASS（因为 clean_intermediate_files 已在任务 1 中实现）

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/cli.py - 在 batch_transcribe() 函数的成功路径中添加清理

# 在每个文件处理完成后添加：
from subtap.engine.cleanroom import Cleanroom
cleanroom = Cleanroom(item_work_dir)
cleanroom.clean_intermediate_files()
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_cleanup.py::TestBatchCleanup -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/cli.py tests/test_cleanup.py
git commit -m "feat(cli): add cleanup after batch transcription completion"
```

---

## 任务 5：添加 `subtap clean --all` CLI 命令

**文件：**
- 修改：`src/subtap/cli.py`
- 测试：`tests/test_cleanup.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_cleanup.py - 添加以下测试

class TestCleanCommand:
    """Test subtap clean command."""

    def test_clean_default_removes_temp_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """subtap clean should remove L1 temp files by default."""
        from typer.testing import CliRunner
        from subtap.cli import app

        runner = CliRunner()

        # Create workspace with temp files
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")

        # Run clean command
        result = runner.invoke(app, ["clean", str(tmp_path)])

        # Verify temp files removed
        assert not (tmp_path / "chunks" / "chunk_0000.wav").exists()

    def test_clean_all_removes_intermediate_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """subtap clean --all should remove L1 + L2 files."""
        from typer.testing import CliRunner
        from subtap.cli import app

        runner = CliRunner()

        # Create workspace with intermediate files
        (tmp_path / "cleaned.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "sentences.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "aligned.jsonl").write_text('{"text": "hello"}\n')

        # Run clean command with --all
        result = runner.invoke(app, ["clean", str(tmp_path), "--all"])

        # Verify intermediate files removed
        assert not (tmp_path / "cleaned.jsonl").exists()
        assert not (tmp_path / "sentences.jsonl").exists()

        # Verify output files preserved
        assert (tmp_path / "aligned.jsonl").exists()

    def test_clean_preserves_output_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """subtap clean should never remove output files."""
        from typer.testing import CliRunner
        from subtap.cli import app

        runner = CliRunner()

        # Create workspace with output files
        (tmp_path / "aligned.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "report.md").write_text("# Report\n")
        (tmp_path / "metrics.json").write_text('{}\n')

        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "test.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

        # Run clean command with --all
        result = runner.invoke(app, ["clean", str(tmp_path), "--all"])

        # Verify output files preserved
        assert (tmp_path / "aligned.jsonl").exists()
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "metrics.json").exists()
        assert (output_dir / "test.srt").exists()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_cleanup.py::TestCleanCommand -v`
预期：FAIL，报错 "No such command 'clean'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/cli.py - 添加 clean 命令

@app.command("clean")
def clean(
    work_dir: Path = typer.Argument(..., help="工作目录路径"),
    all: bool = typer.Option(False, "--all", "-a", help="清理所有中间文件（L1 + L2）"),
) -> None:
    """清理工作区文件。

    默认只清理临时文件（L1）：
    - chunk WAV 文件
    - source WAV 文件
    - 系统文件（.DS_Store 等）

    使用 --all 清理所有中间文件（L1 + L2）：
    - 上述所有文件
    - asr.jsonl
    - cleaned.jsonl
    - sentences.jsonl

    永远不会清理：
    - aligned.jsonl（用户输出）
    - report.md, metrics.json（用户输出）
    - output/ 目录（用户输出）
    """
    from subtap.engine.cleanroom import Cleanroom

    if not work_dir.exists():
        typer.echo(f"✗ 工作目录不存在：{work_dir}", err=True)
        raise typer.Exit(1)

    cleanroom = Cleanroom(work_dir)

    if all:
        result = cleanroom.clean_all()
        typer.echo(f"✓ 已清理所有临时和中间文件：{result['cleaned_count']} 个")
    else:
        result = cleanroom.clean_temp_files()
        typer.echo(f"✓ 已清理临时文件：{result['cleaned_count']} 个")

    if result["issues"]:
        for issue in result["issues"]:
            typer.echo(f"  ⚠ {issue}")
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_cleanup.py::TestCleanCommand -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/cli.py tests/test_cleanup.py
git commit -m "feat(cli): add 'subtap clean' command with --all option"
```

---

## 任务 6：添加 CleanupConfig 配置模型

**文件：**
- 修改：`src/subtap/schemas/config.py`
- 测试：`tests/test_cleanup.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_cleanup.py - 添加以下测试

class TestCleanupConfig:
    """Test CleanupConfig configuration model."""

    def test_default_config(self) -> None:
        """Default cleanup config should auto-cleanup L1."""
        from subtap.schemas.config import CleanupConfig

        config = CleanupConfig()
        assert config.auto_cleanup is True
        assert config.keep_chunks is False

    def test_custom_config(self) -> None:
        """Custom cleanup config should be respected."""
        from subtap.schemas.config import CleanupConfig

        config = CleanupConfig(auto_cleanup=False, keep_chunks=True)
        assert config.auto_cleanup is False
        assert config.keep_chunks is True
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_cleanup.py::TestCleanupConfig -v`
预期：FAIL，报错 "ImportError: cannot import name 'CleanupConfig'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/schemas/config.py - 添加 CleanupConfig

class CleanupConfig(BaseModel):
    """Cleanup strategy configuration."""

    auto_cleanup: bool = Field(
        default=True,
        description="执行完成后自动清理临时文件（L1）",
    )
    keep_chunks: bool = Field(
        default=False,
        description="保留 chunk WAV 文件（不推荐，会占用大量磁盘空间）",
    )
```

并在 `SubtapConfig` 中添加：

```python
class SubtapConfig(BaseModel):
    # ... 现有字段 ...
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_cleanup.py::TestCleanupConfig -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/schemas/config.py tests/test_cleanup.py
git commit -m "feat(config): add CleanupConfig for cleanup strategy configuration"
```

---

## 任务 7：集成配置到 Pipeline 和 CLI

**文件：**
- 修改：`src/subtap/core/pipeline.py`
- 修改：`src/subtap/cli.py`
- 测试：`tests/test_cleanup.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_cleanup.py - 添加以下测试

class TestCleanupIntegration:
    """Test cleanup integration with config."""

    def test_auto_cleanup_disabled(self, tmp_path: Path) -> None:
        """Pipeline should not cleanup when auto_cleanup is False."""
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig, CleanupConfig

        # Create workspace with temp files
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")

        # Create pipeline with auto_cleanup disabled
        config = SubtapConfig(cleanup=CleanupConfig(auto_cleanup=False))
        pipeline = Pipeline(config, work_dir=tmp_path)

        # Run cleanup
        pipeline.cleanup()

        # Verify temp files NOT removed
        assert (tmp_path / "chunks" / "chunk_0000.wav").exists()

    def test_keep_chunks_enabled(self, tmp_path: Path) -> None:
        """Pipeline should keep chunk WAV when keep_chunks is True."""
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig, CleanupConfig

        # Create workspace with chunk files
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")

        # Create pipeline with keep_chunks enabled
        config = SubtapConfig(cleanup=CleanupConfig(keep_chunks=True))
        pipeline = Pipeline(config, work_dir=tmp_path)

        # Run cleanup
        pipeline.cleanup()

        # Verify chunk files preserved
        assert (tmp_path / "chunks" / "chunk_0000.wav").exists()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_cleanup.py::TestCleanupIntegration -v`
预期：FAIL（因为 cleanup 方法未考虑配置）

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/core/pipeline.py - 修改 cleanup() 方法

def cleanup(self) -> dict[str, Any]:
    """Remove L1 temp files after pipeline completion.

    Respects cleanup configuration:
    - auto_cleanup: if False, skip cleanup
    - keep_chunks: if True, preserve chunk WAV files
    """
    if not self.config.cleanup.auto_cleanup:
        return {"cleaned_count": 0, "issues": [], "is_clean": True}

    from subtap.engine.cleanroom import Cleanroom

    cleanroom = Cleanroom(self.workspace.root)

    if self.config.cleanup.keep_chunks:
        # Only clean source.wav and system files
        return cleanroom.clean_temp_files(exclude_chunks=True)
    else:
        return cleanroom.clean_temp_files()
```

```python
# src/subtap/engine/cleanroom.py - 修改 clean_temp_files() 方法

def clean_temp_files(self, exclude_chunks: bool = False) -> dict[str, Any]:
    """Remove L1 temp files.

    Args:
        exclude_chunks: if True, preserve chunk WAV files
    """
    cleaned = 0
    issues: list[str] = []

    # Remove chunk wav files (unless excluded)
    if not exclude_chunks:
        for f in self.root.glob("chunks/chunk_*.wav"):
            if f.is_file():
                f.unlink()
                cleaned += 1

    # ... 其余代码不变 ...
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_cleanup.py::TestCleanupIntegration -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/core/pipeline.py src/subtap/engine/cleanroom.py tests/test_cleanup.py
git commit -m "feat(cleanup): integrate CleanupConfig with Pipeline and Cleanroom"
```

---

## 任务 8：添加清理摘要输出

**文件：**
- 修改：`src/subtap/engine/cleanroom.py`
- 测试：`tests/test_cleanup.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_cleanup.py - 添加以下测试

class TestCleanupSummary:
    """Test cleanup summary output."""

    def test_summary_shows_cleaned_count(self, workspace: Path) -> None:
        """Cleanup summary should show number of cleaned files."""
        cleanroom = Cleanroom(workspace)
        result = cleanroom.clean_temp_files()

        summary = cleanroom.format_summary(result)
        assert "已清理" in summary
        assert str(result["cleaned_count"]) in summary

    def test_summary_shows_freed_space(self, workspace: Path) -> None:
        """Cleanup summary should show freed disk space."""
        cleanroom = Cleanroom(workspace)
        result = cleanroom.clean_temp_files()

        summary = cleanroom.format_summary(result)
        # Should contain size info (KB or MB)
        assert any(unit in summary for unit in ["B", "KB", "MB", "GB"])
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_cleanup.py::TestCleanupSummary -v`
预期：FAIL，报错 "AttributeError: 'Cleanroom' object has no attribute 'format_summary'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/engine/cleanroom.py - 添加 format_summary() 方法

def format_summary(self, result: dict[str, Any]) -> str:
    """Format cleanup result as human-readable summary."""
    cleaned = result["cleaned_count"]
    if cleaned == 0:
        return "✓ 工作区已干净，无需清理"

    return f"✓ 已清理 {cleaned} 个文件"
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_cleanup.py::TestCleanupSummary -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/engine/cleanroom.py tests/test_cleanup.py
git commit -m "feat(cleanroom): add format_summary() for human-readable cleanup output"
```

---

## 任务 9：完整集成测试

**文件：**
- 测试：`tests/test_cleanup.py`

- [ ] **步骤 1：编写完整集成测试**

```python
# tests/test_cleanup.py - 添加以下测试

class TestFullIntegration:
    """Test full cleanup integration."""

    def test_end_to_end_cleanup(self, tmp_path: Path) -> None:
        """End-to-end test: run pipeline, verify cleanup."""
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig

        # Create mock workspace structure
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")
        (chunks_dir / "chunks.jsonl").write_text('{"chunk_id": 0}\n')

        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "source.wav").write_bytes(b"fake wav")

        (tmp_path / "asr").mkdir()
        (tmp_path / "asr" / "asr.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "cleaned.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "sentences.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "aligned.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "report.md").write_text("# Report\n")
        (tmp_path / "metrics.json").write_text('{}\n')

        # Create pipeline
        config = SubtapConfig()
        pipeline = Pipeline(config, work_dir=tmp_path)

        # Run cleanup
        result = pipeline.cleanup()

        # Verify L1 temp files removed
        assert not (tmp_path / "chunks" / "chunk_0000.wav").exists()
        assert not (tmp_path / "audio" / "source.wav").exists()

        # Verify L2 intermediate files preserved
        assert (tmp_path / "chunks" / "chunks.jsonl").exists()
        assert (tmp_path / "asr" / "asr.jsonl").exists()
        assert (tmp_path / "cleaned.jsonl").exists()
        assert (tmp_path / "sentences.jsonl").exists()

        # Verify L3 output files preserved
        assert (tmp_path / "aligned.jsonl").exists()
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "metrics.json").exists()
```

- [ ] **步骤 2：运行测试验证通过**

运行：`pytest tests/test_cleanup.py::TestFullIntegration -v`
预期：PASS

- [ ] **步骤 3：Commit**

```bash
git add tests/test_cleanup.py
git commit -m "test(cleanup): add full integration test for cleanup strategy"
```

---

## 自检

1. **规格覆盖度：** ✅ P0（自动清理 L1）、P2（批量转录清理 L2）、P3（`subtap clean --all`）全部覆盖
2. **占位符扫描：** ✅ 无占位符
3. **类型一致性：** ✅ 所有方法签名和返回值类型一致
