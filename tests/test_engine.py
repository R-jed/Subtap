"""Tests for engine: state machine, policy, controller, events."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from subtap.engine.state import (
    PipelineState,
    StageState,
    StageStatus,
    STATUS_CN,
    STAGE_ORDER,
)
from subtap.engine.policy import ExecutionPolicy, PolicyMode
from subtap.engine.events import EventLogger
from subtap.schemas.config import SubtapConfig

# ── StageStatus tests ──


def test_stage_status_values():
    """All expected statuses exist."""
    expected = {"pending", "running", "success", "failed", "retrying", "skipped"}
    assert {s.value for s in StageStatus} == expected


def test_status_cn_covers_all():
    """STATUS_CN maps every StageStatus."""
    for status in StageStatus:
        assert status in STATUS_CN


# ── StageState tests ──


def test_stage_state_initial():
    """New StageState is PENDING."""
    s = StageState(name="asr", name_cn="语音识别")
    assert s.status == StageStatus.PENDING
    assert s.retry_count == 0
    assert s.can_retry is False  # not failed yet


def test_stage_state_can_retry():
    """can_retry is True only when FAILED and retries remain."""
    s = StageState(name="asr", name_cn="语音识别")
    s.transition(StageStatus.FAILED)
    assert s.can_retry is True
    s.retry_count = 3
    assert s.can_retry is False


def test_stage_state_is_terminal():
    """SUCCESS and SKIPPED are terminal."""
    s = StageState(name="asr", name_cn="语音识别")
    s.transition(StageStatus.SUCCESS)
    assert s.is_terminal is True
    s.transition(StageStatus.SKIPPED)
    assert s.is_terminal is True


def test_stage_state_to_dict():
    """to_dict returns expected keys."""
    s = StageState(name="asr", name_cn="语音识别")
    d = s.to_dict()
    assert d["name"] == "asr"
    assert d["name_cn"] == "语音识别"
    assert d["status"] == "pending"


# ── PipelineState tests ──


def test_pipeline_state_all_stages():
    """PipelineState has all 7 stages."""
    ps = PipelineState()
    assert len(ps.stages) == 7
    for name in STAGE_ORDER:
        assert name in ps.stages


def test_pipeline_state_progress():
    """Progress increases as stages complete."""
    ps = PipelineState()
    assert ps.progress_pct == 0.0

    ps.mark_success("prepare", {}, 0.1)
    assert ps.progress_pct > 0

    for name in STAGE_ORDER:
        ps.mark_success(name, {}, 0.1)
    assert ps.progress_pct == 100.0


def test_pipeline_state_current_stage():
    """current_stage returns the running stage."""
    ps = PipelineState()
    assert ps.current_stage is None

    ps.mark_running("asr")
    assert ps.current_stage == "asr"

    ps.mark_success("asr", {}, 1.0)
    assert ps.current_stage is None


def test_pipeline_state_listener():
    """State changes trigger listener callbacks."""
    ps = PipelineState()
    changes = []
    ps.on_change(lambda name, state: changes.append(name))

    ps.mark_running("chunk")
    ps.mark_success("chunk", {}, 0.5)
    assert changes == ["chunk", "chunk"]


def test_pipeline_state_reset():
    """Reset returns stage to PENDING."""
    ps = PipelineState()
    ps.mark_success("asr", {}, 1.0)
    assert ps.stages["asr"].status == StageStatus.SUCCESS

    ps.reset("asr")
    assert ps.stages["asr"].status == StageStatus.PENDING


# ── ExecutionPolicy tests ──


def test_policy_local():
    """LOCAL_ONLY policy: no LLM."""
    p = ExecutionPolicy("local")
    assert p.use_llm is False
    assert p.should_skip("clean") is False


def test_policy_fast():
    """FAST_MODE policy: no stages skipped."""
    p = ExecutionPolicy("fast")
    assert p.should_skip("clean") is False
    assert p.should_skip("align") is False
    assert p.should_skip("asr") is False


def test_policy_invalid_falls_back():
    """Invalid policy name falls back to LOCAL_ONLY."""
    p = ExecutionPolicy("nonexistent")
    assert p.mode == PolicyMode.LOCAL_ONLY


def test_policy_to_dict():
    """to_dict returns expected keys."""
    p = ExecutionPolicy("local")
    d = p.to_dict()
    assert d["mode"] == "local"
    assert "asr_backend" in d
    assert "skip_stages" in d


# ── EventLogger tests ──


def test_event_logger_write_and_read(tmp_path: Path):
    """Events are written to JSONL and can be read back."""
    logger = EventLogger(tmp_path / "logs")
    logger.log_stage_start("asr")
    logger.log_stage_success("asr", 1.5, {"segment_count": 10})

    events = logger.get_events()
    assert len(events) == 2
    assert events[0]["stage"] == "asr"
    assert events[0]["state"] == "start"
    assert events[1]["state"] == "success"
    assert events[1]["duration"] == 1.5


def test_event_logger_filter_by_stage(tmp_path: Path):
    """get_events can filter by stage name."""
    logger = EventLogger(tmp_path / "logs")
    logger.log_stage_start("asr")
    logger.log_stage_start("align")
    logger.log_stage_success("asr", 1.0, {})

    asr_events = logger.get_events(stage="asr")
    assert len(asr_events) == 2

    align_events = logger.get_events(stage="align")
    assert len(align_events) == 1


def test_event_logger_retry(tmp_path: Path):
    """Retry events are logged with retry count."""
    logger = EventLogger(tmp_path / "logs")
    logger.log_stage_retry("asr", 1)
    logger.log_stage_retry("asr", 2)

    events = logger.get_events()
    assert events[0]["retry_count"] == 1
    assert events[1]["retry_count"] == 2


def test_event_logger_clear(tmp_path: Path):
    """clear() removes all events."""
    logger = EventLogger(tmp_path / "logs")
    logger.log_stage_start("asr")
    assert len(logger.get_events()) == 1

    logger.clear()
    assert len(logger.get_events()) == 0


# ── PipelineController integration tests ──


def test_controller_state_machine(tmp_path: Path):
    """Controller transitions stages through states correctly."""
    from subtap.engine.controller import PipelineController

    config = SubtapConfig()
    ctrl = PipelineController(config, tmp_path / "work")

    # Initially all pending
    assert ctrl.state.get("asr").status == StageStatus.PENDING

    # Skip a stage
    ctrl.skip_stage("clean")
    assert ctrl.state.get("clean").status == StageStatus.SKIPPED

    # Rollback
    ctrl.rollback_stage("clean")
    assert ctrl.state.get("clean").status == StageStatus.PENDING


def test_controller_retry_fails_without_failure(tmp_path: Path):
    """retry_stage raises ValueError if stage isn't failed."""
    from subtap.engine.controller import PipelineController

    config = SubtapConfig()
    ctrl = PipelineController(config, tmp_path / "work")

    try:
        ctrl.retry_stage("asr")
        assert False, "Should have raised"
    except ValueError as e:
        assert "无法重试" in str(e)


