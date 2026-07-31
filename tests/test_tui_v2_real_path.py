"""Real TUI v2 production path tests.

These tests exercise the actual production code paths for:
1. NewTranscriptionScreen.start() — real --tui to --tui-v2 transformation
2. WizardView.build_run_command() — real command generation
3. _build_observer_child_command() — real child command normalization
4. Normalized child args → runner.invoke → clean → export
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from subtap.core.pipeline import Pipeline
from subtap.ui.views.wizard import WizardView
from tests.fixtures.pipeline_stubs import (
    make_instrumented_init as _make_instrumented_init,
    stub_align as _stub_align_child,
    stub_asr as _stub_asr_child,
    stub_chunks as _stub_chunks_child,
    stub_hotword as _stub_hotword_child,
    stub_prepare as _stub_prepare_child,
)

cli_runner = CliRunner()

# ── helpers ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


def _ensure_default_glossary(tmp_path: Path) -> None:
    """Create the default glossary file so WizardView.validate() passes."""
    glossary_dir = tmp_path / ".subtap" / "glossaries"
    glossary_dir.mkdir(parents=True, exist_ok=True)
    (glossary_dir / "default.txt").write_text("# default glossary\n")


# ── Test 1: Real WizardView command generation ─────────────────────


class TestWizardViewRequest:
    """WizardView produces correct CLI command with --local-only and --tui."""

    def test_local_only_command_has_tui_flag(self, tmp_path):
        """local_only=True → command contains --local-only and --tui."""
        _ensure_default_glossary(tmp_path)
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav")

        wizard = WizardView()
        wizard.select_file(audio)
        wizard.select_quality("fast")
        wizard.select_output_dir(tmp_path / "output")
        wizard.select_max_chars(25)

        command = wizard.build_run_command()

        assert "--local-only" in command
        assert "--tui" in command

    def test_command_contains_input_and_output(self, tmp_path):
        """Command includes the selected input path and output directory."""
        _ensure_default_glossary(tmp_path)
        audio = tmp_path / "voice.wav"
        audio.write_bytes(b"fake-wav")
        output = tmp_path / "output"

        wizard = WizardView()
        wizard.select_file(audio)
        wizard.select_quality("fast")
        wizard.select_output_dir(output)
        wizard.select_max_chars(25)

        command = wizard.build_run_command()

        assert str(audio) in command
        assert str(output) in command

    def test_command_contains_max_chars(self, tmp_path):
        """Command includes the selected max_chars value."""
        _ensure_default_glossary(tmp_path)
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav")

        wizard = WizardView()
        wizard.select_file(audio)
        wizard.select_quality("fast")
        wizard.select_output_dir(tmp_path / "output")
        wizard.select_max_chars(30)

        command = wizard.build_run_command()

        assert "30" in command

    def test_command_contains_mode(self, tmp_path):
        """Command includes the selected quality mode."""
        _ensure_default_glossary(tmp_path)
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav")

        wizard = WizardView()
        wizard.select_file(audio)
        wizard.select_quality("quality")
        wizard.select_output_dir(tmp_path / "output")
        wizard.select_max_chars(25)

        command = wizard.build_run_command()

        assert "quality" in command


# ── Test 2: Real NewTranscriptionScreen --tui-v2 transformation ────


class TestNewTranscriptionTransformation:
    """NewTranscriptionScreen.start() performs the real --tui to --tui-v2 transformation.

    The production code at new_transcription.py:435-437:
        if command[-1:] != ["--tui"]:
            raise RuntimeError(...)
        command[-1] = "--tui-v2"

    These tests invoke the actual production method.  If the transformation
    is removed, these tests will fail.
    """

    def test_start_transforms_tui_to_tui_v2(self, tmp_path, monkeypatch):
        """Real start() transforms --tui to --tui-v2 in the production method."""
        from subtap.ui.v2.new_transcription import NewTranscriptionScreen

        _ensure_default_glossary(tmp_path)
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav")
        output = tmp_path / "output"
        output.mkdir(parents=True)

        # Mock load_config with real SubtapConfig
        from subtap.schemas.config import SubtapConfig

        config = SubtapConfig()
        config.output.directory = str(tmp_path / "default_output")
        monkeypatch.setattr(
            "subtap.ui.v2.new_transcription.load_config",
            lambda *_a, **_kw: config,
        )
        monkeypatch.setattr(
            "subtap.ui.v2.new_transcription.asr_mode_for_model",
            lambda _m: "fast",
        )
        monkeypatch.setattr(
            "subtap.ui.v2.new_transcription.apply_asr_mode",
            lambda _c, _m: None,
        )
        monkeypatch.setattr(
            "subtap.ui.v2.new_transcription.validate_runtime_models",
            lambda _c: None,
        )

        screen = NewTranscriptionScreen(input_path=audio)

        # Mock query_one to return configured widget values
        def mock_query_one(selector, widget_type=None):
            mocks = {
                "#output": SimpleNamespace(value=str(output)),
                "#quality": SimpleNamespace(value="fast"),
                "#glossary": SimpleNamespace(value=""),
                "#manuscript": SimpleNamespace(value=""),
                "#max-chars": SimpleNamespace(value="25"),
                "#status": SimpleNamespace(update=lambda *_a: None),
                "#open-models": SimpleNamespace(display=False),
                "#start": SimpleNamespace(disabled=False),
            }
            if isinstance(selector, str) and selector in mocks:
                return mocks[selector]
            return MagicMock()

        screen.query_one = mock_query_one

        # Intercept _finish_review to capture the transformed command
        captured_commands: list[list[str]] = []

        def capturing_finish(confirmed, command):
            captured_commands.append(command)

        screen._finish_review = capturing_finish

        # Mock app.push_screen to invoke the callback (simulating confirm)
        mock_app = MagicMock()
        mock_app.push_screen = lambda scr, cb=None: cb(True) if cb else None

        # Patch the app property on the screen's class
        monkeypatch.setattr(type(screen), "app", property(lambda self: mock_app))

        # Invoke the real production method
        screen.start()

        # Verify transformation
        assert len(captured_commands) == 1
        command = captured_commands[0]

        # --tui-v2 present, no standalone --tui
        assert "--tui-v2" in command
        assert "--tui" not in command, f"standalone --tui found: {command}"

        # Command contents
        assert "--local-only" in command
        assert str(audio) in command
        assert str(output) in command
        assert "25" in command

    def test_start_fails_without_tui_flag(self, tmp_path, monkeypatch):
        """start() raises RuntimeError if WizardView doesn't produce --tui."""
        from subtap.ui.v2.new_transcription import NewTranscriptionScreen

        _ensure_default_glossary(tmp_path)
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav")

        config = SimpleNamespace(
            asr=SimpleNamespace(model="asr_0.6b"),
            output=SimpleNamespace(
                max_chars=25,
                directory=str(tmp_path / "default_output"),
            ),
        )
        monkeypatch.setattr(
            "subtap.ui.v2.new_transcription.load_config",
            lambda *_a, **_kw: config,
        )
        monkeypatch.setattr(
            "subtap.ui.v2.new_transcription.asr_mode_for_model",
            lambda _m: "fast",
        )
        monkeypatch.setattr(
            "subtap.ui.v2.new_transcription.apply_asr_mode",
            lambda _c, _m: None,
        )
        monkeypatch.setattr(
            "subtap.ui.v2.new_transcription.validate_runtime_models",
            lambda _c: None,
        )

        screen = NewTranscriptionScreen(input_path=audio)

        output = tmp_path / "output"
        output.mkdir(parents=True)

        def mock_query_one(selector, widget_type=None):
            mocks = {
                "#output": SimpleNamespace(value=str(output)),
                "#quality": SimpleNamespace(value="fast"),
                "#glossary": SimpleNamespace(value=""),
                "#manuscript": SimpleNamespace(value=""),
                "#max-chars": SimpleNamespace(value="25"),
                "#status": SimpleNamespace(update=lambda *_a: None),
                "#open-models": SimpleNamespace(display=False),
                "#start": SimpleNamespace(disabled=False),
            }
            if isinstance(selector, str) and selector in mocks:
                return mocks[selector]
            return MagicMock()

        screen.query_one = mock_query_one

        # Monkeypatch WizardView to NOT produce --tui
        original_build = WizardView.build_run_command

        def broken_build(self_inner):
            cmd = original_build(self_inner)
            if cmd and cmd[-1] == "--tui":
                cmd[-1] = "--no-tui"
            return cmd

        monkeypatch.setattr(WizardView, "build_run_command", broken_build)

        mock_app = MagicMock()
        monkeypatch.setattr(type(screen), "app", property(lambda self: mock_app))

        with pytest.raises(RuntimeError, match="WizardView"):
            screen.start()


