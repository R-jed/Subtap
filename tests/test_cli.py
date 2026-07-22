"""Tests for CLI commands."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

from typer.testing import CliRunner

from subtap.cli import app, check_first_run_wizard

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text for reliable string matching."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_auto_json_detects_real_pipe(monkeypatch):
    """Machine-readable output activates for an OS pipe, not test capture."""
    import os
    import sys

    from subtap.cli._utils import auto_json

    read_fd, write_fd = os.pipe()
    stream = os.fdopen(write_fd, "w")
    try:
        monkeypatch.setattr(sys, "stdout", stream)
        assert auto_json(False) is True
    finally:
        stream.close()
        os.close(read_fd)


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
            self.run_log = root / "run.log"

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
    assert (subtap_dir / "glossaries" / "default.yaml").exists()
    assert not (subtap_dir / "glossary").exists()
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
    assert payload["models"][0] == {
        "name": "asr_0.6b",
        "required": True,
        "installed": True,
        "path": str(tmp_path / "models" / "asr"),
        "missing_files": [],
    }


def test_doctor_json_rejects_invalid_model_status_types(tmp_path, monkeypatch):
    """doctor 不应把错误的模型状态类型悄悄转换成可用数据。"""
    fake_home = tmp_path / "fakehome"
    config_dir = fake_home / ".subtap"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text("audio:\n  sample_rate: 16000\n")
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(
        "subtap.core.models.ModelRegistry.status",
        lambda _self: [
            SimpleNamespace(
                name=object(),
                installed=True,
                path=tmp_path / "models" / "asr",
                missing_files=[],
            )
        ],
    )

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code != 0


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


def test_run_help_describes_output_contract_not_single_format():
    """run help should not imply --format controls the only generated file."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    clean = _strip_ansi(result.output)
    assert "输出清单标记" in clean
    assert "final.srt" in clean


def test_setup_has_remote_api_options():
    """subtap setup should expose remote API model discovery options."""
    import re

    result = runner.invoke(app, ["setup", "--help"])
    assert result.exit_code == 0
    clean = re.sub(r"\x1b\[[0-9;]*m", "", _strip_ansi(result.output))
    assert "remote-api" in clean
    assert "remote-base-url" in clean
    assert "remote-api-key-env" in clean


def test_run_has_mode_flag():
    """subtap run should accept --mode flag."""
    import re

    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    clean = re.sub(r"\x1b\[[0-9;]*m", "", _strip_ansi(result.output))
    assert "mode" in clean


def test_run_exposes_only_maximum_subtitle_character_limit():
    result = runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0
    clean = _strip_ansi(result.output)
    assert "--max-chars" in clean
    assert "--min-chars" not in clean


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


def test_batch_transcribe_runs_each_file(
    tmp_path, monkeypatch, skip_runtime_model_validation
):
    """batch-transcribe should run the pipeline once per input file."""
    calls = []

    class FakeRunner:
        def run_pipeline(
            self,
            pipeline,
            input_path,
            output_dir,
            **kwargs,
        ):
            calls.append((pipeline.work_dir, input_path, output_dir, kwargs))
            return {
                "output_dir": str(output_dir),
                "format": kwargs.get("fmt", "srt"),
                "timings": {"asr": 1.0},
            }

    class FakePipeline:
        def __init__(self, _config, work_dir):
            self.work_dir = work_dir

            class Workspace:
                run_log = work_dir / "run.log"

                def ensure_dirs(self):
                    return None

            self.workspace = Workspace()

    monkeypatch.setattr("subtap.ui.tui.RichRunner", FakeRunner)
    monkeypatch.setattr("subtap.core.pipeline.Pipeline", FakePipeline)

    def _mock_config(_):
        c = SimpleNamespace()
        c.output = SimpleNamespace()
        c.output.timestamp = True
        c.output.subtitle_punctuation = False
        c.output.subtitle_language = "zh"
        c.output.max_chars = 25
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
            "--no-confirm",
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


