"""Tests for CLI commands."""

from __future__ import annotations

import json
import re
from concurrent.futures import Future
from types import SimpleNamespace

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text for reliable string matching."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_dashboard_exits_when_pipeline_future_finishes():
    """后台 pipeline 完成时，TUI dashboard 必须主动退出。"""
    from subtap.cli import _exit_dashboard_when_pipeline_done

    future = Future()

    class FakeDashboard:
        def __init__(self):
            self.call_from_thread_called = False
            self.exited = False

        def call_from_thread(self, callback):
            self.call_from_thread_called = True
            callback()

        def exit(self):
            self.exited = True

    dashboard = FakeDashboard()
    _exit_dashboard_when_pipeline_done(future, dashboard)
    future.set_result({"timings": {}})

    assert dashboard.call_from_thread_called is True
    assert dashboard.exited is True


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
    assert "subtap" in _strip_ansi(result.output)
    assert "0.1.0" in _strip_ansi(result.output)


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
    assert (
        "ffmpeg" in _strip_ansi(result.output).lower()
        or "python" in _strip_ansi(result.output).lower()
    )


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
    assert (
        "工作区" in _strip_ansi(result.output)
        or "workspace" in _strip_ansi(result.output).lower()
    )


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
    payload = json.loads(_strip_ansi(result.output))
    assert payload["ok"] is True
    assert payload["config"]["valid"] is True
    assert payload["checks"][0]["name"] == "ffmpeg"
    assert payload["models"][0]["name"] == "asr_0.6b"


def test_run_has_no_git_check_flag():
    """subtap run should accept --no-git-check flag."""
    # Just verify the flag is accepted (will fail on missing input file, that's ok)
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "git-check" in _strip_ansi(result.output)


def test_run_has_no_cleanroom_flag():
    """subtap run should accept --no-cleanroom flag."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "cleanroom" in _strip_ansi(result.output)


def test_run_has_no_align_flag():
    """subtap run should expose no-align draft mode."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    clean = _strip_ansi(result.output)
    assert "no-align" in clean
    assert "draft" in clean
    assert "final.srt" in clean