def test_controller_retry_after_failure(tmp_path: Path):
    """retry_stage works after marking stage as failed."""
    from subtap.engine.controller import PipelineController

    config = SubtapConfig()
    ctrl = PipelineController(config, tmp_path / "work")

    # Simulate failure
    ctrl.state.mark_failed("asr", "test error")
    assert ctrl.state.get("asr").can_retry is True

    # retry_stage will fail again (no real audio), but it should attempt
    try:
        ctrl.retry_stage("asr")
    except Exception:
        pass  # expected — no real input file

    # Retry count should have incremented
    assert ctrl.state.get("asr").retry_count >= 1


def test_controller_policy_skip(tmp_path: Path):
    """Fast policy no longer skips any stage."""
    from subtap.engine.controller import PipelineController

    config = SubtapConfig()
    ctrl = PipelineController(config, tmp_path / "work", policy="fast")

    assert ctrl.policy.should_skip("clean") is False
    assert ctrl.policy.should_skip("align") is False
    assert ctrl.policy.should_skip("asr") is False


def test_controller_event_log(tmp_path: Path):
    """Controller writes events to event.log.jsonl."""
    from subtap.engine.controller import PipelineController

    config = SubtapConfig()
    ctrl = PipelineController(config, tmp_path / "work")

    ctrl.skip_stage("asr")
    events = ctrl.event_log.get_events()
    assert len(events) == 1
    assert events[0]["stage"] == "asr"
    assert events[0]["state"] == "skipped"


# ── CLI integration tests ──


def test_cli_run_with_enhance_flag(tmp_path: Path, monkeypatch):
    """CLI run command accepts --enhance flag."""
    from typer.testing import CliRunner
    from subtap.cli import app

    import subtap.schemas.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_config", lambda p: SubtapConfig())
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    fake_input = tmp_path / "test.mp3"
    fake_input.touch()

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "run",
            str(fake_input),
            "-w",
            str(tmp_path / "work"),
            "--enhance",
            "local",
        ],
    )
    # Should accept --enhance without error (may fail on actual audio processing)
    assert result.exit_code in (0, 1)


def test_cli_retry_command_exists():
    """retry command is registered in CLI."""
    from typer.testing import CliRunner
    from subtap.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["retry", "--help"])
    assert result.exit_code == 0
    assert "重试" in result.output


def test_cli_resume_command_exists():
    """resume command is registered in CLI."""
    from typer.testing import CliRunner
    from subtap.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["resume", "--help"])
    assert result.exit_code == 0
    assert "恢复" in result.output


# ── C3: Cross-process resume/retry regression tests ──


def test_resume_skips_persisted_successful_stages(tmp_path: Path):
    """C3-1: Resume skips SUCCESS stages and runs only remaining."""
    from subtap.engine.controller import PipelineController

    config = SubtapConfig()
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Lifecycle A: complete prepare/chunk/asr, fail at clean
    ctrl = PipelineController(config, work_dir)
    ctrl.state.mark_success("prepare", {}, 0.1)
    ctrl.state.mark_success("chunk", {}, 0.1)
    ctrl.state.mark_success("asr", {}, 0.1)
    ctrl.state.mark_failed("clean", "test error")
    ctrl._save_state()

    # Lifecycle B: new controller, load state, resume
    ctrl2 = PipelineController(config, work_dir)
    ctrl2.load_state()

    # Mock pipeline.run_stage to track calls
    calls = []

    def mock_run(stage, **kw):
        calls.append(stage)
        return {"segment_count": 1, "cleaned_jsonl": "x"}

    ctrl2._pipeline = MagicMock()
    ctrl2._pipeline.run_stage = mock_run

    ctrl2.resume_pipeline(
        tmp_path / "input.mp3",
        tmp_path / "output",
        fmt="srt",
    )

    assert calls == ["clean", "segment", "align", "export"]
    # Verify SUCCESS stages were NOT called
    assert "prepare" not in calls
    assert "chunk" not in calls
    assert "asr" not in calls


def test_resume_restarts_stage_left_running_after_crash(tmp_path: Path):
    """C3-2: Resume restarts a stage left in RUNNING state (crash recovery)."""
    from subtap.engine.controller import PipelineController

    config = SubtapConfig()
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Lifecycle A: prepare/chunk SUCCESS, asr RUNNING (process died)
    ctrl = PipelineController(config, work_dir)
    ctrl.state.mark_success("prepare", {}, 0.1)
    ctrl.state.mark_success("chunk", {}, 0.1)
    ctrl.state.mark_running("asr")
    ctrl._save_state()

    # Lifecycle B: new controller, load state, resume
    ctrl2 = PipelineController(config, work_dir)
    ctrl2.load_state()

    calls = []

    def mock_run2(stage, **kw):
        calls.append(stage)
        return {"segment_count": 1, "asr_jsonl": "x", "chunks_jsonl": "x"}

    ctrl2._pipeline = MagicMock()
    ctrl2._pipeline.run_stage = mock_run2

    ctrl2.resume_pipeline(
        tmp_path / "input.mp3",
        tmp_path / "output",
        fmt="srt",
    )

    assert calls == ["asr", "clean", "segment", "align", "export"]
    # No stage should be RUNNING or RETRYING in final state
    for name in STAGE_ORDER:
        status = ctrl2.state.get(name).status
        assert status not in (StageStatus.RUNNING, StageStatus.RETRYING)


def test_retry_loads_failed_stage_from_persisted_state(tmp_path: Path):
    """C3-3: Retry loads FAILED stage from persisted state and re-runs it."""
    from subtap.engine.controller import PipelineController

    config = SubtapConfig()
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Lifecycle A: prepare/chunk SUCCESS, asr FAILED
    ctrl = PipelineController(config, work_dir)
    ctrl.state.mark_success("prepare", {}, 0.1)
    ctrl.state.mark_success("chunk", {}, 0.1)
    ctrl.state.mark_failed("asr", "test error")
    ctrl._save_state()

    # Lifecycle B: new controller, load state, retry asr
    ctrl2 = PipelineController(config, work_dir)
    ctrl2.load_state()

    calls = []

    def mock_run3(stage, **kw):
        calls.append(stage)
        return {"segment_count": 1, "asr_jsonl": "x"}

    ctrl2._pipeline = MagicMock()
    ctrl2._pipeline.run_stage = mock_run3

    ctrl2.retry_stage("asr")

    assert calls == ["asr"]
    assert ctrl2.state.get("asr").status == StageStatus.SUCCESS
    # Downstream stages should be reset to PENDING
    assert ctrl2.state.get("clean").status == StageStatus.PENDING
    assert ctrl2.state.get("segment").status == StageStatus.PENDING

    # Verify state persisted on disk
    ctrl3 = PipelineController(config, work_dir)
    ctrl3.load_state()
    assert ctrl3.state.get("asr").status == StageStatus.SUCCESS


def test_retry_failure_is_persisted(tmp_path: Path):
    """C3-4: When retry handler fails again, final state is FAILED not RETRYING."""
    from subtap.engine.controller import PipelineController

    config = SubtapConfig()
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Set up FAILED stage
    ctrl = PipelineController(config, work_dir)
    ctrl.state.mark_failed("asr", "original error")
    ctrl._save_state()

    # Mock pipeline to raise on run_stage
    ctrl._pipeline = MagicMock()
    ctrl._pipeline.run_stage = MagicMock(side_effect=RuntimeError("still broken"))

    try:
        ctrl.retry_stage("asr")
    except RuntimeError:
        pass

    # Final state should be FAILED, not RETRYING or RUNNING
    assert ctrl.state.get("asr").status == StageStatus.FAILED
    assert ctrl.state.get("asr").retry_count >= 1

    # Verify persisted state matches
    ctrl2 = PipelineController(config, work_dir)
    ctrl2.load_state()
    assert ctrl2.state.get("asr").status == StageStatus.FAILED


