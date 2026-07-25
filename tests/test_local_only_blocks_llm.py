"""Phase 19: 验证 --local-only 阻止 LLM API 调用。"""

from __future__ import annotations

import re
from types import SimpleNamespace

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text for reliable string matching."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_local_only_blocks_enhance_api(tmp_path):
    """--local-only 模式下不能使用 --enhance api。"""
    input_file = tmp_path / "test.mp3"
    input_file.write_bytes(b"fake audio")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--local-only", "--enhance", "api"],
    )
    assert result.exit_code == 1
    assert "local-only" in _strip_ansi(result.output).lower() or "错误" in _strip_ansi(
        result.output
    )


def test_local_only_blocks_remote_asr_backend(tmp_path, monkeypatch):
    """--local-only 模式下不能使用会外发音频的 ASR 后端。"""
    input_file = tmp_path / "test.mp3"
    input_file.write_bytes(b"fake audio")
    home = tmp_path / "home"
    (home / ".subtap").mkdir(parents=True)
    (home / ".subtap" / "config.yaml").write_text(
        "asr:\n  backend: http-asr\n", encoding="utf-8"
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    result = runner.invoke(app, ["run", str(input_file), "--local-only"])
    output = _strip_ansi(result.output)

    assert result.exit_code == 1
    assert "http-asr" in output
    assert "local-only" in output


def test_local_only_allows_enhance_local(tmp_path, monkeypatch):
    """--local-only 模式下可以使用 --enhance local。"""
    input_file = tmp_path / "test.mp3"
    input_file.write_bytes(b"fake audio")

    # Mock 配置加载
    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda p: SimpleNamespace(output=SimpleNamespace(timestamp=True)),
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--local-only", "--enhance", "local"],
    )
    output = _strip_ansi(result.output)
    assert "local-only 模式下不能使用" not in output


def test_enhance_api_shows_warning(tmp_path, monkeypatch):
    """--enhance api 应显示外部 API 警告。"""
    input_file = tmp_path / "test.mp3"
    input_file.write_bytes(b"fake audio")

    # Mock 配置加载
    monkeypatch.setattr(
        "subtap.schemas.config.load_config",
        lambda p: SimpleNamespace(output=SimpleNamespace(timestamp=True)),
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    result = runner.invoke(
        app,
        ["run", str(input_file), "--enhance", "api"],
    )
    output = _strip_ansi(result.output)
    # 应提示字幕文本将发送到外部
    assert "外部" in output or "API" in output


def test_default_enhance_is_local():
    """默认增强模式应为 local。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output)
    # 检查 --enhance 的默认值
    assert "local" in help_text


def test_enhance_accepts_local_api():
    """--enhance 应接受 local/api 两个值。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output)
    assert "local" in help_text
    assert "api" in help_text


# ── Local-only security boundary: LLM enforcement ──


def test_local_only_forces_llm_off_in_config(tmp_path):
    """local_only=True should force llm_proofread=False, llm_hotword=False."""
    from subtap.schemas.config import SubtapConfig
    from subtap.engine.controller import PipelineController
    from subtap.engine.state import PipelineRunContext

    config = SubtapConfig()
    config.llm_proofread = True
    config.llm_hotword = True

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    ctx = PipelineRunContext(
        input_path=str(tmp_path / "test.mp3"),
        output_dir=str(tmp_path / "out"),
        local_only=True,
        llm_proofread=True,
        llm_hotword=True,
    )

    ctrl = PipelineController(config, work_dir)
    ctrl.set_context(ctx)

    assert config.llm_proofread is False
    assert config.llm_hotword is False


def test_local_only_persists_in_context(tmp_path):
    """local_only flag survives serialization roundtrip."""
    from subtap.engine.state import PipelineRunContext

    ctx = PipelineRunContext(
        input_path="/tmp/test.mp3",
        output_dir="/tmp/out",
        local_only=True,
    )

    data = ctx.to_dict()
    assert data["local_only"] is True

    restored = PipelineRunContext.from_dict(data)
    assert restored.local_only is True


def test_local_only_normal_run_persists_flag(tmp_path):
    """Normal run with --local-only persists local_only=True in state."""
    from subtap.schemas.config import SubtapConfig
    from subtap.engine.state import PipelineState, PipelineRunContext

    config = SubtapConfig()
    config.llm_proofread = True
    config.llm_hotword = True

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    ctx = PipelineRunContext(
        input_path=str(tmp_path / "test.mp3"),
        output_dir=str(tmp_path / "out"),
        local_only=True,
        llm_proofread=False,
        llm_hotword=False,
    )

    state = PipelineState.new(
        stage_order=["prepare", "chunk", "asr", "clean", "segment", "align", "export"],
        context=ctx,
    )
    state.mark_success("prepare", {}, 0.1)
    state.mark_success("chunk", {}, 0.1)
    state.mark_success("asr", {}, 0.1)
    state.save(work_dir / "pipeline-state.json")

    # Load and verify
    loaded = PipelineState.load(work_dir / "pipeline-state.json")
    assert loaded.context.local_only is True


def test_local_only_resume_restores_security_boundary(tmp_path):
    """Resume from local_only run should enforce LLM=off even if config has LLM on."""
    from subtap.schemas.config import SubtapConfig
    from subtap.engine.controller import PipelineController
    from subtap.engine.state import PipelineState, PipelineRunContext

    config = SubtapConfig()
    config.llm_proofread = True  # Current config has LLM on
    config.llm_hotword = True

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Persist state from a local_only run
    ctx = PipelineRunContext(
        input_path=str(tmp_path / "test.mp3"),
        output_dir=str(tmp_path / "out"),
        local_only=True,
        llm_proofread=False,
        llm_hotword=False,
    )
    state = PipelineState.new(
        stage_order=["prepare", "chunk", "asr", "clean", "segment", "align", "export"],
        context=ctx,
    )
    state.mark_success("prepare", {}, 0.1)
    state.mark_success("chunk", {}, 0.1)
    state.mark_success("asr", {}, 0.1)
    state.mark_failed("clean", "test error")
    state.save(work_dir / "pipeline-state.json")

    # Resume with new controller
    ctrl = PipelineController(config, work_dir)
    ctrl.load_state()

    # After loading state, LLM should be forced off
    assert config.llm_proofread is False
    assert config.llm_hotword is False


def test_local_only_retry_restores_security_boundary(tmp_path):
    """Retry from local_only run should enforce LLM=off."""
    from subtap.schemas.config import SubtapConfig
    from subtap.engine.controller import PipelineController
    from subtap.engine.state import PipelineState, PipelineRunContext

    config = SubtapConfig()
    config.llm_proofread = True
    config.llm_hotword = True

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    ctx = PipelineRunContext(
        input_path=str(tmp_path / "test.mp3"),
        output_dir=str(tmp_path / "out"),
        local_only=True,
        llm_proofread=False,
        llm_hotword=False,
    )
    state = PipelineState.new(
        stage_order=["prepare", "chunk", "asr", "clean", "segment", "align", "export"],
        context=ctx,
    )
    state.mark_success("prepare", {}, 0.1)
    state.mark_success("chunk", {}, 0.1)
    state.mark_success("asr", {}, 0.1)
    state.mark_failed("clean", "test error")
    state.save(work_dir / "pipeline-state.json")

    # Retry with new controller
    ctrl = PipelineController(config, work_dir)
    ctrl.load_state()

    # After loading state, LLM should be forced off
    assert config.llm_proofread is False
    assert config.llm_hotword is False
