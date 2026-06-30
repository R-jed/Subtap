"""Cleanroom 分层清理方法测试。"""

from __future__ import annotations

import pytest
from pathlib import Path

from subtap.engine.cleanroom import Cleanroom
from subtap.schemas.config import CleanupConfig


class TestCleanupConfig:
    """测试 CleanupConfig 配置模型。"""

    def test_default_config(self) -> None:
        """默认清理配置应自动清理 L1。"""
        config = CleanupConfig()
        assert config.auto_cleanup is True
        assert config.keep_chunks is False

    def test_custom_config(self) -> None:
        """自定义清理配置应被正确应用。"""
        config = CleanupConfig(auto_cleanup=False, keep_chunks=True)
        assert config.auto_cleanup is False
        assert config.keep_chunks is True


@pytest.fixture
def tmp_work(tmp_path: Path) -> Path:
    """创建模拟的工作区目录结构。"""
    # 创建子目录
    (tmp_path / "audio").mkdir()
    (tmp_path / "chunks").mkdir()
    (tmp_path / "asr").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "logs").mkdir()
    return tmp_path


@pytest.fixture
def cleanroom(tmp_work: Path) -> Cleanroom:
    return Cleanroom(tmp_work)


def _create_file(path: Path, content: str = "dummy") -> Path:
    """辅助函数：创建文件并写入内容。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


class TestCleanTempFiles:
    """测试 L1 临时文件清理。"""

    def test_removes_chunk_wav_files(self, cleanroom: Cleanroom, tmp_work: Path):
        """应删除 chunk WAV 文件。"""
        chunk1 = _create_file(tmp_work / "chunks" / "chunk_0001.wav")
        chunk2 = _create_file(tmp_work / "chunks" / "chunk_0002.wav")
        # 保留 chunks.jsonl 不被删除
        chunks_jsonl = _create_file(tmp_work / "chunks" / "chunks.jsonl")

        result = cleanroom.clean_temp_files()

        assert not chunk1.exists()
        assert not chunk2.exists()
        assert chunks_jsonl.exists()
        assert result["cleaned_count"] >= 2

    def test_removes_source_wav(self, cleanroom: Cleanroom, tmp_work: Path):
        """应删除 source WAV 文件。"""
        source = _create_file(tmp_work / "audio" / "source.wav")

        result = cleanroom.clean_temp_files()

        assert not source.exists()
        assert result["cleaned_count"] >= 1

    def test_removes_system_files(self, cleanroom: Cleanroom, tmp_work: Path):
        """应删除 .DS_Store、Thumbs.db 等系统文件。"""
        ds_store = _create_file(tmp_work / "audio" / ".DS_Store")
        thumbs = _create_file(tmp_work / "Thumbs.db")

        result = cleanroom.clean_temp_files()

        assert not ds_store.exists()
        assert not thumbs.exists()
        assert result["cleaned_count"] >= 2

    def test_removes_pycache(self, cleanroom: Cleanroom, tmp_work: Path):
        """应删除 __pycache__ 目录。"""
        pycache = tmp_work / "chunks" / "__pycache__"
        pycache.mkdir()
        (pycache / "module.pyc").write_text("")

        result = cleanroom.clean_temp_files()

        assert not pycache.exists()
        assert result["cleaned_count"] >= 1

    def test_exclude_chunks_preserves_chunk_wav(
        self, cleanroom: Cleanroom, tmp_work: Path
    ):
        """exclude_chunks=True 时保留 chunk WAV 文件。"""
        chunk1 = _create_file(tmp_work / "chunks" / "chunk_0001.wav")
        source = _create_file(tmp_work / "audio" / "source.wav")

        result = cleanroom.clean_temp_files(exclude_chunks=True)

        assert chunk1.exists(), "chunk WAV 应被保留"
        assert not source.exists(), "source WAV 应被删除"

    def test_returns_cleaned_count_and_files(self, cleanroom: Cleanroom, tmp_work: Path):
        """返回值应包含 cleaned_count 和 cleaned_files 列表。"""
        _create_file(tmp_work / "chunks" / "chunk_0001.wav")
        _create_file(tmp_work / "audio" / "source.wav")

        result = cleanroom.clean_temp_files()

        assert "cleaned_count" in result
        assert "cleaned_files" in result
        assert result["cleaned_count"] == 2
        assert len(result["cleaned_files"]) == 2

    def test_does_not_delete_intermediate_files(self, cleanroom: Cleanroom, tmp_work: Path):
        """L1 清理不应删除 L2 中间文件。"""
        asr_jsonl = _create_file(tmp_work / "asr" / "asr.jsonl")
        cleaned_jsonl = _create_file(tmp_work / "cleaned.jsonl")
        sentences_jsonl = _create_file(tmp_work / "sentences.jsonl")

        cleanroom.clean_temp_files()

        assert asr_jsonl.exists()
        assert cleaned_jsonl.exists()
        assert sentences_jsonl.exists()

    def test_does_not_delete_protected_files(self, cleanroom: Cleanroom, tmp_work: Path):
        """永远不删除 aligned.jsonl、report.md、metrics.json、output/。"""
        aligned = _create_file(tmp_work / "aligned.jsonl")
        report = _create_file(tmp_work / "report.md")
        metrics = _create_file(tmp_work / "metrics.json")
        output_file = _create_file(tmp_work / "output" / "output.srt")

        cleanroom.clean_temp_files()

        assert aligned.exists()
        assert report.exists()
        assert metrics.exists()
        assert output_file.exists()


class TestCleanIntermediateFiles:
    """测试 L2 中间文件清理。"""

    def test_removes_asr_jsonl(self, cleanroom: Cleanroom, tmp_work: Path):
        """应删除 asr/asr.jsonl。"""
        asr = _create_file(tmp_work / "asr" / "asr.jsonl")

        result = cleanroom.clean_intermediate_files()

        assert not asr.exists()
        assert result["cleaned_count"] >= 1

    def test_removes_cleaned_jsonl(self, cleanroom: Cleanroom, tmp_work: Path):
        """应删除 cleaned.jsonl。"""
        cleaned = _create_file(tmp_work / "cleaned.jsonl")

        result = cleanroom.clean_intermediate_files()

        assert not cleaned.exists()

    def test_removes_sentences_jsonl(self, cleanroom: Cleanroom, tmp_work: Path):
        """应删除 sentences.jsonl。"""
        sentences = _create_file(tmp_work / "sentences.jsonl")

        result = cleanroom.clean_intermediate_files()

        assert not sentences.exists()

    def test_never_removes_aligned_jsonl(self, cleanroom: Cleanroom, tmp_work: Path):
        """永远不删除 aligned.jsonl。"""
        aligned = _create_file(tmp_work / "aligned.jsonl")

        cleanroom.clean_intermediate_files()

        assert aligned.exists()

    def test_never_removes_report_and_metrics(
        self, cleanroom: Cleanroom, tmp_work: Path
    ):
        """永远不删除 report.md 和 metrics.json。"""
        report = _create_file(tmp_work / "report.md")
        metrics = _create_file(tmp_work / "metrics.json")

        cleanroom.clean_intermediate_files()

        assert report.exists()
        assert metrics.exists()

    def test_never_removes_output_directory(
        self, cleanroom: Cleanroom, tmp_work: Path
    ):
        """永远不删除 output/ 目录及其内容。"""
        output_file = _create_file(tmp_work / "output" / "output.srt")

        cleanroom.clean_intermediate_files()

        assert output_file.exists()

    def test_does_not_delete_temp_files(self, cleanroom: Cleanroom, tmp_work: Path):
        """L2 清理不应删除 L1 临时文件。"""
        chunk = _create_file(tmp_work / "chunks" / "chunk_0001.wav")
        source = _create_file(tmp_work / "audio" / "source.wav")

        cleanroom.clean_intermediate_files()

        assert chunk.exists()
        assert source.exists()

    def test_returns_cleaned_count_and_files(
        self, cleanroom: Cleanroom, tmp_work: Path
    ):
        """返回值应包含 cleaned_count 和 cleaned_files 列表。"""
        _create_file(tmp_work / "asr" / "asr.jsonl")
        _create_file(tmp_work / "cleaned.jsonl")
        _create_file(tmp_work / "sentences.jsonl")

        result = cleanroom.clean_intermediate_files()

        assert result["cleaned_count"] == 3
        assert len(result["cleaned_files"]) == 3

    def test_removes_asr_draft_jsonl(self, cleanroom: Cleanroom, tmp_work: Path):
        """应删除 asr/asr_draft.jsonl。"""
        draft = _create_file(tmp_work / "asr" / "asr_draft.jsonl")

        result = cleanroom.clean_intermediate_files()

        assert not draft.exists()


class TestCleanAll:
    """测试完整清理（L1 + L2）。"""

    def test_cleans_all_temp_and_intermediate(
        self, cleanroom: Cleanroom, tmp_work: Path
    ):
        """clean_all 应清理所有 L1 和 L2 文件。"""
        chunk = _create_file(tmp_work / "chunks" / "chunk_0001.wav")
        source = _create_file(tmp_work / "audio" / "source.wav")
        asr = _create_file(tmp_work / "asr" / "asr.jsonl")
        cleaned = _create_file(tmp_work / "cleaned.jsonl")
        sentences = _create_file(tmp_work / "sentences.jsonl")

        result = cleanroom.clean_all()

        assert not chunk.exists()
        assert not source.exists()
        assert not asr.exists()
        assert not cleaned.exists()
        assert not sentences.exists()
        assert result["cleaned_count"] == 5

    def test_never_removes_protected_files(
        self, cleanroom: Cleanroom, tmp_work: Path
    ):
        """clean_all 永远不删除受保护文件。"""
        aligned = _create_file(tmp_work / "aligned.jsonl")
        report = _create_file(tmp_work / "report.md")
        metrics = _create_file(tmp_work / "metrics.json")
        output_file = _create_file(tmp_work / "output" / "output.srt")

        cleanroom.clean_all()

        assert aligned.exists()
        assert report.exists()
        assert metrics.exists()
        assert output_file.exists()

    def test_returns_combined_results(self, cleanroom: Cleanroom, tmp_work: Path):
        """clean_all 返回合并的清理结果。"""
        _create_file(tmp_work / "chunks" / "chunk_0001.wav")
        _create_file(tmp_work / "audio" / "source.wav")
        _create_file(tmp_work / "asr" / "asr.jsonl")
        _create_file(tmp_work / "cleaned.jsonl")

        result = cleanroom.clean_all()

        assert "cleaned_count" in result
        assert "cleaned_files" in result
        assert result["cleaned_count"] == 4


class TestCleanupSummary:
    """测试清理结果摘要格式化。"""

    def test_summary_shows_cleaned_count(self, tmp_path: Path) -> None:
        """清理摘要应显示已清理文件数量。"""
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")

        cleanroom = Cleanroom(tmp_path)
        result = cleanroom.clean_temp_files()

        summary = cleanroom.format_summary(result)
        assert "已清理" in summary
        assert str(result["cleaned_count"]) in summary

    def test_summary_shows_no_cleanup_needed(self, tmp_path: Path) -> None:
        """工作区干净时应显示无需清理。"""
        cleanroom = Cleanroom(tmp_path)
        result = cleanroom.clean_temp_files()

        summary = cleanroom.format_summary(result)
        assert "无需清理" in summary

    def test_format_summary_with_cleaned_files(
        self, cleanroom: Cleanroom, tmp_work: Path
    ):
        """应格式化包含已清理文件列表的摘要。"""
        result = {
            "cleaned_count": 3,
            "cleaned_files": [
                "chunks/chunk_0001.wav",
                "audio/source.wav",
                "asr/asr.jsonl",
            ],
            "is_clean": True,
            "issues": [],
        }

        summary = cleanroom.format_summary(result)

        assert isinstance(summary, str)
        assert "3" in summary  # 包含数量
        assert "chunk_0001.wav" in summary  # 包含文件名

    def test_format_summary_with_issues(self, cleanroom: Cleanroom):
        """有问题时应包含问题描述。"""
        result = {
            "cleaned_count": 1,
            "cleaned_files": ["chunks/chunk_0001.wav"],
            "is_clean": False,
            "issues": ["已清理损坏的 event.log.jsonl"],
        }

        summary = cleanroom.format_summary(result)

        assert "event.log.jsonl" in summary or "损坏" in summary


class TestCleanupIntegration:
    """测试 CleanupConfig 集成到 Pipeline 和 Cleanroom。"""

    def test_auto_cleanup_disabled(self, tmp_path: Path) -> None:
        """auto_cleanup=False 时 Pipeline 不应执行清理。"""
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig, CleanupConfig

        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")

        config = SubtapConfig(cleanup=CleanupConfig(auto_cleanup=False))
        pipeline = Pipeline(config, work_dir=tmp_path)
        pipeline.cleanup()

        assert (tmp_path / "chunks" / "chunk_0000.wav").exists()

    def test_keep_chunks_enabled(self, tmp_path: Path) -> None:
        """keep_chunks=True 时 Pipeline 应保留 chunk WAV 文件。"""
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig, CleanupConfig

        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")

        config = SubtapConfig(cleanup=CleanupConfig(keep_chunks=True))
        pipeline = Pipeline(config, work_dir=tmp_path)
        pipeline.cleanup()

        assert (tmp_path / "chunks" / "chunk_0000.wav").exists()

    def test_default_cleanup_removes_all(self, tmp_path: Path) -> None:
        """默认配置（auto_cleanup=True, keep_chunks=False）应清理所有 L1 文件。"""
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig, CleanupConfig

        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")

        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "source.wav").write_bytes(b"fake wav")

        config = SubtapConfig(cleanup=CleanupConfig())
        pipeline = Pipeline(config, work_dir=tmp_path)
        result = pipeline.cleanup()

        assert not (tmp_path / "chunks" / "chunk_0000.wav").exists()
        assert not (tmp_path / "audio" / "source.wav").exists()
        assert result["cleaned_count"] >= 2


class TestPipelineCleanup:
    """测试 Pipeline 的 cleanup 方法。"""

    def test_cleanup_removes_temp_files(self, tmp_path: Path) -> None:
        """Pipeline.cleanup() 应清理 L1 临时文件。"""
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig

        # 创建 chunk WAV 文件
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")

        # 创建 source WAV 文件
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "source.wav").write_bytes(b"fake wav")

        config = SubtapConfig()
        pipeline = Pipeline(config, work_dir=tmp_path)
        result = pipeline.cleanup()

        assert not (tmp_path / "chunks" / "chunk_0000.wav").exists()
        assert not (tmp_path / "audio" / "source.wav").exists()
        assert result["cleaned_count"] >= 2

    def test_cleanup_preserves_intermediate_files(self, tmp_path: Path) -> None:
        """Pipeline.cleanup() 应保留 L2 中间文件。"""
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig

        # 创建中间文件
        (tmp_path / "cleaned.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "sentences.jsonl").write_text('{"text": "hello"}\n')

        config = SubtapConfig()
        pipeline = Pipeline(config, work_dir=tmp_path)
        pipeline.cleanup()

        assert (tmp_path / "cleaned.jsonl").exists()
        assert (tmp_path / "sentences.jsonl").exists()


class TestBatchCleanup:
    """测试批量转录完成后的清理行为。"""

    def test_batch_transcribe_calls_cleanup_on_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """批量转录成功处理文件后应调用 clean_intermediate_files() 清理 L2 中间文件。"""
        from unittest.mock import MagicMock, patch
        from typer.testing import CliRunner
        from subtap.cli import app
        from subtap.schemas.config import SubtapConfig

        runner = CliRunner()
        config = SubtapConfig()
        monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)
        monkeypatch.setattr("subtap.cli.Path.home", lambda: tmp_path)

        # 创建测试音频文件
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake wav")

        # 创建输出目录
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 模拟 PlainRunner.run_pipeline 返回成功结果
        mock_result = {
            "timings": {"prepare": 0.1, "chunk": 0.2},
            "output_path": str(output_dir / "batch.srt"),
        }

        # 用于捕获 clean_intermediate_files 的调用
        cleanup_called = []
        original_clean = None

        with patch("subtap.ui.tui.PlainRunner") as mock_runner_class:
            mock_runner = MagicMock()
            mock_runner.run_pipeline.return_value = mock_result
            mock_runner_class.return_value = mock_runner

            # 模拟 Cleanroom.clean_intermediate_files
            with patch("subtap.engine.cleanroom.Cleanroom.clean_intermediate_files") as mock_clean:
                mock_clean.return_value = {"cleaned_count": 3, "cleaned_files": []}

                # 运行批量转录
                result = runner.invoke(app, [
                    "batch-transcribe", str(audio_file),
                    "--output-dir", str(output_dir),
                    "--no-confirm",
                    "--json",
                ])

                # 验证 clean_intermediate_files 被调用
                assert mock_clean.called, "batch_transcribe 成功后应调用 clean_intermediate_files()"

    def test_batch_transcribe_no_cleanup_on_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """批量转录失败时不应调用 clean_intermediate_files()。"""
        from unittest.mock import MagicMock, patch
        from typer.testing import CliRunner
        from subtap.cli import app
        from subtap.schemas.config import SubtapConfig

        runner = CliRunner()
        config = SubtapConfig()
        monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)
        monkeypatch.setattr("subtap.cli.Path.home", lambda: tmp_path)

        # 创建测试音频文件
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake wav")

        # 创建输出目录
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 模拟 PlainRunner.run_pipeline 抛出异常
        with patch("subtap.ui.tui.PlainRunner") as mock_runner_class:
            mock_runner = MagicMock()
            mock_runner.run_pipeline.side_effect = RuntimeError("模拟处理失败")
            mock_runner_class.return_value = mock_runner

            # 模拟 Cleanroom.clean_intermediate_files
            with patch("subtap.engine.cleanroom.Cleanroom.clean_intermediate_files") as mock_clean:
                mock_clean.return_value = {"cleaned_count": 3, "cleaned_files": []}

                # 运行批量转录
                result = runner.invoke(app, [
                    "batch-transcribe", str(audio_file),
                    "--output-dir", str(output_dir),
                    "--no-confirm",
                    "--json",
                ])

                # 验证 clean_intermediate_files 未被调用
                assert not mock_clean.called, "batch_transcribe 失败时不应调用 clean_intermediate_files()"


class TestCLIRunCleanup:
    """测试 CLI run 命令完成后的清理行为。"""

    def test_run_cleanup_removes_temp_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI run 应在成功执行后调用 pipeline.cleanup() 清理临时文件。"""
        from unittest.mock import MagicMock, patch
        from typer.testing import CliRunner
        from subtap.cli import app
        from subtap.schemas.config import SubtapConfig

        runner = CliRunner()
        config = SubtapConfig()
        monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)
        monkeypatch.setattr("subtap.cli.Path.home", lambda: tmp_path)

        # 创建测试音频文件
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake wav")

        # 模拟 PlainRunner 成功执行并创建临时文件
        work_dir = tmp_path / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        chunks_dir = work_dir / "chunks"
        chunks_dir.mkdir(exist_ok=True)

        # 创建模拟的 chunk WAV 文件（这些应该被 cleanup 清理）
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake chunk wav")
        (chunks_dir / "chunk_0001.wav").write_bytes(b"fake chunk wav")
        (chunks_dir / "chunks.jsonl").write_text('{"chunk_id": 0}\n')

        # 模拟 PlainRunner.run_pipeline 返回成功结果
        mock_result = {
            "timings": {"prepare": 0.1, "chunk": 0.2},
            "output_path": str(tmp_path / "output" / "draft.srt"),
        }

        with patch("subtap.ui.tui.PlainRunner") as mock_runner_class:
            mock_runner = MagicMock()
            mock_runner.run_pipeline.return_value = mock_result
            mock_runner_class.return_value = mock_runner

            # 运行 pipeline（禁用 cleanroom 预检查，避免它清理文件）
            result = runner.invoke(app, [
                "run", str(audio_file),
                "-w", str(work_dir),
                "-o", str(tmp_path / "output"),
                "--no-tui",
                "--no-align",
                "--no-cleanroom",
                "--no-git-check",
            ])

        # 验证 cleanup 发生：chunk WAV 文件应该被清理
        assert work_dir.exists(), "工作目录应该存在"
        chunk_wavs = list(chunks_dir.glob("chunk_*.wav"))
        assert len(chunk_wavs) == 0, "chunk WAV 文件应该被 pipeline.cleanup() 清理"