def test_corrupt_pipeline_state_fails_explicitly(tmp_path: Path):
    """C3-5: Corrupt pipeline-state.json causes explicit failure."""
    from subtap.engine.state import PipelineState

    state_file = tmp_path / "pipeline-state.json"

    # Write corrupt JSON
    state_file.write_text('{"stages":', encoding="utf-8")

    try:
        PipelineState.load(state_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "无法读取或格式无效" in str(e)

    # Original corrupt file should be untouched
    assert state_file.read_text(encoding="utf-8") == '{"stages":'

    # Test missing stages field
    state_file.write_text('{"version": 1}', encoding="utf-8")
    try:
        PipelineState.load(state_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "无法读取或格式无效" in str(e)

    # Test missing status in stage data
    state_file.write_text(
        '{"version": 1, "stages": {"asr": {"retry_count": 0}}}',
        encoding="utf-8",
    )
    try:
        PipelineState.load(state_file)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "无法读取或格式无效" in str(e)


# ── C3 Production-Path: real pipeline writes state ──


def test_normal_run_persists_stage_state(tmp_path: Path):
    """C3-P1: Normal run via TrackedPipeline writes pipeline-state.json."""
    import os
    import subprocess
    import sys

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    input_file = tmp_path / "input.mp3"
    input_file.write_bytes(b"\x00" * 100)

    env = {
        **os.environ,
        "C3_TEST_MODE": "normal",
        "C3_INPUT_PATH": str(input_file),
        "C3_WORK_DIR": str(work_dir),
        "C3_OUTPUT_DIR": str(output_dir),
    }
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "_c3_test_helper.py")],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"helper failed: {result.stderr}"

    state_file = work_dir / "pipeline-state.json"
    assert state_file.exists(), "pipeline-state.json not created by normal run"

    state = PipelineState.load(state_file)
    for name in STAGE_ORDER:
        assert state.get(name).status == StageStatus.SUCCESS


def test_hard_crash_leaves_running_checkpoint(tmp_path: Path):
    """C3-P2: os._exit during ASR leaves RUNNING checkpoint on disk."""
    import os
    import subprocess
    import sys

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    input_file = tmp_path / "input.mp3"
    input_file.write_bytes(b"\x00" * 100)

    env = {
        **os.environ,
        "C3_TEST_MODE": "crash_at_asr",
        "C3_INPUT_PATH": str(input_file),
        "C3_WORK_DIR": str(work_dir),
        "C3_OUTPUT_DIR": str(output_dir),
    }
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "_c3_test_helper.py")],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    # os._exit(99) → non-zero exit
    assert result.returncode != 0

    state_file = work_dir / "pipeline-state.json"
    assert state_file.exists(), "state file missing after hard crash"

    state = PipelineState.load(state_file)
    assert state.get("prepare").status == StageStatus.SUCCESS
    assert state.get("chunk").status == StageStatus.SUCCESS
    assert state.get("asr").status == StageStatus.RUNNING
    # Remaining stages stay PENDING
    for name in ["clean", "segment", "align", "export"]:
        assert state.get(name).status == StageStatus.PENDING


def test_resume_after_hard_crash_skips_completed_stages(tmp_path: Path):
    """C3-P3: Resume after crash runs only remaining stages."""
    from subtap.engine.controller import PipelineController
    from subtap.schemas.config import SubtapConfig

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Simulate post-crash state: prepare/chunk SUCCESS, asr RUNNING
    ctrl = PipelineController(config=SubtapConfig(), work_dir=work_dir)
    ctrl.state.mark_success("prepare", {}, 0.1)
    ctrl.state.mark_success("chunk", {}, 0.1)
    ctrl.state.mark_running("asr")
    ctrl._save_state()

    # New lifecycle: load state, verify resume finds correct start point
    ctrl2 = PipelineController(config=SubtapConfig(), work_dir=work_dir)
    ctrl2.load_state()

    # Identify first incomplete stage
    first_incomplete = None
    for name in STAGE_ORDER:
        s = ctrl2.state.get(name)
        if s.status not in (StageStatus.SUCCESS, StageStatus.SKIPPED):
            first_incomplete = name
            break

    assert first_incomplete == "asr"

    # Fake remaining stage handlers
    calls = []
    fake = {
        "segment_count": 1,
        "asr_jsonl": "x",
        "cleaned_jsonl": "x",
        "sentence_count": 1,
        "sentences_jsonl": "x",
        "aligned_count": 1,
        "aligned_jsonl": "x",
    }

    def mock_run_resume(stage, **kw):
        calls.append(stage)
        return fake

    ctrl2._pipeline = MagicMock()
    ctrl2._pipeline.run_stage = mock_run_resume

    ctrl2.resume_pipeline(tmp_path / "input.mp3", tmp_path / "output", fmt="srt")

    assert calls == ["asr", "clean", "segment", "align", "export"]
    assert "prepare" not in calls
    assert "chunk" not in calls
    # Final state: no RUNNING or RETRYING
    for name in STAGE_ORDER:
        assert ctrl2.state.get(name).status not in (
            StageStatus.RUNNING,
            StageStatus.RETRYING,
        )