# ── Test 3: Observer-child command normalization ───────────────────


class TestObserverChildCommand:
    """_build_observer_child_command() strips parent flags and adds child flags."""

    def test_strips_tui_flags(self):
        """Observer flags (--tui, --tui-v2) are removed from child command."""
        from subtap.cli import _build_observer_child_command

        parent = ["subtap", "run", "voice.wav", "--tui", "--tui-v2"]
        child = _build_observer_child_command(parent)

        assert "--tui" not in child
        assert "--tui-v2" not in child

    def test_adds_observer_child_and_no_tui(self):
        """Child command includes --observer-child and --no-tui."""
        from subtap.cli import _build_observer_child_command

        parent = ["subtap", "run", "voice.wav", "--tui"]
        child = _build_observer_child_command(parent)

        assert "--observer-child" in child
        assert "--no-tui" in child

    def test_preserves_input_output_options(self):
        """Child command preserves task input/output options."""
        from subtap.cli import _build_observer_child_command

        parent = [
            "subtap",
            "run",
            "voice.wav",
            "--tui",
            "--local-only",
            "--work-dir",
            "/tmp/work",
            "--output-dir",
            "/tmp/output",
        ]
        child = _build_observer_child_command(parent)

        assert "voice.wav" in child
        assert "--local-only" in child
        assert "--work-dir" in child
        assert "/tmp/work" in child
        assert "--output-dir" in child
        assert "/tmp/output" in child

    def test_includes_launcher_prefix(self):
        """Child command starts with sys.executable -m subtap.cli."""
        from subtap.cli import _build_observer_child_command

        parent = ["subtap", "run", "voice.wav", "--tui"]
        child = _build_observer_child_command(parent)

        assert child[0] == sys.executable
        assert child[1] == "-m"
        assert child[2] == "subtap.cli"