class TestFullIntegration:
    """端到端集成测试：验证完整清理策略。"""

    def test_end_to_end_cleanup(self, tmp_path: Path) -> None:
        """端到端测试：运行 pipeline，验证清理行为。"""
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig

        # 创建模拟的工作区结构
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

        # 创建 pipeline
        config = SubtapConfig()
        pipeline = Pipeline(config, work_dir=tmp_path)

        # 运行清理
        result = pipeline.cleanup()

        # 验证 L1 临时文件已移除
        assert not (tmp_path / "chunks" / "chunk_0000.wav").exists()
        assert not (tmp_path / "audio" / "source.wav").exists()

        # 验证 L2 中间文件被保留
        assert (tmp_path / "chunks" / "chunks.jsonl").exists()
        assert (tmp_path / "asr" / "asr.jsonl").exists()
        assert (tmp_path / "cleaned.jsonl").exists()
        assert (tmp_path / "sentences.jsonl").exists()

        # 验证 L3 输出文件被保留
        assert (tmp_path / "aligned.jsonl").exists()
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "metrics.json").exists()

    def test_full_cleanup_removes_intermediate(self, tmp_path: Path) -> None:
        """全部清理应移除 L1 + L2 文件。"""
        from subtap.engine.cleanroom import Cleanroom

        # 创建包含所有类型文件的工作区
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")
        (chunks_dir / "chunks.jsonl").write_text('{"chunk_id": 0}\n')

        (tmp_path / "asr").mkdir()
        (tmp_path / "asr" / "asr.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "cleaned.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "sentences.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "aligned.jsonl").write_text('{"text": "hello"}\n')

        # 运行全部清理
        cleanroom = Cleanroom(tmp_path)
        result = cleanroom.clean_all()

        # 验证 L1 已移除
        assert not (tmp_path / "chunks" / "chunk_0000.wav").exists()

        # 验证 L2 已移除
        assert not (tmp_path / "asr" / "asr.jsonl").exists()
        assert not (tmp_path / "cleaned.jsonl").exists()
        assert not (tmp_path / "sentences.jsonl").exists()

        # 验证 L3 被保留
        assert (tmp_path / "aligned.jsonl").exists()
        assert (tmp_path / "chunks" / "chunks.jsonl").exists()


class TestCleanCommand:
    """测试 CLI clean 命令。"""

    def test_clean_default_removes_temp_files(self, tmp_path: Path) -> None:
        """subtap clean 应默认移除 L1 临时文件。"""
        from typer.testing import CliRunner
        from subtap.cli import app

        runner = CliRunner()

        # 创建包含临时文件的工作区
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "chunk_0000.wav").write_bytes(b"fake wav")

        # 运行 clean 命令
        result = runner.invoke(app, ["cleanup", str(tmp_path)])

        # 验证临时文件已移除
        assert not (tmp_path / "chunks" / "chunk_0000.wav").exists()

    def test_clean_all_removes_intermediate_files(self, tmp_path: Path) -> None:
        """subtap clean --all 应移除 L1 + L2 文件。"""
        from typer.testing import CliRunner
        from subtap.cli import app

        runner = CliRunner()

        # 创建包含中间文件的工作区
        (tmp_path / "cleaned.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "sentences.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "aligned.jsonl").write_text('{"text": "hello"}\n')

        # 运行 clean 命令（带 --all 参数）
        result = runner.invoke(app, ["cleanup", str(tmp_path), "--all"])

        # 验证中间文件已移除
        assert not (tmp_path / "cleaned.jsonl").exists()
        assert not (tmp_path / "sentences.jsonl").exists()

        # 验证输出文件被保留
        assert (tmp_path / "aligned.jsonl").exists()

    def test_clean_preserves_output_files(self, tmp_path: Path) -> None:
        """subtap clean 应永不移除输出文件。"""
        from typer.testing import CliRunner
        from subtap.cli import app

        runner = CliRunner()

        # 创建包含输出文件的工作区
        (tmp_path / "aligned.jsonl").write_text('{"text": "hello"}\n')
        (tmp_path / "report.md").write_text("# Report\n")
        (tmp_path / "metrics.json").write_text('{}\n')

        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "test.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

        # 运行 clean 命令（带 --all 参数）
        result = runner.invoke(app, ["cleanup", str(tmp_path), "--all"])

        # 验证输出文件被保留
        assert (tmp_path / "aligned.jsonl").exists()
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "metrics.json").exists()
        assert (output_dir / "test.srt").exists()