def test_new_run_replaces_previous_pipeline_state(tmp_path: Path):
    """C3-P4: New normal run creates fresh state, not inheriting old SUCCESS."""
    from subtap.engine.controller import PipelineController
    from subtap.engine.state import PipelineRunContext
    from subtap.schemas.config import SubtapConfig
    from subtap.core.tracked_pipeline import TrackedPipeline

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Lifecycle A: old run completed
    ctrl = PipelineController(config=SubtapConfig(), work_dir=work_dir)
    ctrl.state.context = PipelineRunContext(
        input_path="/tmp/test.mp3", output_dir="/tmp/out"
    )
    for name in STAGE_ORDER:
        ctrl.state.mark_success(name, {}, 0.1)
    ctrl._save_state()

    # Verify old state on disk
    old_state = PipelineState.load(work_dir / "pipeline-state.json")
    assert old_state.get("asr").status == StageStatus.SUCCESS

    # Lifecycle B: fresh TrackedPipeline creates new state
    pipeline = TrackedPipeline(config=SubtapConfig(), work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    # Simulate normal run: context must be set before save
    pipeline.set_stage_plan(
        pipeline.state.stage_order,
        PipelineRunContext(input_path="/tmp/new.mp3", output_dir="/tmp/new_out"),
    )

    # Fresh state should be all PENDING
    for name in STAGE_ORDER:
        assert pipeline.state.get(name).status == StageStatus.PENDING

    # After first stage, state is persisted and old state is overwritten
    pipeline.state.mark_running("prepare")
    pipeline.save_state()

    loaded = PipelineState.load(work_dir / "pipeline-state.json")
    assert loaded.get("prepare").status == StageStatus.RUNNING
    assert loaded.get("asr").status == StageStatus.PENDING  # not old SUCCESS


# ── C1: Pipeline preflight does not modify git state ──


def test_pipeline_preflight_does_not_modify_git_state(tmp_path: Path):
    """C1: Git preflight check is read-only — no auto-commit."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=repo, capture_output=True
    )
    (repo / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: init"], cwd=repo, capture_output=True
    )

    # Record HEAD before
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()

    # Create a dirty file (untracked, not staged)
    (repo / "dirty.txt").write_text("uncommitted")

    # Run preflight
    from subtap.engine.git_guard import GitGuard

    guard = GitGuard(repo)
    result = guard.pre_task_check()
    assert not result["ok"]

    # Verify HEAD unchanged (preflight is read-only)
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    assert head_before == head_after

    # Verify dirty.txt was NOT committed by preflight
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "dirty" not in log


# ── C2: Align ignores stale script_match when script disabled ──


def test_align_ignores_stale_script_match_when_script_disabled(tmp_path: Path):
    """C2: With script_path=None, _stage_align passes sentences.jsonl to run_align."""
    from subtap.schemas.config import SubtapConfig
    from subtap.core.workspace import Workspace
    from subtap.core.pipeline import Pipeline

    config = SubtapConfig()
    config.output.script_path = None

    ws = Workspace(config, base_dir=tmp_path / "work")
    ws.ensure_dirs()

    captured = {}

    def fake_run_align(workspace, config, **kwargs):
        captured["sentences_path"] = kwargs.get("sentences_path")
        return {"aligned_count": 0}

    import subtap.core.align as align_mod

    original = align_mod.run_align
    align_mod.run_align = fake_run_align
    try:
        pipeline = Pipeline(config, work_dir=tmp_path / "work")
        pipeline._stage_align()
        assert captured["sentences_path"] == ws.sentences_jsonl
    finally:
        align_mod.run_align = original


# ── C4: Timestamp formatting edge cases ──


def test_fmt_srt_time_rounding():
    """C4: _fmt_srt_time rounds correctly at boundaries."""
    from subtap.core.export import _fmt_srt_time

    assert _fmt_srt_time(1.9996) == "00:00:02,000"
    assert _fmt_srt_time(59.9996) == "00:01:00,000"
    assert _fmt_srt_time(3599.9996) == "01:00:00,000"
    assert _fmt_srt_time(0.0) == "00:00:00,000"
    assert _fmt_srt_time(-1.0) == "00:00:00,000"


def test_fmt_ass_time_rounding():
    """C4: _fmt_ass_time rounds correctly at boundaries."""
    from subtap.core.export import _fmt_ass_time

    assert _fmt_ass_time(1.996) == "0:00:02.00"
    assert _fmt_ass_time(59.996) == "0:01:00.00"
    assert _fmt_ass_time(3599.996) == "1:00:00.00"
    assert _fmt_ass_time(0.0) == "0:00:00.00"
    assert _fmt_ass_time(-1.0) == "0:00:00.00"


# ── C5: Segment timing invariants ──


def _fix_word_timestamps(words: list[dict]) -> list[dict]:
    """Replicate align.py word timestamp fixup for testing."""
    for w in words:
        if w["end_sec"] <= w["start_sec"]:
            w["end_sec"] = w["start_sec"] + 0.020
    for k in range(len(words) - 1):
        if words[k]["end_sec"] > words[k + 1]["start_sec"]:
            words[k + 1]["start_sec"] = words[k]["end_sec"]
            if words[k + 1]["end_sec"] <= words[k + 1]["start_sec"]:
                words[k + 1]["end_sec"] = words[k + 1]["start_sec"] + 0.020
    return words


def _assert_timing_invariants(words: list[dict]) -> None:
    for i, w in enumerate(words):
        assert (
            w["end_sec"] > w["start_sec"]
        ), f"word[{i}] end_sec({w['end_sec']}) <= start_sec({w['start_sec']})"
        if i > 0:
            assert words[i - 1]["end_sec"] <= w["start_sec"], (
                f"word[{i-1}].end_sec({words[i-1]['end_sec']}) > "
                f"word[{i}].start_sec({w['start_sec']})"
            )


def test_c5_last_word_zero_duration():
    """C5: Last word with zero duration gets minimum 20ms."""
    words = [
        {"word": "hello", "start_sec": 0.0, "end_sec": 0.5},
        {"word": "world", "start_sec": 0.5, "end_sec": 0.5},
    ]
    words = _fix_word_timestamps(words)
    _assert_timing_invariants(words)
    assert words[1]["end_sec"] == 0.520


def test_c5_overlap_pushes_start_past_end():
    """C5: Overlap pushes next start past previous end."""
    words = [
        {"word": "a", "start_sec": 0.0, "end_sec": 1.0},
        {"word": "b", "start_sec": 0.5, "end_sec": 0.8},
    ]
    words = _fix_word_timestamps(words)
    _assert_timing_invariants(words)
    assert words[1]["start_sec"] == 1.0


def test_c5_cascading_overlap():
    """C5: Cascading overlaps are resolved sequentially."""
    words = [
        {"word": "a", "start_sec": 0.0, "end_sec": 1.0},
        {"word": "b", "start_sec": 0.5, "end_sec": 0.8},
        {"word": "c", "start_sec": 0.6, "end_sec": 0.9},
        {"word": "d", "start_sec": 0.7, "end_sec": 1.0},
    ]
    words = _fix_word_timestamps(words)
    _assert_timing_invariants(words)


def test_c5_empty_words():
    """C5: Empty word list doesn't crash."""
    words = _fix_word_timestamps([])
    assert words == []


def test_c5_single_word():
    """C5: Single word with zero duration is fixed."""
    words = [{"word": "x", "start_sec": 1.0, "end_sec": 1.0}]
    words = _fix_word_timestamps(words)
    _assert_timing_invariants(words)
    assert words[0]["end_sec"] == 1.020


# ── C3-E: Dynamic stage plan & context persistence ──


def test_pipeline_state_v2_dynamic_stage_order():
    """PipelineState.new() creates state with custom stage_order."""
    from subtap.engine.state import PipelineRunContext

    order = [
        "prepare",
        "chunk",
        "asr",
        "clean",
        "segment",
        "script_match",
        "align",
        "export",
    ]
    ctx = PipelineRunContext(
        input_path="/tmp/test.mp3",
        output_dir="/tmp/out",
        script_path="/tmp/script.txt",
    )
    ps = PipelineState.new(stage_order=order, context=ctx)

    assert ps.stage_order == order
    assert len(ps.stages) == 8
    assert "script_match" in ps.stages
    assert ps.context is not None
    assert ps.context.script_path == "/tmp/script.txt"


def test_pipeline_state_v2_roundtrip():
    """V2 state with stage_order and context survives save/load."""
    from subtap.engine.state import PipelineRunContext

    order = [
        "prepare",
        "chunk",
        "asr",
        "clean",
        "segment",
        "align",
        "hotword",
        "learn",
        "export",
    ]
    ctx = PipelineRunContext(
        input_path="/tmp/in.mp3",
        output_dir="/tmp/out",
        translate_to="en",
        bilingual="source-first",
        glossary_path="/tmp/glossary.json",
    )
    ps = PipelineState.new(stage_order=order, context=ctx)
    ps.mark_success("prepare", {}, 0.1)
    ps.mark_success("chunk", {}, 0.2)
    ps.mark_running("asr")

    data = ps.to_dict()
    assert data["version"] == 2
    assert data["stage_order"] == order
    assert data["context"]["translate_to"] == "en"
    assert data["context"]["bilingual"] == "source-first"

    restored = PipelineState.from_dict(data)
    assert restored.stage_order == order
    assert "hotword" in restored.stages
    assert "learn" in restored.stages
    assert restored.get("prepare").status == StageStatus.SUCCESS
    assert restored.get("asr").status == StageStatus.RUNNING
    assert restored.context.translate_to == "en"
    assert restored.context.bilingual == "source-first"


def test_pipeline_state_v1_backward_compat():
    """V1 state (no stage_order/context) loads with default 7-stage order."""
    v1_data = {
        "version": 1,
        "stages": {
            "prepare": {
                "status": "success",
                "retry_count": 0,
                "error_msg": "",
                "duration_sec": 0.1,
            },
            "chunk": {
                "status": "success",
                "retry_count": 0,
                "error_msg": "",
                "duration_sec": 0.1,
            },
            "asr": {
                "status": "running",
                "retry_count": 0,
                "error_msg": "",
                "duration_sec": 0.0,
            },
            "clean": {
                "status": "pending",
                "retry_count": 0,
                "error_msg": "",
                "duration_sec": 0.0,
            },
            "segment": {
                "status": "pending",
                "retry_count": 0,
                "error_msg": "",
                "duration_sec": 0.0,
            },
            "align": {
                "status": "pending",
                "retry_count": 0,
                "error_msg": "",
                "duration_sec": 0.0,
            },
            "export": {
                "status": "pending",
                "retry_count": 0,
                "error_msg": "",
                "duration_sec": 0.0,
            },
        },
    }
    ps = PipelineState.from_dict(v1_data)
    assert ps.stage_order == STAGE_ORDER
    assert len(ps.stages) == 7
    assert ps.context is None
    assert ps.get("prepare").status == StageStatus.SUCCESS
    assert ps.get("asr").status == StageStatus.RUNNING


def _run_helper_subprocess(
    tmp_path, mode, script_path="", translate_to="", glossary_path=""
):
    """Run _c3_test_helper.py as subprocess, return (returncode, state_file_path)."""
    import os
    import subprocess
    import sys

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    input_file = tmp_path / "input.mp3"
    input_file.write_bytes(b"\x00" * 100)

    env = {
        **os.environ,
        "C3_TEST_MODE": mode,
        "C3_INPUT_PATH": str(input_file),
        "C3_WORK_DIR": str(work_dir),
        "C3_OUTPUT_DIR": str(output_dir),
        "C3_SCRIPT_PATH": script_path,
        "C3_TRANSLATE_TO": translate_to,
        "C3_GLOSSARY_PATH": glossary_path,
    }
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "_c3_test_helper.py")],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, work_dir / "pipeline-state.json"