def test_batch_transcribe_passes_translate_and_bilingual(
    tmp_path, monkeypatch, skip_runtime_model_validation
):
    """batch-transcribe 应传递 translate_to、bilingual 和 fmt 参数。"""
    captured_kwargs = []

    class FakeRunner:
        def run_pipeline(self, pipeline, input_path, output_dir, **kwargs):
            captured_kwargs.append(kwargs)
            return {
                "output_dir": str(output_dir),
                "format": kwargs.get("fmt", "srt"),
                "timings": {"asr": 1.0},
            }

    class FakePipeline:
        def __init__(self, _config, work_dir):
            self.work_dir = work_dir

            class Workspace:
                run_log = work_dir / "run.log"

                def ensure_dirs(self):
                    return None

            self.workspace = Workspace()

    monkeypatch.setattr("subtap.ui.tui.RichRunner", FakeRunner)
    monkeypatch.setattr("subtap.core.pipeline.Pipeline", FakePipeline)

    def _mock_config(_):
        c = SimpleNamespace()
        c.output = SimpleNamespace()
        c.output.timestamp = True
        c.output.subtitle_punctuation = False
        c.output.subtitle_language = "zh"
        c.output.max_chars = 25
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
    one.write_bytes(b"1")

    result = runner.invoke(
        app,
        [
            "batch-transcribe",
            "--files",
            str(one),
            "--output-dir",
            str(tmp_path / "out"),
            "--json",
            "--no-confirm",
            "--translate-to",
            "en",
            "--bilingual",
            "source-first",
        ],
    )

    assert result.exit_code == 0
    assert len(captured_kwargs) == 1
    kw = captured_kwargs[0]
    assert kw["fmt"] == "srt"
    assert kw["translate_to"] == "en"
    assert kw["bilingual"] == "source-first"


def test_batch_transcribe_bilingual_defaults_to_off(
    tmp_path, monkeypatch, skip_runtime_model_validation
):
    """batch-transcribe bilingual 未指定时应默认 off。"""
    captured_kwargs = []

    class FakeRunner:
        def run_pipeline(self, pipeline, input_path, output_dir, **kwargs):
            captured_kwargs.append(kwargs)
            return {
                "output_dir": str(output_dir),
                "format": kwargs.get("fmt", "srt"),
                "timings": {"asr": 1.0},
            }

    class FakePipeline:
        def __init__(self, _config, work_dir):
            self.work_dir = work_dir

            class Workspace:
                run_log = work_dir / "run.log"

                def ensure_dirs(self):
                    return None

            self.workspace = Workspace()

    monkeypatch.setattr("subtap.ui.tui.RichRunner", FakeRunner)
    monkeypatch.setattr("subtap.core.pipeline.Pipeline", FakePipeline)

    def _mock_config(_):
        c = SimpleNamespace()
        c.output = SimpleNamespace()
        c.output.timestamp = True
        c.output.subtitle_punctuation = False
        c.output.subtitle_language = "zh"
        c.output.max_chars = 25
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
    one.write_bytes(b"1")

    result = runner.invoke(
        app,
        [
            "batch-transcribe",
            "--files",
            str(one),
            "--output-dir",
            str(tmp_path / "out"),
            "--json",
            "--no-confirm",
        ],
    )

    assert result.exit_code == 0
    assert len(captured_kwargs) == 1
    kw = captured_kwargs[0]
    assert kw["fmt"] == "srt"
    assert kw["translate_to"] is None
    assert kw["bilingual"] == "off"


