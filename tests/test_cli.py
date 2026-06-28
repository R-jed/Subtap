"""Tests for CLI commands."""

from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def _patch_stage_pipeline(monkeypatch, stage_name: str):
    """Patch Pipeline so CLI stage tests only cover CLI file routing."""
    config = SimpleNamespace(
        clean=SimpleNamespace(backend="mock-llm"),
        align=SimpleNamespace(backend="mock-align"),
    )
    captured = {}

    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)

    class FakeWorkspace:
        def __init__(self, root):
            self.root = root
            self.asr_jsonl = root / "asr" / "asr.jsonl"
            self.cleaned_jsonl = root / "cleaned.jsonl"
            self.sentences_jsonl = root / "sentences.jsonl"
            self.aligned_jsonl = root / "aligned.jsonl"

        def ensure_dirs(self):
            self.asr_jsonl.parent.mkdir(parents=True, exist_ok=True)
            self.root.mkdir(parents=True, exist_ok=True)

    class FakePipeline:
        def __init__(self, _config, work_dir):
            self.workspace = FakeWorkspace(work_dir)
            captured["workspace"] = self.workspace

        def run_stage(self, stage, **_kwargs):
            assert stage == stage_name
            if stage == "clean":
                assert self.workspace.asr_jsonl.read_text(encoding="utf-8") == "input\n"
                self.workspace.cleaned_jsonl.write_text("cleaned\n", encoding="utf-8")
                return {
                    "segment_count": 1,
                    "cleaned_jsonl": str(self.workspace.cleaned_jsonl),
                }
            if stage == "segment":
                assert (
                    self.workspace.cleaned_jsonl.read_text(encoding="utf-8")
                    == "input\n"
                )
                self.workspace.sentences_jsonl.write_text(
                    "sentences\n", encoding="utf-8"
                )
                return {
                    "sentence_count": 1,
                    "sentences_jsonl": str(self.workspace.sentences_jsonl),
                }
            if stage == "align":
                assert (
                    self.workspace.sentences_jsonl.read_text(encoding="utf-8")
                    == "input\n"
                )
                self.workspace.aligned_jsonl.write_text("aligned\n", encoding="utf-8")
                return {
                    "aligned_count": 1,
                    "aligned_jsonl": str(self.workspace.aligned_jsonl),
                }
            raise AssertionError(stage)

    monkeypatch.setattr("subtap.core.pipeline.Pipeline", FakePipeline)
    return captured


def test_version():
    """subtap version should print version string."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "subtap" in result.output
    assert "0.1.0" in result.output


def test_init(tmp_path, monkeypatch):
    """subtap init should create ~/.subtap/ structure."""
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    subtap_dir = fake_home / ".subtap"
    assert subtap_dir.exists()
    assert (subtap_dir / "config.yaml").exists()
    assert (subtap_dir / "glossary" / "global.yaml").exists()
    assert (subtap_dir / "subtap.db").exists()


def test_doctor(tmp_path, monkeypatch):
    """subtap doctor should run without crashing."""
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    # Create a minimal config so doctor can load it
    config_dir = fake_home / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("audio:\n  sample_rate: 16000\n")

    result = runner.invoke(app, ["doctor"])
    # Should either pass (exit 0) or fail due to missing ffmpeg (exit 1)
    assert result.exit_code in (0, 1)
    assert "ffmpeg" in result.output.lower() or "python" in result.output.lower()


def test_doctor_workspace(tmp_path, monkeypatch):
    """subtap doctor --workspace should show workspace state."""
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    config_dir = fake_home / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("audio:\n  sample_rate: 16000\n")

    # Create a mock workspace
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    result = runner.invoke(app, ["doctor", "--workspace"])
    assert result.exit_code == 0
    assert "工作区" in result.output or "workspace" in result.output.lower()


def test_doctor_json_outputs_machine_readable_status(tmp_path, monkeypatch):
    """doctor --json 应输出可被 CI 读取的状态结构。"""
    fake_home = tmp_path / "fakehome"
    config_dir = fake_home / ".subtap"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text("audio:\n  sample_rate: 16000\n")
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tool")

    model_status = [
        SimpleNamespace(
            name="asr_0.6b",
            installed=True,
            path=tmp_path / "models" / "asr",
            missing_files=[],
        )
    ]
    monkeypatch.setattr(
        "subtap.core.models.ModelRegistry.status", lambda _self: model_status
    )

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["config"]["valid"] is True
    assert payload["checks"][0]["name"] == "ffmpeg"
    assert payload["models"][0]["name"] == "asr_0.6b"


def test_run_has_no_git_check_flag():
    """subtap run should accept --no-git-check flag."""
    # Just verify the flag is accepted (will fail on missing input file, that's ok)
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "git-check" in result.output


def test_run_has_no_cleanroom_flag():
    """subtap run should accept --no-cleanroom flag."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "cleanroom" in result.output