# ── C3-E1: script_match hard crash → same artifact resume ──


def test_script_match_crash_and_resume(tmp_path: Path):
    """C3-E1: script_match crash leaves RUNNING, resume continues from script_match."""
    script_file = tmp_path / "script.txt"
    script_file.write_text("test script content\n", encoding="utf-8")

    returncode, state_file = _run_helper_subprocess(
        tmp_path, "crash_at_script_match", script_path=str(script_file)
    )
    assert returncode != 0, "Expected non-zero exit from os._exit(97)"
    assert state_file.exists(), "state file missing after crash"

    state = PipelineState.load(state_file)
    # Core stages before script_match should be SUCCESS
    for name in ["prepare", "chunk", "asr", "clean", "segment"]:
        assert (
            state.get(name).status == StageStatus.SUCCESS
        ), f"{name} should be SUCCESS"
    # script_match should be RUNNING (crash checkpoint)
    assert state.get("script_match").status == StageStatus.RUNNING
    # Remaining stages should be PENDING
    for name in ["align", "hotword", "learn", "export"]:
        assert (
            state.get(name).status == StageStatus.PENDING
        ), f"{name} should be PENDING"

    # stage_order should include script_match
    assert "script_match" in state.stage_order

    # Resume using the same state file — new lifecycle
    from subtap.engine.controller import PipelineController

    config = SubtapConfig()
    config.output.script_path = str(script_file)
    ctrl = PipelineController(config, tmp_path / "work")
    ctrl.load_state()

    calls = []

    def mock_run_e1(stage, **kw):
        calls.append(stage)
        return {"segment_count": 1, "aligned_count": 1}

    ctrl._pipeline = MagicMock()
    ctrl._pipeline.run_stage = mock_run_e1

    ctrl.resume_pipeline(tmp_path / "input.mp3", tmp_path / "output", fmt="srt")

    # Must resume from script_match, not skip it
    assert (
        calls[0] == "script_match"
    ), f"First stage should be script_match, got {calls[0]}"
    # Core stages must NOT be re-executed
    for name in ["prepare", "chunk", "asr", "clean", "segment"]:
        assert name not in calls, f"{name} should not be re-executed"


# ── C3-E2: translate hard crash → same artifact resume ──


def test_translate_crash_and_resume(tmp_path: Path):
    """C3-E2: translate crash leaves RUNNING, resume continues from translate."""
    returncode, state_file = _run_helper_subprocess(
        tmp_path, "crash_at_translate", translate_to="en"
    )
    assert returncode != 0, "Expected non-zero exit from os._exit(96)"
    assert state_file.exists(), "state file missing after crash"

    state = PipelineState.load(state_file)
    # Core stages should be SUCCESS
    for name in ["prepare", "chunk", "asr", "clean", "segment", "align"]:
        assert (
            state.get(name).status == StageStatus.SUCCESS
        ), f"{name} should be SUCCESS"
    # hotword/learn should be SUCCESS (they run before translate)
    for name in ["hotword", "learn"]:
        assert (
            state.get(name).status == StageStatus.SUCCESS
        ), f"{name} should be SUCCESS"
    # translate should be RUNNING
    assert state.get("translate").status == StageStatus.RUNNING
    # export should be PENDING
    assert state.get("export").status == StageStatus.PENDING

    assert "translate" in state.stage_order

    # Resume
    from subtap.engine.controller import PipelineController

    config = SubtapConfig()
    ctrl = PipelineController(config, tmp_path / "work")
    ctrl.load_state()

    calls = []

    def mock_run_e2(stage, **kw):
        calls.append(stage)
        return {"translated_count": 1, "output_path": "x.srt", "segment_count": 1}

    ctrl._pipeline = MagicMock()
    ctrl._pipeline.run_stage = mock_run_e2

    ctrl.resume_pipeline(tmp_path / "input.mp3", tmp_path / "output", fmt="srt")

    assert calls == ["translate", "export"]
    # Previous stages must NOT be re-executed
    for name in [
        "prepare",
        "chunk",
        "asr",
        "clean",
        "segment",
        "align",
        "hotword",
        "learn",
    ]:
        assert name not in calls


# ── C3-E3: original CLI context survives resume ──