def test_run_full_pipeline_with_align(
    tmp_path, monkeypatch, skip_runtime_model_validation
):
    """run should always execute align stage."""
    calls = []

    class FakePipeline:
        def __init__(self, _config, work_dir):
            self.config = _config

            class Workspace:
                root = work_dir
                asr_jsonl = work_dir / "asr" / "asr.jsonl"
                aligned_jsonl = work_dir / "aligned.jsonl"
                run_log = work_dir / "run.log"

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
            if stage == "learn":
                return {"learned": 0}
            if stage == "segment":
                return {"sentence_count": 1}
            if stage == "script_match":
                return {"skipped": True}
            if stage == "align":
                self.workspace.aligned_jsonl.parent.mkdir(parents=True, exist_ok=True)
                self.workspace.aligned_jsonl.write_text(
                    '{"sentence_id":0,"start_sec":0.0,"end_sec":1.0,'
                    '"text":"hello","words":[]}\n',
                    encoding="utf-8",
                )
                return {"aligned_count": 1}
            if stage == "translate":
                return {"translated_count": 0}
            if stage == "export":
                return {"exported_count": 1}
            raise AssertionError(stage)

        def cleanup(self):
            """模拟 cleanup 调用。"""
            return {"cleaned_count": 0, "cleaned_files": []}

    config = SimpleNamespace(
        mode="online",
        asr=SimpleNamespace(model="asr_0.6b"),
        clean=SimpleNamespace(glossary_path=None),
        output=SimpleNamespace(
            timestamp=True,
            generate_metrics=False,
            subtitle_punctuation=False,
            subtitle_language="zh",
            max_chars=25,
            subtitle_formats=["srt"],
            subtitle_stem="output",
        ),
        metrics=SimpleNamespace(output_path="metrics.json"),
        workspace=SimpleNamespace(root="./work"),
    )
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
            "--no-git-check",
            "--no-cleanroom",
            "--output-dir",
            str(output_dir),
            "--work-dir",
            str(tmp_path / "work"),
        ],
    )

    assert result.exit_code == 0
    assert "align" in calls
    # 输出文件名由输入文件名决定（subtitle_stem 默认用输入文件名）
    srt_files = list(output_dir.glob("*.srt"))
    assert len(srt_files) > 0, f"No .srt files in {output_dir}"
    work_dir = tmp_path / "work"
    run_log = work_dir / "run.log.jsonl"
    assert run_log.exists()
    assert '"event_type": "stage_start"' in run_log.read_text(encoding="utf-8")


def test_run_enhance_local_passes_clean_local_to_pipeline(
    tmp_path, monkeypatch, skip_runtime_model_validation
):
    """--enhance local 应传到 clean 阶段，避免触发 LLM backend。"""
    clean_kwargs = []

    class FakePipeline:
        def __init__(self, _config, work_dir):
            self.config = _config

            class Workspace:
                root = work_dir
                asr_jsonl = work_dir / "asr" / "asr.jsonl"
                aligned_jsonl = work_dir / "aligned.jsonl"
                run_log = work_dir / "run.log"

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
            if stage == "learn":
                return {"learned": 0}
            if stage == "segment":
                return {"sentence_count": 1}
            if stage == "script_match":
                return {"skipped": True}
            if stage == "align":
                self.workspace.aligned_jsonl.parent.mkdir(parents=True, exist_ok=True)
                self.workspace.aligned_jsonl.write_text(
                    '{"sentence_id":0,"start_sec":0.0,"end_sec":1.0,'
                    '"text":"hello","words":[]}\n',
                    encoding="utf-8",
                )
                return {"aligned_count": 1}
            if stage == "translate":
                return {"translated_count": 0}
            if stage == "export":
                return {"exported_count": 1}
            raise AssertionError(stage)

        def cleanup(self):
            """模拟 cleanup 调用。"""
            return {"cleaned_count": 0, "cleaned_files": []}

    config = SimpleNamespace(
        mode="online",
        asr=SimpleNamespace(model="asr_0.6b"),
        clean=SimpleNamespace(glossary_path=None),
        output=SimpleNamespace(
            timestamp=True,
            generate_metrics=False,
            subtitle_punctuation=False,
            subtitle_language="zh",
            max_chars=25,
            subtitle_formats=["srt"],
            subtitle_stem="output",
        ),
        metrics=SimpleNamespace(output_path="metrics.json"),
        workspace=SimpleNamespace(root="./work"),
    )
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
            "local",
            "--no-git-check",
            "--no-cleanroom",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 0
    assert clean_kwargs[0]["enhance_mode"] == "local"


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