def test_run_help_describes_output_contract_not_single_format():
    """run help should not imply --format controls the only generated file."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    clean = _strip_ansi(result.output)
    assert "输出清单标记" in clean
    assert "精对齐默认生成 final.srt/final.vtt/final.json/final.tsv" in clean


def test_setup_has_remote_api_options():
    """subtap setup should expose remote API model discovery options."""
    import re

    result = runner.invoke(app, ["setup", "--help"])
    assert result.exit_code == 0
    clean = re.sub(r"\x1b\[[0-9;]*m", "", _strip_ansi(result.output))
    assert "remote-api" in clean
    assert "remote-base-url" in clean
    assert "remote-api-key-env" in clean


def test_quality_command_exists():
    """subtap quality command should exist."""
    import re

    result = runner.invoke(app, ["quality", "--help"])
    assert result.exit_code == 0
    clean = re.sub(r"\x1b\[[0-9;]*m", "", _strip_ansi(result.output))
    assert "aligned.jsonl" in clean
    assert "fix" in clean
    assert "report-only" in clean


def test_run_has_mode_flag():
    """subtap run should accept --mode flag."""
    import re

    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    clean = re.sub(r"\x1b\[[0-9;]*m", "", _strip_ansi(result.output))
    assert "mode" in clean


def test_run_json_flag_is_available():
    """subtap run should accept --json for machine-readable output."""
    result = runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0
    assert "--json" in _strip_ansi(result.output)


def test_batch_transcribe_command_exists():
    """subtap batch-transcribe should expose batch input and JSON output."""
    result = runner.invoke(app, ["batch-transcribe", "--help"])

    assert result.exit_code == 0
    assert "--files" in _strip_ansi(result.output)
    assert "--json" in _strip_ansi(result.output)


def test_batch_transcribe_runs_each_file(tmp_path, monkeypatch):
    """batch-transcribe should run the pipeline once per input file."""
    calls = []

    class FakeRunner:
        def run_pipeline(
            self, pipeline, input_path, output_dir, fmt="srt", enhance="local", align_enabled=True
        ):
            calls.append((pipeline.work_dir, input_path, output_dir, fmt))
            return {"output_dir": str(output_dir), "format": fmt, "timings": {"asr": 1.0}}

    class FakePipeline:
        def __init__(self, _config, work_dir):
            self.work_dir = work_dir

            class Workspace:
                def ensure_dirs(self):
                    return None

            self.workspace = Workspace()

    monkeypatch.setattr("subtap.ui.tui.PlainRunner", FakeRunner)
    monkeypatch.setattr("subtap.core.pipeline.Pipeline", FakePipeline)

    def _mock_config(_):
        c = SimpleNamespace()
        c.output = SimpleNamespace()
        c.output.timestamp = True
        c.output.subtitle_punctuation = False
        c.output.subtitle_language = "zh"
        c.output.max_chars = 25
        c.output.min_chars = 10
        c.output.subtitle_stem = "test"
        c.asr = SimpleNamespace()
        c.asr.model = "asr_0.6b"
        c.asr.quantization = "q8"
        c.align = SimpleNamespace()
        c.align.model = "aligner"
        c.align.quantization = "q8"
        return c

    monkeypatch.setattr("subtap.schemas.config.load_config", _mock_config)
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
    # JSON Lines output: last line is the "complete" event
    lines = _strip_ansi(result.output).strip().split("\n")
    data = json.loads(lines[-1])
    assert data["type"] == "complete"
    assert data["ok"] is True
    assert data["succeeded"] == 2
    assert len(calls) == 2
    assert calls[0][0] == tmp_path / "out" / "one_wav" / "work"
    assert calls[0][2] == tmp_path / "out" / "one_wav"
    assert calls[1][2] == tmp_path / "out" / "two_wav"


def test_run_no_align_passes_align_disabled_to_runner(tmp_path, monkeypatch):
    """--no-align should disable align stage in runner."""
    calls = []

    class FakePipeline:
        def __init__(self, _config, work_dir):
            class Workspace:
                root = work_dir
                asr_jsonl = work_dir / "asr" / "asr.jsonl"
                aligned_jsonl = work_dir / "aligned.jsonl"

                def ensure_dirs(self):
                    self.root.mkdir(parents=True, exist_ok=True)

            self.workspace = Workspace()

        def run_stage(self, stage, **kwargs):
            calls.append(stage)
            if stage == "prepare":
                return {"media_info": {"duration": 1.0, "sample_rate": 16000}}
            if stage == "chunk":
                return {"chunk_count": 1}
            if stage == "asr":
                self.workspace.asr_jsonl.parent.mkdir(parents=True, exist_ok=True)
                self.workspace.asr_jsonl.write_text(
                    '{"chunk_id":0,"segment_id":0,"start_sec":0.0,'
                    '"end_sec":1.0,"text":"hello","confidence":null}\n',
                    encoding="utf-8",
                )
                return {"segment_count": 1}
            if stage == "clean":
                return {"segment_count": 1}
            if stage == "hotword":
                return {"replaced": 0, "total": 1}
            if stage == "segment":
                return {"sentence_count": 1}
            if stage == "align":
                raise AssertionError("--no-align must not run align")
            raise AssertionError(stage)

    config = SimpleNamespace(output=SimpleNamespace(timestamp=True))
    monkeypatch.setattr("subtap.core.pipeline.Pipeline", FakePipeline)
    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)

    input_path = tmp_path / "input.wav"
    output_dir = tmp_path / "out"
    input_path.write_bytes(b"data")

    result = runner.invoke(
        app,
        [
            "run",
            str(input_path),
            "--no-tui",
            "--no-git-check",
            "--no-cleanroom",
            "--no-align",
            "--output-dir",
            str(output_dir),
            "--work-dir",
            str(tmp_path / "work"),
        ],
    )

    assert result.exit_code == 0
    assert "align" not in calls
    assert (output_dir / "draft.srt").exists()
    assert (output_dir / "draft.json").exists()
    assert not (output_dir / "final.srt").exists()
    work_dir = tmp_path / "work"
    assert "未精对齐" in (work_dir / "report.md").read_text(encoding="utf-8")
    metrics = json.loads((work_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["alignment_enabled"] is False
    assert metrics["align_runtime_sec"] == 0
    assert metrics["external_audio_sent"] is False
    run_log = work_dir / "run.log.jsonl"
    assert run_log.exists()
    assert '"event_type": "stage_start"' in run_log.read_text(encoding="utf-8")


def test_run_enhance_off_passes_clean_off_to_pipeline(tmp_path, monkeypatch):
    """--enhance off 应传到 clean 阶段，避免触发 LLM backend。"""
    clean_kwargs = []

    class FakePipeline:
        def __init__(self, _config, work_dir):
            self.config = _config

            class Workspace:
                root = work_dir
                asr_jsonl = work_dir / "asr" / "asr.jsonl"
                aligned_jsonl = work_dir / "aligned.jsonl"

                def ensure_dirs(self):
                    self.root.mkdir(parents=True, exist_ok=True)

            self.workspace = Workspace()

        def run_stage(self, stage, **kwargs):
            if stage == "prepare":
                return {"media_info": {"duration": 1.0, "sample_rate": 16000}}
            if stage == "chunk":
                return {"chunk_count": 1}
            if stage == "asr":
                self.workspace.asr_jsonl.parent.mkdir(parents=True, exist_ok=True)
                self.workspace.asr_jsonl.write_text(
                    '{"chunk_id":0,"segment_id":0,"start_sec":0.0,'
                    '"end_sec":1.0,"text":"hello","confidence":null}\n',
                    encoding="utf-8",
                )
                return {"segment_count": 1}
            if stage == "clean":
                clean_kwargs.append(kwargs)
                return {"segment_count": 1}
            if stage == "hotword":
                return {"replaced": 0, "total": 1}
            if stage == "segment":
                return {"sentence_count": 1}
            if stage == "align":
                raise AssertionError("--no-align must not run align")
            raise AssertionError(stage)

    config = SimpleNamespace(output=SimpleNamespace(timestamp=True))
    monkeypatch.setattr("subtap.core.pipeline.Pipeline", FakePipeline)
    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)

    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"data")

    result = runner.invoke(
        app,
        [
            "run",
            str(input_path),
            "--enhance",
            "off",
            "--no-tui",
            "--no-git-check",
            "--no-cleanroom",
            "--no-align",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 0
    assert clean_kwargs == [{"llm_backend": "off"}]


def test_run_tui_starts_observer_child_process(tmp_path, monkeypatch):
    """默认 TUI 只做观察者，推理必须放到 --observer-child 子进程。"""

    child_calls = []

    def fake_observer_parent(command, log_path):
        child_calls.append((command, log_path))

    monkeypatch.setattr("subtap.cli._run_observer_parent", fake_observer_parent)

    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"data")
    output_dir = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "run",
            str(input_path),
            "--no-git-check",
            "--no-cleanroom",
            "--no-align",
            "--output-dir",
            str(output_dir),
            "--work-dir",
            str(tmp_path / "work"),
        ],
    )

    assert result.exit_code == 0
    assert child_calls
    command, log_path = child_calls[0]
    assert "--observer-child" in command
    assert "--no-tui" in command
    assert "--no-align" in command
    assert log_path == tmp_path / "work" / "run.log.jsonl"
    assert "观察者进程" in result.output


def test_observe_command_prints_event_log_status(tmp_path):
    """observe 命令只读 run.log.jsonl 输出当前状态。"""
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "asr_draft_ready",
                        "timestamp": 1,
                        "data": {
                            "stage": "asr",
                            "chunk_id": 0,
                            "progress": 40,
                            "model": "asr_0.6b-q8",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "event_type": "alignment_ready",
                        "timestamp": 2,
                        "data": {"stage": "align", "subtitle_id": 1, "progress": 80},
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["observe", str(log_path)])

    assert result.exit_code == 0
    clean = _strip_ansi(result.output)
    assert "当前阶段：align" in clean
    assert "进度：80%" in clean
    assert "已对齐：1" in clean


def test_observer_parent_runs_textual_dashboard(tmp_path, monkeypatch):
    """父进程启动子进程后，应进入 Textual 观察者 Dashboard。"""
    from subtap.cli import _run_observer_parent

    calls = []

    class FakeProcess:
        returncode = 0

        def poll(self):
            return 0

    class FakePopen:
        def __new__(cls, command, stdout, stderr):
            calls.append(("popen", command, bool(stdout), bool(stderr)))
            return FakeProcess()

    class FakeDashboard:
        def __init__(self, log_path, process):
            calls.append(("dashboard", log_path, process))

        def run(self):
            calls.append(("run",))

    monkeypatch.setattr("subtap.cli.subprocess.Popen", FakePopen)
    monkeypatch.setattr("subtap.ui.observer.ObserverDashboard", FakeDashboard)

    log_path = tmp_path / "run.log.jsonl"
    _run_observer_parent(["subtap", "run"], log_path)

    assert calls[0][0] == "popen"
    assert calls[1][0] == "dashboard"
    assert calls[1][1] == log_path
    assert calls[2] == ("run",)


def test_run_mode_fast():
    """subtap run should accept --mode fast."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "fast" in _strip_ansi(result.output)