def test_resume_restores_original_context(tmp_path: Path):
    """C3-E3: Resume uses persisted context, not current config defaults."""
    from subtap.engine.controller import PipelineController
    from subtap.engine.state import PipelineRunContext

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    ctx = PipelineRunContext(
        input_path=str(tmp_path / "original.mp3"),
        output_dir=str(tmp_path / "original_out"),
        fmt="ass",
        translate_to="en",
        bilingual="source-first",
        script_path=str(tmp_path / "original_script.txt"),
    )
    state = PipelineState.new(
        stage_order=["prepare", "chunk", "asr", "clean", "segment", "align", "export"],
        context=ctx,
    )
    state.mark_success("prepare", {}, 0.1)
    state.mark_success("chunk", {}, 0.1)
    state.mark_running("asr")
    state.save(work_dir / "pipeline-state.json")

    # Resume with DIFFERENT args — should use persisted context
    config = SubtapConfig()
    ctrl = PipelineController(config, work_dir)
    ctrl.load_state()

    calls = []

    def mock_run_e3(stage, **kw):
        calls.append(stage)
        return {"segment_count": 1}

    ctrl._pipeline = MagicMock()
    ctrl._pipeline.run_stage = mock_run_e3

    # Pass different input_path/output_dir — persisted context should override
    ctrl.resume_pipeline(
        tmp_path / "different.mp3",
        tmp_path / "different_out",
        fmt="srt",
    )

    # Verify context was restored
    assert ctrl._run_context is not None
    assert ctrl._run_context.translate_to == "en"
    assert ctrl._run_context.bilingual == "source-first"
    assert ctrl._run_context.script_path == str(tmp_path / "original_script.txt")


# ── C3-E4: new normal run overwrites old plan/context ──


def test_new_run_overwrites_old_plan_and_context(tmp_path: Path):
    """C3-E4: New normal run creates fresh state, discarding old plan/context."""
    from subtap.core.tracked_pipeline import TrackedPipeline
    from subtap.engine.state import PipelineRunContext

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Run A: script + translate enabled
    old_order = [
        "prepare",
        "chunk",
        "asr",
        "clean",
        "segment",
        "script_match",
        "align",
        "hotword",
        "learn",
        "translate",
        "export",
    ]
    old_ctx = PipelineRunContext(
        input_path="/tmp/old.mp3",
        output_dir="/tmp/old_out",
        script_path="/tmp/old_script.txt",
        translate_to="en",
    )
    old_state = PipelineState.new(stage_order=old_order, context=old_ctx)
    for name in old_order:
        old_state.mark_success(name, {}, 0.1)
    old_state.save(work_dir / "pipeline-state.json")

    # Run B: no script, no translate — fresh TrackedPipeline
    config = SubtapConfig()
    config.output.script_path = ""
    pipeline = TrackedPipeline(
        config,
        work_dir=work_dir,
        stage_order=["prepare", "chunk", "asr", "clean", "segment", "align", "export"],
    )
    pipeline.workspace.ensure_dirs()

    # Simulate normal run creating context before save
    pipeline.set_stage_plan(
        pipeline.state.stage_order,
        PipelineRunContext(
            input_path="/tmp/new.mp3",
            output_dir="/tmp/new_out",
        ),
    )

    # New state should NOT have script_match or translate
    assert "script_match" not in pipeline.state.stage_order
    assert "translate" not in pipeline.state.stage_order

    # Save and reload
    pipeline.save_state()
    loaded = PipelineState.load(work_dir / "pipeline-state.json")
    assert "script_match" not in loaded.stage_order
    assert "translate" not in loaded.stage_order
    # All stages should be PENDING (fresh run)
    for name in loaded.stage_order:
        assert loaded.get(name).status == StageStatus.PENDING


# ── C2 fix: align uses production path for sentences_path ──


def test_align_uses_production_path_for_sentences(tmp_path: Path):
    """C2: Pipeline._stage_align passes correct sentences_path to run_align."""
    from subtap.core.pipeline import Pipeline
    from subtap.core.workspace import Workspace

    # Case A: script_path=None → should use sentences.jsonl
    config_a = SubtapConfig()
    config_a.output.script_path = None
    ws_a = Workspace(config_a, base_dir=tmp_path / "work_a")
    ws_a.ensure_dirs()

    captured = {}

    def fake_run_align(workspace, config, **kwargs):
        captured["sentences_path"] = kwargs.get("sentences_path")
        return {"aligned_count": 0}

    import subtap.core.align as align_mod

    original = align_mod.run_align
    align_mod.run_align = fake_run_align
    try:
        p = Pipeline(config_a, work_dir=tmp_path / "work_a")
        p._stage_align()
        assert captured["sentences_path"] == ws_a.sentences_jsonl
    finally:
        align_mod.run_align = original

    # Case B: script_path set → should use script_matched.jsonl
    config_b = SubtapConfig()
    config_b.output.script_path = str(tmp_path / "script.txt")
    ws_b = Workspace(config_b, base_dir=tmp_path / "work_b")
    ws_b.ensure_dirs()

    captured.clear()
    align_mod.run_align = fake_run_align
    try:
        p = Pipeline(config_b, work_dir=tmp_path / "work_b")
        p._stage_align()
        assert captured["sentences_path"] == ws_b.script_matched_jsonl
    finally:
        align_mod.run_align = original


# ── Config restoration regression tests ──


def test_no_script_override_survives_resume(tmp_path: Path):
    """CR-1: --no-script override (script_path=None) survives resume.

    Global config has script_path=old.txt, but original run used --no-script.
    After restore, config.output.script_path must be None.
    """
    from subtap.engine.controller import PipelineController
    from subtap.engine.state import PipelineRunContext

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Config starts with script_path set (simulates global config)
    config = SubtapConfig()
    config.output.script_path = "old.txt"

    # Persisted context from --no-script run: script_path is empty
    ctx = PipelineRunContext(
        input_path=str(tmp_path / "test.mp3"),
        output_dir=str(tmp_path / "out"),
        script_path="",  # --no-script
    )
    state = PipelineState.new(
        stage_order=["prepare", "chunk", "asr", "clean", "segment", "align", "export"],
        context=ctx,
    )
    state.mark_success("prepare", {}, 0.1)
    state.mark_success("chunk", {}, 0.1)
    state.mark_running("asr")
    state.save(work_dir / "pipeline-state.json")

    # Resume
    ctrl = PipelineController(config, work_dir)
    ctrl.load_state()

    # script_path must be None (not "old.txt")
    assert config.output.script_path is None


def test_quality_mode_survives_resume(tmp_path: Path):
    """CR-2: Quality ASR model survives resume."""
    from subtap.engine.controller import PipelineController
    from subtap.engine.state import PipelineRunContext

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    config = SubtapConfig()
    config.asr.model = "asr_0.6b"  # Default

    ctx = PipelineRunContext(
        input_path=str(tmp_path / "test.mp3"),
        output_dir=str(tmp_path / "out"),
        asr_model="asr_1.7b",  # Quality mode
    )
    state = PipelineState.new(
        stage_order=["prepare", "chunk", "asr", "clean", "segment", "align", "export"],
        context=ctx,
    )
    state.mark_success("prepare", {}, 0.1)
    state.mark_running("chunk")
    state.save(work_dir / "pipeline-state.json")

    ctrl = PipelineController(config, work_dir)
    ctrl.load_state()

    assert config.asr.model == "asr_1.7b"