def test_tui_run_rejects_zero_exit_without_subtitle(
    tmp_path, monkeypatch, skip_runtime_model_validation
):
    """子进程返回成功但没有字幕文件时，CLI 不能报告成功。"""
    import subprocess

    config = SimpleNamespace(
        mode="online",
        translate_to="",
        asr=SimpleNamespace(backend="mlx-qwen-asr", model="asr_0.6b"),
        clean=SimpleNamespace(glossary_path=None),
        output=SimpleNamespace(
            timestamp=True,
            subtitle_punctuation=False,
            subtitle_language="zh",
            subtitle_stem="output",
        ),
        workspace=SimpleNamespace(root=str(tmp_path / "work")),
    )
    process = SimpleNamespace(returncode=0, pid=42, poll=lambda: 0)
    dashboard = SimpleNamespace(run=lambda: "quit")
    popen_kwargs = {}

    def start_child(*_args, **kwargs):
        popen_kwargs.update(kwargs)
        return process

    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _path: config)
    monkeypatch.setattr("subtap.cli.pipeline_cli.subprocess.Popen", start_child)
    monkeypatch.setattr(
        "subtap.ui.observer._make_observer_dashboard",
        lambda *_args, **_kwargs: dashboard,
    )
    input_path = tmp_path / "voice.wav"
    input_path.write_bytes(b"audio")

    result = runner.invoke(
        app,
        [
            "run",
            str(input_path),
            "--tui",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
        ],
    )

    assert result.exit_code == 1
    assert "未找到字幕文件" in _strip_ansi(result.output)
    assert popen_kwargs["start_new_session"] is True
    assert popen_kwargs["stderr"] is subprocess.STDOUT
    assert popen_kwargs["stdout"].name == str(tmp_path / "work" / "observer-child.log")


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
    from unittest.mock import patch
    from pathlib import Path

    # 隔离 Path.home()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # 创建模拟配置文件
    config_dir = tmp_path / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("")

    with patch("subtap.core.models.ModelRegistry.status") as mock_status:
        mock_status.return_value = [
            SimpleNamespace(
                name="aligner",
                installed=True,
                path=tmp_path / "models" / "aligner",
                missing_files=[],
            ),
            SimpleNamespace(
                name="asr",
                installed=True,
                path=tmp_path / "models" / "asr",
                missing_files=[],
            ),
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
    assert "--asr-model" in _strip_ansi(result.output)
    assert "hf-mirror" in _strip_ansi(result.output)


def test_setup_persists_explicit_asr_selection(tmp_path, monkeypatch):
    from subtap.schemas.config import load_config

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "subtap.core.setup.SetupWizard.check_system_deps",
        lambda self: {"ffmpeg": True, "ffprobe": True, "python": True},
    )
    monkeypatch.setattr(
        "subtap.core.setup.SetupWizard.check_config_exists", lambda self: True
    )

    result = runner.invoke(app, ["setup", "--skip-models", "--asr-model", "asr_1.7b"])

    assert result.exit_code == 0
    assert load_config(tmp_path / ".subtap" / "config.yaml").asr.model == "asr_1.7b"


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
    from unittest.mock import patch
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    subtap_dir = tmp_path / ".subtap"
    subtap_dir.mkdir()
    (subtap_dir / "config.yaml").write_text(
        "models:\n  root: models\n", encoding="utf-8"
    )

    # 模拟 registry.status() 返回缺失模型
    mock_asr = SimpleNamespace(
        name="asr_0.6b",
        installed=False,
        path=tmp_path / "models" / "asr_0.6b",
        missing_files=["config.json", "model.safetensors"],
    )
    mock_aligner = SimpleNamespace(
        name="aligner",
        installed=True,
        path=tmp_path / "models" / "aligner",
        missing_files=[],
    )
    missing_status = [mock_asr, mock_aligner]

    with patch("subtap.core.models.ModelRegistry") as MockRegistry:
        MockRegistry.return_value.status.return_value = missing_status
        result = runner.invoke(app, ["doctor", "--release"])

    assert result.exit_code == 1
    assert "部分检查未通过" in _strip_ansi(result.output)
    assert "缺失" in _strip_ansi(result.output)