def test_run_mode_quality():
    """subtap run should accept --mode quality."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "quality" in _strip_ansi(result.output)


def test_analyze_command_exists():
    """subtap analyze command should exist."""
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "SRT" in _strip_ansi(result.output) or "srt" in _strip_ansi(result.output)


def test_setup_command_exists():
    """Test that setup command exists."""
    result = runner.invoke(app, ["setup", "--help"])
    assert result.exit_code == 0
    assert "初始化向导" in _strip_ansi(result.output)


def test_setup_system_check():
    """Test setup system check step."""
    from unittest.mock import patch

    with patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_check:
        mock_check.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        result = runner.invoke(app, ["setup", "--skip-models"])
        assert "系统检查" in _strip_ansi(result.output)


def test_setup_system_check_failure():
    """Test setup system check when deps are missing."""
    from unittest.mock import patch

    with patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_check:
        mock_check.return_value = {"ffmpeg": False, "ffprobe": True, "python": True}
        result = runner.invoke(app, ["setup", "--skip-models"])
        assert result.exit_code == 1
        assert "系统检查未通过" in _strip_ansi(result.output)


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
        assert "模型安装（已跳过）" in _strip_ansi(result.output)


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
        assert "配置状态" in _strip_ansi(result.output)
        assert "模型状态" in _strip_ansi(result.output)
        assert "asr" in _strip_ansi(result.output)
        assert "aligner" in _strip_ansi(result.output)


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
        assert "系统检查" in _strip_ansi(result.output)
        assert "初始化配置" in _strip_ansi(result.output)
        assert "初始化完成" in _strip_ansi(result.output)
        # Verify setup_models was called
        mock_models.assert_called_once()


def test_demo_command_exists():
    """Test demo command exists with expected options."""
    result = runner.invoke(app, ["demo", "--help"])
    assert result.exit_code == 0
    assert "演示" in _strip_ansi(result.output)
    assert "--output-dir" in _strip_ansi(result.output)
    assert "--skip-tui" in _strip_ansi(result.output)


def test_setup_help_has_download_source_option():
    """Test setup --help shows --download-source option."""
    result = runner.invoke(app, ["setup", "--help"])

    assert result.exit_code == 0
    assert "--download-source" in _strip_ansi(result.output)
    assert "hf-mirror" in _strip_ansi(result.output)


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
    assert "部分检查未通过" in _strip_ansi(result.output)
    assert "缺失" in _strip_ansi(result.output)


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
        assert "模型安装失败" in _strip_ansi(result.output)


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
        assert "模型安装待手动完成" in _strip_ansi(result.output)


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
        assert "模型安装待手动完成" in _strip_ansi(result.output)