# ── Test 4: Normalized child args → real CLI runner ────────────────


class TestNormalizedChildArgsExecution:
    """Normalized child args → real CLI runner → clean → export.

    Exercises the full production path:
        _build_observer_child_command()
            → strip launcher prefix
            → CliRunner.invoke(app, child_args)
            → real Pipeline + real RichRunner stage loop
            → clean → segment → export
    """

    def test_normalized_child_args_drives_clean_and_export(
        self, tmp_path, monkeypatch, skip_runtime_model_validation
    ):
        """Normalized child command args drive pipeline through clean and export."""
        from subtap.cli import _build_observer_child_command, app

        original_init = Pipeline.__init__
        instrumented = _make_instrumented_init(original_init, ["child  test  segment"])
        monkeypatch.setattr(Pipeline, "__init__", instrumented)
        monkeypatch.setattr("subtap.core.media.prepare_media", _stub_prepare_child)
        monkeypatch.setattr("subtap.core.vad.split_chunks", _stub_chunks_child)
        monkeypatch.setattr("subtap.core.asr.run_asr", _stub_asr_child)
        monkeypatch.setattr("subtap.core.align.run_align", _stub_align_child)
        monkeypatch.setattr("subtap.core.hotword.run_hotword", _stub_hotword_child)
        monkeypatch.setattr(
            "subtap.core.models.validate_runtime_models", lambda _c: None
        )
        monkeypatch.setattr("subtap.core.models.apply_asr_mode", lambda _c, _m: None)
        monkeypatch.setattr("subtap.core.models.asr_mode_for_model", lambda _m: "fast")

        def fail_if_llm(*_a, **_k):
            raise AssertionError("get_llm_backend must not be called")

        monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_llm)

        # Stub _generate_metrics to avoid model load measurement validation
        # (stubbed ASR/align backends don't emit model load events)
        monkeypatch.setattr(
            "subtap.cli.pipeline_cli._generate_metrics",
            lambda *_a, **_kw: None,
        )

        audio = tmp_path / "voice.wav"
        audio.write_bytes(b"audio")
        output = tmp_path / "output"
        work_dir = tmp_path / "work"

        # Build parent command and normalize to child args
        parent = [
            "subtap",
            "run",
            str(audio),
            "--tui",
            "--local-only",
            "--output-dir",
            str(output),
            "--work-dir",
            str(work_dir),
        ]
        child = _build_observer_child_command(parent)

        # Strip launcher prefix (sys.executable -m subtap.cli)
        cli_args = child[3:]

        result = cli_runner.invoke(app, cli_args)
        assert result.exit_code == 0, result.output

        # Verify clean stage produced cleaned.jsonl
        assert (work_dir / "cleaned.jsonl").exists()

        # Verify segment stage produced sentences.jsonl
        assert (work_dir / "sentences.jsonl").exists()

        # Verify export produced final SRT
        srt_path = output / "voice.srt"
        assert srt_path.exists()
        srt_text = srt_path.read_text()
        assert srt_text.strip()

        # Verify SRT contains cleaned (single-space) text, not double-space original
        assert "child test" in srt_text.lower()
        assert (
            "child  test" not in srt_text.lower()
        ), f"SRT still contains uncleaned double-space text: {srt_text[:200]}"