def test_doctor_default_reports_missing_models_without_failing(tmp_path, monkeypatch):
    """doctor 默认用于安装后诊断，缺模型时应提示但不阻断。"""
    from unittest.mock import patch
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    subtap_dir = tmp_path / ".subtap"
    subtap_dir.mkdir()
    (subtap_dir / "config.yaml").write_text(
        "models:\n  root: models\n", encoding="utf-8"
    )

    mock_asr = SimpleNamespace(
        name="asr_0.6b",
        installed=False,
        path=tmp_path / "models" / "asr_0.6b",
        missing_files=["config.json"],
    )
    missing_status = [mock_asr]

    with patch("subtap.core.models.ModelRegistry") as MockRegistry:
        MockRegistry.return_value.status.return_value = missing_status
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "缺失" in _strip_ansi(result.output)


def test_python_module_entrypoint_outputs_help():
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parent.parent / "src")
    env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-m", "subtap.cli", "--help"],
        capture_output=True,
        text=True,
        env=env,
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


# ── 首次运行向导测试 ──────────────────────────────────────────


def test_first_run_wizard_prompts_when_llm_proofread_not_set(monkeypatch):
    """首次运行向导应在 llm_proofread 未设置时提示用户"""
    from subtap.schemas.config import RemoteAPIConfig, SubtapConfig

    # 模拟 API 配置存在但 llm_proofread 未设置
    config = SubtapConfig(
        remote_api=RemoteAPIConfig(base_url="http://test.com", api_key_env="TEST_KEY")
    )
    config.llm_proofread = None

    # 模拟环境变量存在
    monkeypatch.setenv("TEST_KEY", "test-value")
    # 模拟用户输入 "y"
    monkeypatch.setattr("builtins.input", lambda _: "y")

    result = check_first_run_wizard(config)
    assert result is True
    assert config.llm_proofread is True
    assert config.llm_hotword is True


def test_first_run_wizard_prompts_user_declines(monkeypatch):
    """首次运行向导应处理用户拒绝开启 AI 校对"""
    from subtap.schemas.config import RemoteAPIConfig, SubtapConfig

    config = SubtapConfig(
        remote_api=RemoteAPIConfig(base_url="http://test.com", api_key_env="TEST_KEY")
    )
    config.llm_proofread = None

    # 模拟环境变量存在
    monkeypatch.setenv("TEST_KEY", "test-value")
    # 模拟用户输入 "n"
    monkeypatch.setattr("builtins.input", lambda _: "n")

    result = check_first_run_wizard(config)
    assert result is True
    assert config.llm_proofread is False
    assert config.llm_hotword is False


def test_first_run_wizard_accepts_empty_input(monkeypatch):
    """首次运行向导应接受空输入（直接回车）"""
    from subtap.schemas.config import RemoteAPIConfig, SubtapConfig

    config = SubtapConfig(
        remote_api=RemoteAPIConfig(base_url="http://test.com", api_key_env="TEST_KEY")
    )
    config.llm_proofread = None

    # 模拟环境变量存在
    monkeypatch.setenv("TEST_KEY", "test-value")
    # 模拟用户直接回车
    monkeypatch.setattr("builtins.input", lambda _: "")

    result = check_first_run_wizard(config)
    assert result is True
    assert config.llm_proofread is True
    assert config.llm_hotword is True


def test_first_run_wizard_accepts_yes_input(monkeypatch):
    """首次运行向导应接受 'yes' 输入"""
    from subtap.schemas.config import RemoteAPIConfig, SubtapConfig

    config = SubtapConfig(
        remote_api=RemoteAPIConfig(base_url="http://test.com", api_key_env="TEST_KEY")
    )
    config.llm_proofread = None

    monkeypatch.setenv("TEST_KEY", "test-value")
    monkeypatch.setattr("builtins.input", lambda _: "yes")

    result = check_first_run_wizard(config)
    assert result is True
    assert config.llm_proofread is True
    assert config.llm_hotword is True


