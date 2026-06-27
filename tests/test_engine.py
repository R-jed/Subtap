"""Tests for engine: state machine, policy, controller, events."""

from __future__ import annotations

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
    """LOCAL_ONLY policy: no LLM, align enabled."""
    p = ExecutionPolicy("local")
    assert p.use_llm is False
    assert p.align_enabled is True
    assert p.should_skip("clean") is False


def test_policy_hybrid():
    """HYBRID policy: LLM enabled, 1.7B model."""
    p = ExecutionPolicy("hybrid")
    assert p.use_llm is True
    assert p.asr_model == "asr_1.7b"


def test_policy_fast():
    """FAST_MODE policy: skips clean and align."""
    p = ExecutionPolicy("fast")
    assert p.should_skip("clean") is True
    assert p.should_skip("align") is True
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
    """Fast policy skips clean and align in run_pipeline."""
    from subtap.engine.controller import PipelineController

    config = SubtapConfig()
    ctrl = PipelineController(config, tmp_path / "work", policy="fast")

    assert ctrl.policy.should_skip("clean") is True
    assert ctrl.policy.should_skip("align") is True
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


def test_cli_run_with_policy_flag(tmp_path: Path, monkeypatch):
    """CLI run command accepts --policy flag."""
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
            "--no-tui",
            "--policy",
            "fast",
        ],
    )
    # Should accept --policy without error (may fail on actual audio processing)
    assert "--policy" not in result.output or result.exit_code in (0, 1)


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
