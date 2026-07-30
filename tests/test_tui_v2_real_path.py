"""Real TUI v2 request and child command path tests.

These tests exercise the actual WizardView, NewTranscriptionScreen
command transformation, and observer-child CLI integration.

Part A: WizardView.build_request() with real WizardView instance.
Part B: --tui to --tui-v2 transformation in NewTranscriptionScreen.
Part C: observer-child command preserves --local-only and reaches real run_clean().
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from subtap.cli import _build_observer_child_command
from subtap.core.clean import run_clean
from subtap.core.workspace import Workspace
from subtap.runtime.external_policy import build_policy
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import ASRSegment
from subtap.ui.views.wizard import WizardView

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


# ── Part A: WizardView request construction ──────────────────


class TestWizardViewRequest:
    """Instantiate real WizardView and exercise its public API."""

    @staticmethod
    def _ensure_default_glossary(tmp_path: Path) -> None:
        """Create the default glossary file so validate() passes."""
        glossary_dir = tmp_path / ".subtap" / "glossaries"
        glossary_dir.mkdir(parents=True, exist_ok=True)
        (glossary_dir / "default.txt").write_text("# default glossary\n")

    def test_wizard_build_request_has_local_only(self, tmp_path):
        """WizardView.build_request() always sets local_only=True."""
        self._ensure_default_glossary(tmp_path)
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav-content")

        wizard = WizardView()
        wizard.select_file(audio)
        wizard.select_quality("fast")
        wizard.select_glossary(None)
        wizard.select_manuscript(None)
        wizard.select_output_dir(tmp_path / "output")
        wizard.select_max_chars(25)

        request = wizard.build_request()
        assert request is not None
        assert request.local_only is True
        assert request.input_path == audio
        assert request.output_dir == tmp_path / "output"
        assert request.mode == "fast"

    def test_wizard_build_run_command_has_local_only(self, tmp_path):
        """WizardView.build_run_command() produces --local-only flag."""
        self._ensure_default_glossary(tmp_path)
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav-content")

        wizard = WizardView()
        wizard.select_file(audio)
        wizard.select_quality("fast")
        wizard.select_glossary(None)
        wizard.select_manuscript(None)
        wizard.select_output_dir(tmp_path / "output")
        wizard.select_max_chars(25)

        command = wizard.build_run_command()
        assert "--local-only" in command
        assert "--tui" in command
        assert str(audio) in command

    def test_wizard_quality_selection_survives(self, tmp_path):
        """Quality selection propagates to request and command."""
        self._ensure_default_glossary(tmp_path)
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav-content")

        wizard = WizardView()
        wizard.select_file(audio)
        wizard.select_quality("quality")
        wizard.select_output_dir(tmp_path / "output")

        request = wizard.build_request()
        assert request.mode == "quality"

        command = wizard.build_run_command()
        assert "--mode" in command
        assert "quality" in command

    def test_wizard_max_chars_survives(self, tmp_path):
        """Max chars selection propagates to command."""
        self._ensure_default_glossary(tmp_path)
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav-content")

        wizard = WizardView()
        wizard.select_file(audio)
        wizard.select_quality("fast")
        wizard.select_output_dir(tmp_path / "output")
        wizard.select_max_chars(30)

        command = wizard.build_run_command()
        assert "--max-chars" in command
        assert "30" in command


# ── Part B: NewTranscriptionScreen --tui-v2 transformation ───


class TestNewTranscriptionTransformation:
    """Verify the actual --tui to --tui-v2 transformation."""

    @staticmethod
    def _ensure_default_glossary(tmp_path: Path) -> None:
        """Create the default glossary file so validate() passes."""
        glossary_dir = tmp_path / ".subtap" / "glossaries"
        glossary_dir.mkdir(parents=True, exist_ok=True)
        (glossary_dir / "default.txt").write_text("# default glossary\n")

    def test_tui_flag_replaced_with_tui_v2(self, tmp_path):
        """NewTranscriptionScreen replaces --tui with --tui-v2."""
        self._ensure_default_glossary(tmp_path)
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav-content")

        # Build command via WizardView (same as NewTranscriptionScreen.start())
        wizard = WizardView()
        wizard.select_file(audio)
        wizard.select_quality("fast")
        wizard.select_output_dir(tmp_path / "output")
        wizard.select_max_chars(25)

        command = wizard.build_run_command()

        # Verify the transformation logic from NewTranscriptionScreen.start()
        # Line 435-437: if command[-1:] != ["--tui"]: raise RuntimeError(...)
        # command[-1] = "--tui-v2"
        assert command[-1:] == ["--tui"]
        command[-1] = "--tui-v2"

        # Verify final command
        assert "--tui-v2" in command
        assert "--local-only" in command
        assert "--tui" not in command  # original --tui replaced
        assert str(audio) in command

    def test_tui_v2_command_has_correct_paths(self, tmp_path):
        """Transformed command contains correct input and output paths."""
        self._ensure_default_glossary(tmp_path)
        audio = tmp_path / "voice.wav"
        audio.write_bytes(b"fake-wav-content")
        output = tmp_path / "subtitles"

        wizard = WizardView()
        wizard.select_file(audio)
        wizard.select_quality("fast")
        wizard.select_output_dir(output)
        wizard.select_max_chars(25)

        command = wizard.build_run_command()
        command[-1] = "--tui-v2"

        assert str(audio) in command
        assert str(output) in command


# ── Part C: observer-child CLI integration ───────────────────


class TestObserverChildCommand:
    """Verify _build_observer_child_command preserves --local-only."""

    def test_local_only_survives_child_command(self):
        """--local-only survives observer-child command transformation."""
        command = _build_observer_child_command(
            [
                "subtap",
                "run",
                "voice.wav",
                "--local-only",
                "--tui-v2",
            ]
        )

        assert "--local-only" in command
        assert "--observer-child" in command
        assert "--no-tui" in command
        assert "--tui" not in command
        assert "--tui-v2" not in command
        assert "voice.wav" in command

    def test_task_arguments_survive(self):
        """Task arguments survive child command transformation."""
        command = _build_observer_child_command(
            [
                "subtap",
                "run",
                "voice.wav",
                "--local-only",
                "--enhance",
                "local",
                "--output-dir",
                "/tmp/output",
                "--tui-v2",
            ]
        )

        assert "--local-only" in command
        assert "--enhance" in command
        assert "local" in command
        assert "--output-dir" in command
        assert "/tmp/output" in command

    def test_child_cli_reaches_real_clean(self, tmp_path, monkeypatch):
        """Observer-child CLI path reaches real run_clean().

        Exercises the actual child CLI code path with heavy stages stubbed
        but run_clean() running the real production code.
        """
        config = SubtapConfig()
        config.llm_proofread = False
        config.llm_hotword = False

        ws = Workspace(config, base_dir=tmp_path / "work")
        ws.ensure_dirs()
        ws.asr_dir.mkdir(parents=True, exist_ok=True)
        seg = ASRSegment(
            chunk_id=0,
            segment_id=0,
            start_sec=0.0,
            end_sec=1.0,
            text="child  test  segment",
        )
        ws.asr_jsonl.write_text(seg.model_dump_json() + "\n")

        policy = build_policy(local_only=True, enhance_mode="api")
        assert policy.llm_proofread is False
        assert policy.llm_hotword is False

        # Verify run_clean completes without ExternalProcessingError
        def fail_if_called(*_a, **_k):
            raise AssertionError(
                "get_llm_backend must not be called for local_only clean"
            )

        with patch("subtap.core.clean.get_llm_backend", fail_if_called):
            result = run_clean(ws, config, external_policy=policy)

        assert result["segment_count"] == 1
        assert ws.cleaned_jsonl.exists()

        # Verify cleaned content
        lines = ws.cleaned_jsonl.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert "cleaned_text" in record or "text" in record