def test_first_run_wizard_rejects_no_input(monkeypatch):
    """首次运行向导应拒绝 'no' 输入"""
    from subtap.schemas.config import RemoteAPIConfig, SubtapConfig

    config = SubtapConfig(
        remote_api=RemoteAPIConfig(base_url="http://test.com", api_key_env="TEST_KEY")
    )
    config.llm_proofread = None

    # 模拟环境变量存在
    monkeypatch.setenv("TEST_KEY", "test-value")
    # 模拟用户输入 "no"
    monkeypatch.setattr("builtins.input", lambda _: "no")

    result = check_first_run_wizard(config)
    assert result is True
    assert config.llm_proofread is False
    assert config.llm_hotword is False


def test_first_run_wizard_skips_when_llm_proofread_set():
    """首次运行向导应在 llm_proofread 已设置时跳过"""
    from subtap.schemas.config import SubtapConfig

    config = SubtapConfig()
    config.llm_proofread = True

    result = check_first_run_wizard(config)
    assert result is False  # 未触发向导


def test_first_run_wizard_skips_when_no_api_config():
    """首次运行向导应在无 API 配置时跳过"""
    from subtap.schemas.config import SubtapConfig

    config = SubtapConfig()
    config.llm_proofread = None

    result = check_first_run_wizard(config)
    assert result is False  # 未触发向导


def test_first_run_wizard_skips_when_env_var_not_set(monkeypatch):
    """首次运行向导应在环境变量未设置时跳过"""
    from subtap.schemas.config import RemoteAPIConfig, SubtapConfig

    config = SubtapConfig(
        remote_api=RemoteAPIConfig(base_url="http://test.com", api_key_env="TEST_KEY")
    )
    config.llm_proofread = None

    # 确保环境变量不存在
    monkeypatch.delenv("TEST_KEY", raising=False)

    result = check_first_run_wizard(config)
    assert result is False  # 未触发向导


# ── CLI 参数传递测试 ──────────────────────────────────────────


def test_apply_cli_overrides_sets_values():
    """_apply_cli_overrides 应设置 config 中的 llm_proofread 和 llm_hotword"""
    from subtap.cli.pipeline_cli import _apply_cli_overrides
    from subtap.schemas.config import SubtapConfig

    config = SubtapConfig()
    config.llm_proofread = None
    config.llm_hotword = None

    _apply_cli_overrides(config, llm_proofread=True, llm_hotword=False)

    assert config.llm_proofread is True
    assert config.llm_hotword is False


def test_apply_cli_overrides_preserves_when_none():
    """_apply_cli_overrides 不传参时应保留 config 原值"""
    from subtap.cli.pipeline_cli import _apply_cli_overrides
    from subtap.schemas.config import SubtapConfig

    config = SubtapConfig()
    config.llm_proofread = True
    config.llm_hotword = True

    _apply_cli_overrides(config)

    assert config.llm_proofread is True
    assert config.llm_hotword is True


# ── hotword edit 跨平台测试 ──────────────────────────────────────


def test_open_file_cross_platform_macos(monkeypatch):
    """macOS 应使用 open 命令（不含 -a Numbers）"""
    from unittest.mock import patch
    from pathlib import Path

    monkeypatch.setattr("subtap.cli.hotword_cli.platform.system", lambda: "Darwin")

    with patch("subtap.cli.hotword_cli.subprocess.run") as mock_run:
        from subtap.cli.hotword_cli import _open_file_cross_platform

        _open_file_cross_platform(Path("/tmp/test.txt"))

        mock_run.assert_called_once_with(["open", "/tmp/test.txt"], check=True)


def test_open_file_cross_platform_linux(monkeypatch):
    """Linux 应使用 xdg-open 命令"""
    from unittest.mock import patch
    from pathlib import Path

    monkeypatch.setattr("subtap.cli.hotword_cli.platform.system", lambda: "Linux")

    with patch("subtap.cli.hotword_cli.subprocess.run") as mock_run:
        from subtap.cli.hotword_cli import _open_file_cross_platform

        _open_file_cross_platform(Path("/tmp/test.txt"))

        mock_run.assert_called_once_with(["xdg-open", "/tmp/test.txt"], check=True)