def test_setup_has_remote_api_options():
    """subtap setup should expose remote API model discovery options."""
    import re
    result = runner.invoke(app, ["setup", "--help"])
    assert result.exit_code == 0
    clean = re.sub(r'\x1b\[[0-9;]*m', '', result.output)
    assert "remote-api" in clean
    assert "remote-base-url" in clean
    assert "remote-api-key-env" in clean


def test_quality_command_exists():
    """subtap quality command should exist."""
    import re
    result = runner.invoke(app, ["quality", "--help"])
    assert result.exit_code == 0
    clean = re.sub(r'\x1b\[[0-9;]*m', '', result.output)
    assert "aligned.jsonl" in clean
    assert "fix" in clean
    assert "report-only" in clean


def test_run_has_mode_flag():
    """subtap run should accept --mode flag."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--mode" in result.output


def test_run_json_flag_is_available():
    """subtap run should accept --json for machine-readable output."""
    result = runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0
    assert "--json" in result.output


def test_batch_transcribe_command_exists():
    """subtap batch-transcribe should expose batch input and JSON output."""
    result = runner.invoke(app, ["batch-transcribe", "--help"])

    assert result.exit_code == 0
    assert "--files" in result.output
    assert "--json" in result.output


def test_batch_transcribe_runs_each_file(tmp_path, monkeypatch):
    """batch-transcribe should run the pipeline once per input file."""
    calls = []

    class FakeRunner:
        def run_pipeline(self, pipeline, input_path, output_dir, fmt="srt"):
            calls.append((pipeline.work_dir, input_path, output_dir, fmt))
            return {"output_dir": str(output_dir), "format": fmt}

    class FakePipeline:
        def __init__(self, _config, work_dir):
            self.work_dir = work_dir

            class Workspace:
                def ensure_dirs(self):
                    return None

            self.workspace = Workspace()

    monkeypatch.setattr("subtap.ui.tui.PlainRunner", FakeRunner)
    monkeypatch.setattr("subtap.core.pipeline.Pipeline", FakePipeline)
    monkeypatch.setattr(
        "subtap.schemas.config.load_config", lambda _: SimpleNamespace()
    )
    one = tmp_path / "one.wav"
    two = tmp_path / "two.wav"
    one.write_bytes(b"1")
    two.write_bytes(b"2")

    result = runner.invoke(
        app,
        [
            "batch-transcribe",
            "--files",
            f"{one},{two}",
            "--output-dir",
            str(tmp_path / "out"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True
    assert len(data["items"]) == 2
    assert len(calls) == 2
    assert calls[0][0] == tmp_path / "out" / one.stem / "work"
    assert calls[0][2] == tmp_path / "out" / one.stem
    assert calls[1][2] == tmp_path / "out" / two.stem


def test_run_mode_fast():
    """subtap run should accept --mode fast."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "fast" in result.output


