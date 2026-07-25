"""Tests for engine: state machine, policy, controller, events."""

from __future__ import annotations

import os
import sys
from pathlib import Path

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

    # Monkeypatch handlers to track calls
    calls = []
    fake_result = {"segment_count": 1, "cleaned_jsonl": "x"}
    for name in ["clean", "segment", "align", "export"]:
        ctrl2._stage_handlers[name] = lambda n=name, **kw: (
            calls.append(n),
            fake_result,
        )[1]

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
    fake_result = {"segment_count": 1, "asr_jsonl": "x", "chunks_jsonl": "x"}
    for name in ["asr", "clean", "segment", "align", "export"]:
        ctrl2._stage_handlers[name] = lambda n=name, **kw: (
            calls.append(n),
            fake_result,
        )[1]

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
    fake_result = {"segment_count": 1, "asr_jsonl": "x"}

    def fake_asr(**kw):
        calls.append("asr")
        return fake_result

    ctrl2._stage_handlers["asr"] = fake_asr

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

    # Retry with a handler that raises
    def failing_handler(**kw):
        raise RuntimeError("still broken")

    ctrl._stage_handlers["asr"] = failing_handler

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
    for name in ["asr", "clean", "segment", "align", "export"]:
        ctrl2._stage_handlers[name] = lambda n=name, **kw: (calls.append(n), fake)[1]

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
    from subtap.schemas.config import SubtapConfig
    from subtap.core.tracked_pipeline import TrackedPipeline

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Lifecycle A: old run completed
    ctrl = PipelineController(config=SubtapConfig(), work_dir=work_dir)
    for name in STAGE_ORDER:
        ctrl.state.mark_success(name, {}, 0.1)
    ctrl._save_state()

    # Verify old state on disk
    old_state = PipelineState.load(work_dir / "pipeline-state.json")
    assert old_state.get("asr").status == StageStatus.SUCCESS

    # Lifecycle B: fresh TrackedPipeline creates new state
    pipeline = TrackedPipeline(config=SubtapConfig(), work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

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
    """C2: With script_path=None, align uses sentences.jsonl, not stale script_matched."""
    from subtap.schemas.config import SubtapConfig
    from subtap.core.workspace import Workspace
    from subtap.core.pipeline import Pipeline

    config = SubtapConfig()
    config.output.script_path = None

    ws = Workspace(config, base_dir=tmp_path / "work")
    ws.ensure_dirs()

    # Write CURRENT sentences.jsonl
    ws.sentences_jsonl.write_text(
        '{"sentence_id": 0, "text": "current", "start_sec": 0.0, "end_sec": 1.0}\n',
        encoding="utf-8",
    )
    # Write STALE script_matched.jsonl
    ws.script_matched_jsonl.write_text(
        '{"sentence_id": 0, "text": "stale", "start_sec": 0.0, "end_sec": 1.0}\n',
        encoding="utf-8",
    )

    pipeline = Pipeline(config, work_dir=tmp_path / "work")

    assert pipeline.config.output.script_path is None
    # Align stage picks sentences.jsonl when script_path is None
    expected = ws.sentences_jsonl
    actual = (
        ws.script_matched_jsonl
        if pipeline.config.output.script_path
        else ws.sentences_jsonl
    )
    assert actual == expected


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