def test_open_file_cross_platform_windows(monkeypatch):
    """Windows 应使用 start 命令并启用 shell"""
    from unittest.mock import patch
    from pathlib import Path

    monkeypatch.setattr("subtap.cli.hotword_cli.platform.system", lambda: "Windows")

    with patch("subtap.cli.hotword_cli.subprocess.run") as mock_run:
        from subtap.cli.hotword_cli import _open_file_cross_platform

        _open_file_cross_platform(Path("C:\\test.txt"))

        mock_run.assert_called_once_with(
            ["start", "C:\\test.txt"], shell=True, check=True
        )


def test_open_file_cross_platform_unsupported_os(monkeypatch):
    """不支持的操作系统应抛出 RuntimeError"""
    from pathlib import Path

    monkeypatch.setattr("subtap.cli.hotword_cli.platform.system", lambda: "FreeBSD")

    from subtap.cli.hotword_cli import _open_file_cross_platform

    try:
        _open_file_cross_platform(Path("/tmp/test.txt"))
        assert False, "应抛出 RuntimeError"
    except RuntimeError as e:
        assert "FreeBSD" in str(e)


def test_handle_error_default_exit_code():
    """_handle_error 默认退出码应为 1，错误消息应输出到 stderr"""
    from typer import Exit
    from subtap.cli import _handle_error

    try:
        _handle_error("测试错误消息")
        assert False, "应抛出 Exit 异常"
    except Exit as e:
        assert e.exit_code == 1


def test_handle_error_custom_exit_code():
    """_handle_error 应支持自定义退出码"""
    from typer import Exit
    from subtap.cli import _handle_error

    try:
        _handle_error("自定义错误", exit_code=2)
        assert False, "应抛出 Exit 异常"
    except Exit as e:
        assert e.exit_code == 2


def test_handle_error_message_format():
    """_handle_error 输出的消息应包含 ✗ 前缀"""
    from unittest.mock import patch
    from subtap.cli import _handle_error

    with patch("subtap.cli.typer.echo") as mock_echo:
        try:
            _handle_error("文件不存在")
        except Exception:
            pass

        # 验证调用了 typer.echo
        mock_echo.assert_called_once()
        call_args = mock_echo.call_args
        # 检查消息内容
        assert "✗ 文件不存在" in call_args[0][0]
        # 检查 err=True
        assert call_args[1].get("err", False) is True


def test_cli_file_not_found_errors(tmp_path, monkeypatch):
    """CLI 命令对不存在的文件应输出错误并退出码 1"""
    # 测试 prepare 命令
    result = runner.invoke(app, ["prepare", str(tmp_path / "nonexistent.mp3")])
    assert result.exit_code == 1
    assert "文件未找到" in _strip_ansi(result.output)

    # 测试 transcribe 命令
    result = runner.invoke(app, ["transcribe", str(tmp_path / "nonexistent.wav")])
    assert result.exit_code == 1
    assert "文件未找到" in _strip_ansi(result.output)

    # 测试 export 命令
    result = runner.invoke(app, ["export", str(tmp_path / "nonexistent.jsonl")])
    assert result.exit_code == 1
    assert "文件未找到" in _strip_ansi(result.output)


def test_cli_run_parameter_validation(tmp_path):
    """run 命令参数验证应输出正确错误消息"""
    # 创建一个假文件以通过文件存在检查
    fake_file = tmp_path / "test.mp3"
    fake_file.touch()

    # 测试 --enhance 参数验证
    result = runner.invoke(app, ["run", str(fake_file), "--enhance", "invalid"])
    assert result.exit_code == 1
    assert "--enhance" in _strip_ansi(result.output)

    # 测试 --bilingual 参数验证
    result = runner.invoke(app, ["run", str(fake_file), "--bilingual", "invalid"])
    assert result.exit_code == 1
    assert "--bilingual" in _strip_ansi(result.output)

    result = runner.invoke(app, ["run", str(fake_file), "--mode", "invalid"])
    assert result.exit_code == 1
    assert "--mode" in _strip_ansi(result.output)