def test_asr_hotwords_survive_resume(tmp_path: Path):
    """CR-3: ASR hotwords survive resume."""
    from subtap.engine.controller import PipelineController
    from subtap.engine.state import PipelineRunContext

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    config = SubtapConfig()
    config.asr.hotwords = []

    ctx = PipelineRunContext(
        input_path=str(tmp_path / "test.mp3"),
        output_dir=str(tmp_path / "out"),
        asr_hotwords="Foo,Bar",
    )
    state = PipelineState.new(
        stage_order=["prepare", "chunk", "asr", "clean", "segment", "align", "export"],
        context=ctx,
    )
    state.mark_success("prepare", {}, 0.1)
    state.mark_running("chunk")
    state.save(work_dir / "pipeline-state.json")

    ctrl = PipelineController(config, work_dir)
    ctrl.load_state()

    assert config.asr.hotwords == ["Foo", "Bar"]


def test_llm_flags_survive_resume(tmp_path: Path):
    """CR-4: LLM flags (proofread=False, hotword=True) survive resume."""
    from subtap.engine.controller import PipelineController
    from subtap.engine.state import PipelineRunContext

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    config = SubtapConfig()
    config.llm_proofread = True  # Opposite of what was persisted
    config.llm_hotword = False

    ctx = PipelineRunContext(
        input_path=str(tmp_path / "test.mp3"),
        output_dir=str(tmp_path / "out"),
        llm_proofread=False,
        llm_hotword=True,
    )
    state = PipelineState.new(
        stage_order=["prepare", "chunk", "asr", "clean", "segment", "align", "export"],
        context=ctx,
    )
    state.mark_success("prepare", {}, 0.1)
    state.mark_running("chunk")
    state.save(work_dir / "pipeline-state.json")

    ctrl = PipelineController(config, work_dir)
    ctrl.load_state()

    assert config.llm_proofread is False
    assert config.llm_hotword is True


def test_context_roundtrip_preserves_all_fields(tmp_path: Path):
    """CR-5: PipelineRunContext roundtrip preserves all fields."""
    from subtap.engine.state import PipelineRunContext

    ctx = PipelineRunContext(
        input_path="/tmp/test.mp3",
        output_dir="/tmp/out",
        fmt="ass",
        enhance="api",
        translate_to="en",
        bilingual="source-first",
        script_path="",
        script_mode="correct_only",
        subtitle_language="en",
        subtitle_punctuation=True,
        max_chars=40,
        glossary_path="",
        llm_proofread=False,
        llm_hotword=True,
        asr_backend="http-asr",
        asr_model="asr_1.7b",
        asr_hotwords="Foo,Bar",
        subtitle_stem="custom",
        policy_mode="local",
        local_only=True,
    )

    data = ctx.to_dict()
    restored = PipelineRunContext.from_dict(data)

    assert restored.input_path == "/tmp/test.mp3"
    assert restored.output_dir == "/tmp/out"
    assert restored.fmt == "ass"
    assert restored.enhance == "api"
    assert restored.translate_to == "en"
    assert restored.bilingual == "source-first"
    assert restored.script_path == ""
    assert restored.script_mode == "correct_only"
    assert restored.subtitle_language == "en"
    assert restored.subtitle_punctuation is True
    assert restored.max_chars == 40
    assert restored.glossary_path == ""
    assert restored.llm_proofread is False
    assert restored.llm_hotword is True
    assert restored.asr_backend == "http-asr"
    assert restored.asr_model == "asr_1.7b"
    assert restored.asr_hotwords == "Foo,Bar"
    assert restored.subtitle_stem == "custom"
    assert restored.policy_mode == "local"
    assert restored.local_only is True


# ── Legacy v2 state rejection tests ──


def _make_v2_context_data(**overrides) -> dict:
    """Build a complete valid v2 context dict matching PipelineRunContext schema."""
    base = {
        "input_path": "/tmp/test.mp3",
        "output_dir": "/tmp/out",
        "fmt": "srt",
        "enhance": "local",
        "translate_to": "",
        "bilingual": "off",
        "script_path": "",
        "script_mode": "follow_script",
        "subtitle_language": "zh",
        "subtitle_punctuation": False,
        "max_chars": 24,
        "glossary_path": "",
        "llm_proofread": False,
        "llm_hotword": False,
        "asr_backend": "mlx-qwen-asr",
        "asr_model": "asr_0.6b",
        "asr_hotwords": "",
        "subtitle_stem": "final",
        "policy_mode": "local",
        "local_only": False,
    }
    base.update(overrides)
    return base


def _make_v2_state_dict(context: dict | None = None) -> dict:
    """Build a minimal valid v2 state dict. Includes a complete context by default."""
    data: dict = {
        "version": 2,
        "stage_order": [
            "prepare",
            "chunk",
            "asr",
            "clean",
            "segment",
            "align",
            "export",
        ],
        "stages": {
            name: {
                "status": "pending",
                "retry_count": 0,
                "max_retries": 3,
                "error_msg": "",
                "result": {},
                "duration_sec": 0.0,
            }
            for name in [
                "prepare",
                "chunk",
                "asr",
                "clean",
                "segment",
                "align",
                "export",
            ]
        },
    }
    # v2 requires context; default to a complete valid one
    data["context"] = context if context is not None else _make_v2_context_data()
    return data


def test_v2_legacy_missing_both_fields_rejected():
    """LV2-1: v2 context missing asr_model and local_only raises ValueError."""
    ctx = _make_v2_context_data()
    del ctx["asr_model"]
    del ctx["local_only"]
    data = _make_v2_state_dict(context=ctx)

    with pytest.raises(ValueError, match="missing required fields"):
        PipelineState.from_dict(data)


def test_v2_legacy_missing_local_only_rejected():
    """LV2-2: v2 context missing only local_only raises ValueError."""
    ctx = _make_v2_context_data()
    del ctx["local_only"]
    data = _make_v2_state_dict(context=ctx)

    with pytest.raises(ValueError, match="local_only"):
        PipelineState.from_dict(data)


def test_v2_legacy_missing_asr_model_rejected():
    """LV2-3: v2 context missing only asr_model raises ValueError."""
    ctx = _make_v2_context_data()
    del ctx["asr_model"]
    data = _make_v2_state_dict(context=ctx)

    with pytest.raises(ValueError, match="asr_model"):
        PipelineState.from_dict(data)


def test_v2_valid_with_safety_fields_loads():
    """LV2-4: v2 state with complete context loads successfully."""
    ctx = _make_v2_context_data(asr_model="asr_1.7b", local_only=True)
    data = _make_v2_state_dict(context=ctx)

    state = PipelineState.from_dict(data)
    assert state.context is not None
    assert state.context.asr_model == "asr_1.7b"
    assert state.context.local_only is True


def test_v2_legacy_invalid_preserves_file(tmp_path: Path):
    """LV2-5: Loading invalid legacy v2 state does not modify the file."""
    ctx = _make_v2_context_data()
    del ctx["asr_model"]
    del ctx["local_only"]
    data = _make_v2_state_dict(context=ctx)

    state_file = tmp_path / "pipeline-state.json"
    import json

    state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    original_content = state_file.read_text(encoding="utf-8")

    with pytest.raises(ValueError):
        PipelineState.load(state_file)

    # File must be exactly unchanged
    assert state_file.read_text(encoding="utf-8") == original_content


# ── Phase 2B: strict v2 schema validation ──────────────────────────