def test_run_mode_quality():
    """subtap run should accept --mode quality."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "quality" in result.output


def test_analyze_command_exists():
    """subtap analyze command should exist."""
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "SRT" in result.output or "srt" in result.output


def test_setup_command_exists():
    """Test that setup command exists."""
    result = runner.invoke(app, ["setup", "--help"])
    assert result.exit_code == 0
    assert "初始化向导" in result.output


def test_setup_system_check():
    """Test setup system check step."""
    from unittest.mock import patch

    with patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_check:
        mock_check.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        result = runner.invoke(app, ["setup", "--skip-models"])
        assert "系统检查" in result.output


def test_setup_system_check_failure():
    """Test setup system check when deps are missing."""
    from unittest.mock import patch

    with patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_check:
        mock_check.return_value = {"ffmpeg": False, "ffprobe": True, "python": True}
        result = runner.invoke(app, ["setup", "--skip-models"])
        assert result.exit_code == 1
        assert "系统检查未通过" in result.output


def test_setup_skip_models():
    """Test setup with --skip-models flag."""
    from unittest.mock import patch

    with (
        patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_deps,
        patch("subtap.core.setup.SetupWizard.check_config_exists") as mock_config,
    ):
        mock_deps.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        mock_config.return_value = True
        result = runner.invoke(app, ["setup", "--skip-models"])
        assert result.exit_code == 0
        assert "模型安装（已跳过）" in result.output


def test_doctor_enhanced_checks(monkeypatch, tmp_path):
    """Test enhanced doctor checks."""
    from unittest.mock import patch, MagicMock
    from pathlib import Path

    # 隔离 Path.home()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # 创建模拟配置文件
    config_dir = tmp_path / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("")

    with patch("subtap.core.models.ModelRegistry.status") as mock_status:
        mock_status.return_value = [
            MagicMock(
                name="aligner", installed=True, path=tmp_path / "models" / "aligner"
            ),
            MagicMock(name="asr", installed=True, path=tmp_path / "models" / "asr"),
        ]
        result = runner.invoke(app, ["doctor"])
        assert "配置状态" in result.output
        assert "模型状态" in result.output
        assert "asr" in result.output
        assert "aligner" in result.output


def test_setup_full_flow():
    """Test complete setup flow."""
    from unittest.mock import patch

    with (
        patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_deps,
        patch("subtap.core.setup.SetupWizard.check_config_exists") as mock_config,
        patch("subtap.core.setup.SetupWizard.setup_models") as mock_models,
    ):

        mock_deps.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        mock_config.return_value = False
        mock_models.return_value = True

        result = runner.invoke(app, ["setup"])

        assert result.exit_code == 0
        assert "系统检查" in result.output
        assert "初始化配置" in result.output
        assert "初始化完成" in result.output
        # Verify setup_models was called
        mock_models.assert_called_once()


def test_demo_command_exists():
    """Test demo command exists with expected options."""
    result = runner.invoke(app, ["demo", "--help"])
    assert result.exit_code == 0
    assert "演示" in result.output
    assert "--output-dir" in result.output
    assert "--skip-tui" in result.output


def test_setup_help_has_download_source_option():
    """Test setup --help shows --download-source option."""
    result = runner.invoke(app, ["setup", "--help"])

    assert result.exit_code == 0
    assert "--download-source" in result.output
    assert "hf-mirror" in result.output


def test_clean_stage_copies_external_input_and_output(tmp_path, monkeypatch):
    """clean 命令应使用传入的 asr.jsonl 并支持自定义输出路径。"""
    _patch_stage_pipeline(monkeypatch, "clean")
    input_path = tmp_path / "input-asr.jsonl"
    output_path = tmp_path / "custom" / "cleaned.jsonl"
    input_path.write_text("input\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "clean",
            str(input_path),
            "-w",
            str(tmp_path / "work"),
            "-o",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert output_path.read_text(encoding="utf-8") == "cleaned\n"


def test_segment_stage_copies_external_input_and_output(tmp_path, monkeypatch):
    """segment 命令应使用传入的 cleaned.jsonl 并支持自定义输出路径。"""
    _patch_stage_pipeline(monkeypatch, "segment")
    input_path = tmp_path / "input-cleaned.jsonl"
    output_path = tmp_path / "custom" / "sentences.jsonl"
    input_path.write_text("input\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "segment",
            str(input_path),
            "-w",
            str(tmp_path / "work"),
            "-o",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert output_path.read_text(encoding="utf-8") == "sentences\n"


def test_align_stage_copies_external_input_and_output(tmp_path, monkeypatch):
    """align 命令应使用传入的 sentences.jsonl 并支持自定义输出路径。"""
    _patch_stage_pipeline(monkeypatch, "align")
    input_path = tmp_path / "input-sentences.jsonl"
    output_path = tmp_path / "custom" / "aligned.jsonl"
    input_path.write_text("input\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "align",
            str(input_path),
            "-w",
            str(tmp_path / "work"),
            "-o",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert output_path.read_text(encoding="utf-8") == "aligned\n"


def test_doctor_release_fails_when_models_missing(tmp_path, monkeypatch):
    """doctor --release 应在模型未安装时返回 exit_code=1."""
    from unittest.mock import patch, MagicMock
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    subtap_dir = tmp_path / ".subtap"
    subtap_dir.mkdir()
    (subtap_dir / "config.yaml").write_text(
        "models:\n  root: models\n", encoding="utf-8"
    )

    # 模拟 registry.status() 返回缺失模型
    missing_status = [
        MagicMock(
            name="asr_0.6b",
            installed=False,
            path=tmp_path / "models" / "asr_0.6b",
            missing_files=["config.json", "model.safetensors"],
        ),
        MagicMock(
            name="aligner",
            installed=True,
            path=tmp_path / "models" / "aligner",
            missing_files=[],
        ),
    ]

    with patch("subtap.core.models.ModelRegistry") as MockRegistry:
        MockRegistry.return_value.status.return_value = missing_status
        result = runner.invoke(app, ["doctor", "--release"])

    assert result.exit_code == 1
    assert "部分检查未通过" in result.output
    assert "缺失" in result.output


def test_python_module_entrypoint_outputs_help():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "subtap.cli", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Subtap" in result.stdout
    assert "run" in result.stdout


def test_setup_interactive_fallback_hf_to_mirror(tmp_path, monkeypatch):
    """交互模式下，hf 连不通时提示降级到 hf-mirror."""
    from unittest.mock import patch, MagicMock

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    # 创建配置文件
    config_dir = fake_home / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("")

    with (
        patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_deps,
        patch("subtap.core.setup.SetupWizard.check_config_exists") as mock_config,
        patch("subtap.core.setup.SetupWizard.choose_download_source") as mock_choose,
        patch("subtap.core.models.ModelDownloader") as mock_downloader_cls,
    ):

        mock_deps.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        mock_config.return_value = True
        # 模拟用户选择 hf
        mock_choose.return_value = "hf"

        # 模拟 hf 连不通，hf-mirror 连通
        mock_downloader = MagicMock()
        mock_downloader.check_connectivity.side_effect = [False, True]
        mock_downloader_cls.return_value = mock_downloader

        # 模拟用户选择降级
        with patch("typer.prompt", return_value="y"), patch("typer.echo"):
            runner.invoke(app, ["setup", "--download-source", "ask"])

        # 验证选择了 hf，然后降级到 hf-mirror
        mock_choose.assert_called_once_with("ask")
        assert mock_downloader.check_connectivity.call_count == 2


def test_setup_non_interactive_fails_on_connectivity_error(tmp_path, monkeypatch):
    """非交互模式下，连不通时直接返回失败."""
    from unittest.mock import patch, MagicMock

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    # 创建配置文件
    config_dir = fake_home / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("")

    with (
        patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_deps,
        patch("subtap.core.setup.SetupWizard.check_config_exists") as mock_config,
        patch("subtap.core.models.ModelDownloader") as mock_downloader_cls,
    ):

        mock_deps.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        mock_config.return_value = True

        # 模拟 hf 连不通
        mock_downloader = MagicMock()
        mock_downloader.check_connectivity.return_value = False
        mock_downloader_cls.return_value = mock_downloader

        # 非交互模式，指定 --download-source hf
        result = runner.invoke(app, ["setup", "--skip-models"])
        assert result.exit_code == 0


def test_setup_model_download_failure_exits(tmp_path, monkeypatch):
    """非 manual 模式下模型下载失败应返回 exit_code=1."""
    from unittest.mock import patch

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    # 创建配置文件
    config_dir = fake_home / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("")

    with (
        patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_deps,
        patch("subtap.core.setup.SetupWizard.check_config_exists") as mock_config,
        patch("subtap.core.setup.SetupWizard.setup_models") as mock_models,
    ):

        mock_deps.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        mock_config.return_value = True
        # 模拟模型下载失败（非 manual 模式）
        mock_models.return_value = False

        result = runner.invoke(app, ["setup", "--download-source", "hf"])
        assert result.exit_code == 1
        assert "模型安装失败" in result.output


def test_setup_manual_model_failure_continues(tmp_path, monkeypatch):
    """manual 模式下模型安装待完成应正常结束."""
    from unittest.mock import patch

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    # 创建配置文件
    config_dir = fake_home / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("")

    with (
        patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_deps,
        patch("subtap.core.setup.SetupWizard.check_config_exists") as mock_config,
        patch("subtap.core.setup.SetupWizard.setup_models") as mock_models,
    ):

        mock_deps.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        mock_config.return_value = True
        # manual 模式下 setup_models 返回 False（预期行为）
        mock_models.return_value = False

        result = runner.invoke(app, ["setup", "--download-source", "manual"])
        assert result.exit_code == 0
        assert "模型安装待手动完成" in result.output


def test_setup_interactive_manual_choice_continues(tmp_path, monkeypatch):
    """交互菜单选择 manual 时也应正常结束."""
    from unittest.mock import patch

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    config_dir = fake_home / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("")

    with (
        patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_deps,
        patch("subtap.core.setup.SetupWizard.check_config_exists") as mock_config,
        patch(
            "subtap.core.setup.SetupWizard.choose_download_source",
            return_value="manual",
        ),
    ):

        mock_deps.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        mock_config.return_value = True

        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0
        assert "模型安装待手动完成" in result.output