def test_cli_run_accepts_glossary_selection():
    result = runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0
    assert "--glossary" in _strip_ansi(result.output)


def test_cli_run_rejects_reset_and_explicit_hotwords(tmp_path):
    fake_file = tmp_path / "test.mp3"
    fake_file.touch()

    result = runner.invoke(
        app,
        ["run", str(fake_file), "--reset-hotwords", "--hotwords", "GR4"],
    )

    assert result.exit_code == 1
    assert "不能同时" in _strip_ansi(result.output)


def test_run_config_applies_selected_glossary(tmp_path):
    from subtap.cli.pipeline_cli import _apply_run_config
    from subtap.schemas.config import SubtapConfig
    from subtap.schemas.task_request import SubtitleTaskRequest

    glossary = tmp_path / "camera.yaml"
    config = SubtapConfig()

    _apply_run_config(
        config=config,
        request=SubtitleTaskRequest(
            input_path=tmp_path / "voice.wav",
            output_dir=tmp_path / "output",
            mode="quality",
            glossary_path=glossary,
        ),
        timestamp=None,
        punctuation=None,
        max_chars=None,
        script_mode="follow_script",
        hotwords=None,
        work_dir=tmp_path / "work",
    )

    assert config.clean.glossary_path == str(glossary)
    assert config.asr.model == "asr_1.7b"


def test_run_config_fast_mode_selects_06b_model(tmp_path):
    from subtap.cli.pipeline_cli import _apply_run_config
    from subtap.schemas.config import SubtapConfig
    from subtap.schemas.task_request import SubtitleTaskRequest

    config = SubtapConfig()
    config.asr.model = "asr_1.7b"

    _apply_run_config(
        config=config,
        request=SubtitleTaskRequest(
            input_path=tmp_path / "voice.wav",
            output_dir=tmp_path / "output",
            mode="fast",
        ),
        timestamp=None,
        punctuation=None,
        max_chars=None,
        script_mode="follow_script",
        hotwords=None,
        work_dir=tmp_path / "work",
    )

    assert config.asr.model == "asr_0.6b"


def test_run_config_without_mode_preserves_selected_model(tmp_path):
    from subtap.cli.pipeline_cli import _apply_run_config
    from subtap.schemas.config import SubtapConfig
    from subtap.schemas.task_request import SubtitleTaskRequest

    config = SubtapConfig()
    config.asr.model = "asr_1.7b"

    _apply_run_config(
        config=config,
        request=SubtitleTaskRequest(
            input_path=tmp_path / "voice.wav",
            output_dir=tmp_path / "output",
        ),
        timestamp=None,
        punctuation=None,
        max_chars=None,
        script_mode="follow_script",
        hotwords=None,
        work_dir=tmp_path / "work",
    )

    assert config.asr.model == "asr_1.7b"


def test_run_config_explicitly_resets_optional_resources(tmp_path, monkeypatch):
    from subtap.cli.pipeline_cli import _apply_run_config
    from subtap.schemas.config import SubtapConfig
    from subtap.schemas.task_request import SubtitleTaskRequest

    config = SubtapConfig()
    config.clean.glossary_path = "/old/glossary.yaml"
    config.output.script_path = "/old/script.txt"
    config.asr.hotwords = ["旧热词"]
    default_glossary = tmp_path / ".subtap" / "glossaries" / "default.yaml"
    default_glossary.parent.mkdir(parents=True)
    default_glossary.write_text("", encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    request = SubtitleTaskRequest(
        input_path=tmp_path / "voice.wav",
        output_dir=tmp_path / "output",
        mode="fast",
        use_default_glossary=True,
        disable_script=True,
        reset_hotwords=True,
    )

    _apply_run_config(
        config=config,
        request=request,
        timestamp=None,
        punctuation=None,
        max_chars=None,
        script_mode="follow_script",
        hotwords=None,
        work_dir=tmp_path / "work",
    )

    assert config.clean.glossary_path == str(default_glossary)
    assert config.output.script_path is None
    assert config.asr.hotwords == []