def test_v2_missing_context_rejected():
    """SV2-A: v2 state without context field raises ValueError."""
    data = _make_v2_state_dict()
    # _make_v2_state_dict includes context=None by default; remove it
    data.pop("context", None)

    with pytest.raises(ValueError, match="missing required 'context'"):
        PipelineState.from_dict(data)


def test_v2_null_context_rejected():
    """SV2-B: v2 state with context=null raises ValueError."""
    data = _make_v2_state_dict()
    data["context"] = None  # explicitly set to null

    with pytest.raises(ValueError, match="context.*must be a dict"):
        PipelineState.from_dict(data)


def test_v2_missing_stage_in_stages_rejected():
    """SV2-C: stage_order has key missing from stages raises ValueError."""
    ctx = _make_v2_context_data()
    data = _make_v2_state_dict(context=ctx)
    # stage_order includes all stages, but remove 'asr' from stages
    del data["stages"]["asr"]

    with pytest.raises(ValueError, match="missing keys"):
        PipelineState.from_dict(data)


def test_v2_extra_stage_in_stages_rejected():
    """SV2-D: stages has extra key not in stage_order raises ValueError."""
    ctx = _make_v2_context_data()
    data = _make_v2_state_dict(context=ctx)
    data["stages"]["phantom"] = {
        "status": "pending",
        "retry_count": 0,
        "max_retries": 3,
        "error_msg": "",
        "result": {},
        "duration_sec": 0.0,
    }

    with pytest.raises(ValueError, match="extra keys"):
        PipelineState.from_dict(data)


def test_v2_unknown_stage_name_rejected():
    """SV2-E: stage_order with unknown stage name raises ValueError."""
    ctx = _make_v2_context_data()
    data = _make_v2_state_dict(context=ctx)
    data["stage_order"] = ["prepare", "chunk", "mystery_stage"]
    data["stages"] = {
        "prepare": {
            "status": "pending",
            "retry_count": 0,
            "max_retries": 3,
            "error_msg": "",
            "result": {},
            "duration_sec": 0.0,
        },
        "chunk": {
            "status": "pending",
            "retry_count": 0,
            "max_retries": 3,
            "error_msg": "",
            "result": {},
            "duration_sec": 0.0,
        },
        "mystery_stage": {
            "status": "pending",
            "retry_count": 0,
            "max_retries": 3,
            "error_msg": "",
            "result": {},
            "duration_sec": 0.0,
        },
    }

    with pytest.raises(ValueError, match="unknown stages"):
        PipelineState.from_dict(data)


def test_v2_missing_non_safety_context_field_rejected():
    """SV2-F: context missing a non-safety field (fmt) raises ValueError."""
    ctx = _make_v2_context_data()
    del ctx["fmt"]
    data = _make_v2_state_dict(context=ctx)

    with pytest.raises(ValueError, match="missing required fields.*fmt"):
        PipelineState.from_dict(data)


def test_v2_extra_context_field_rejected():
    """SV2-G: context with unknown extra field raises ValueError."""
    ctx = _make_v2_context_data(future_magic=True)
    data = _make_v2_state_dict(context=ctx)

    with pytest.raises(ValueError, match="unknown fields.*future_magic"):
        PipelineState.from_dict(data)


def test_v2_valid_roundtrip_preserves_all_fields():
    """SV2-H: valid v2 roundtrip preserves all PipelineRunContext fields."""
    from subtap.engine.state import PipelineRunContext

    ctx = PipelineRunContext(
        input_path="/media/input.mp3",
        output_dir="/out",
        fmt="vtt",
        enhance="api",
        translate_to="en",
        bilingual="source-first",
        script_path="/script.txt",
        script_mode="follow_script",
        subtitle_language="en",
        subtitle_punctuation=True,
        max_chars=30,
        glossary_path="/glossary.yaml",
        llm_proofread=True,
        llm_hotword=True,
        asr_backend="mlx-qwen-asr",
        asr_model="asr_1.7b",
        asr_hotwords="hello,world",
        subtitle_stem="custom",
        policy_mode="fast",
        local_only=True,
    )
    state = PipelineState.new(["prepare", "chunk", "asr"], context=ctx)
    data = state.to_dict()

    loaded = PipelineState.from_dict(data)
    assert loaded.context is not None
    assert loaded.context.input_path == "/media/input.mp3"
    assert loaded.context.fmt == "vtt"
    assert loaded.context.enhance == "api"
    assert loaded.context.translate_to == "en"
    assert loaded.context.bilingual == "source-first"
    assert loaded.context.script_path == "/script.txt"
    assert loaded.context.subtitle_punctuation is True
    assert loaded.context.max_chars == 30
    assert loaded.context.glossary_path == "/glossary.yaml"
    assert loaded.context.llm_proofread is True
    assert loaded.context.llm_hotword is True
    assert loaded.context.asr_backend == "mlx-qwen-asr"
    assert loaded.context.asr_model == "asr_1.7b"
    assert loaded.context.asr_hotwords == "hello,world"
    assert loaded.context.subtitle_stem == "custom"
    assert loaded.context.policy_mode == "fast"
    assert loaded.context.local_only is True


def test_v1_remains_supported():
    """SV2-I: v1 state format still loads correctly."""
    data = {
        "version": 1,
        "stages": {
            "prepare": {
                "status": "success",
                "retry_count": 0,
                "max_retries": 3,
                "error_msg": "",
                "result": {},
                "duration_sec": 1.0,
            },
            "chunk": {
                "status": "success",
                "retry_count": 0,
                "max_retries": 3,
                "error_msg": "",
                "result": {},
                "duration_sec": 2.0,
            },
            "asr": {
                "status": "pending",
                "retry_count": 0,
                "max_retries": 3,
                "error_msg": "",
                "result": {},
                "duration_sec": 0.0,
            },
            "clean": {
                "status": "pending",
                "retry_count": 0,
                "max_retries": 3,
                "error_msg": "",
                "result": {},
                "duration_sec": 0.0,
            },
            "segment": {
                "status": "pending",
                "retry_count": 0,
                "max_retries": 3,
                "error_msg": "",
                "result": {},
                "duration_sec": 0.0,
            },
            "align": {
                "status": "pending",
                "retry_count": 0,
                "max_retries": 3,
                "error_msg": "",
                "result": {},
                "duration_sec": 0.0,
            },
            "export": {
                "status": "pending",
                "retry_count": 0,
                "max_retries": 3,
                "error_msg": "",
                "result": {},
                "duration_sec": 0.0,
            },
        },
    }
    state = PipelineState.from_dict(data)
    assert state.context is None
    assert state.stage_order == [
        "prepare",
        "chunk",
        "asr",
        "clean",
        "segment",
        "align",
        "export",
    ]
    assert state.stages["prepare"].status.value == "success"


def test_v2_invalid_preserves_file_bytes(tmp_path: Path):
    """SV2-J: loading structurally-invalid v2 state does not modify file."""
    ctx = _make_v2_context_data()
    del ctx["fmt"]  # missing required field
    data = _make_v2_state_dict(context=ctx)

    state_file = tmp_path / "pipeline-state.json"
    import json

    state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    original_content = state_file.read_text(encoding="utf-8")

    with pytest.raises(ValueError):
        PipelineState.load(state_file)

    assert state_file.read_text(encoding="utf-8") == original_content
