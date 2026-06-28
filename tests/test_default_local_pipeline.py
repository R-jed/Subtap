"""Phase 19: 验证默认 pipeline 走本地路径。"""

from __future__ import annotations

from subtap.engine.decision import PipelineDecision, PipelineMode


def test_default_mode_is_fast():
    """默认模式应为 fast。"""
    decision = PipelineDecision.from_mode("fast")
    assert decision.mode == PipelineMode.FAST


def test_fast_mode_uses_local_asr():
    """fast 模式应使用本地 ASR 模型。"""
    decision = PipelineDecision.from_mode("fast")
    assert decision.asr_model == "asr_0.6b"


def test_quality_mode_uses_local_asr():
    """quality 模式应使用本地 ASR 模型。"""
    decision = PipelineDecision.from_mode("quality")
    assert decision.asr_model == "asr_1.7b"


def test_fast_mode_no_llm():
    """fast 模式不应使用 LLM。"""
    decision = PipelineDecision.from_mode("fast")
    assert decision.should_use_llm() is False


def test_all_modes_run_clean():
    """所有模式都应运行 clean 阶段。"""
    for mode in ("fast", "quality"):
        decision = PipelineDecision.from_mode(mode)
        assert decision.should_run_clean() is True


def test_all_modes_run_align():
    """所有模式都应运行 align 阶段。"""
    for mode in ("fast", "quality"):
        decision = PipelineDecision.from_mode(mode)
        assert decision.should_run_align() is True


def test_decision_has_no_external_api_flag():
    """PipelineDecision 不应有 external_api 标志。"""
    decision = PipelineDecision.from_mode("fast")
    # 不应有调用外部 API 的标志
    assert not hasattr(decision, "use_external_api") or not getattr(
        decision, "use_external_api", False
    )


def test_config_default_asr_is_mlx():
    """默认 ASR 配置应为 MLX。"""
    from subtap.schemas.config import ASRConfig

    config = ASRConfig()
    assert "mlx" in config.backend


def test_config_default_align_is_mlx():
    """默认对齐配置应为 MLX。"""
    from subtap.schemas.config import AlignConfig

    config = AlignConfig()
    assert "mlx" in config.backend


def test_task_default_mode_is_fast():
    """Task 默认模式应为 fast。"""
    from pathlib import Path
    from subtap.task.task import Task

    task = Task(input_file=Path("test.mp3"))
    assert task.mode == "fast"


def test_task_default_policy_is_fast():
    """Task 默认策略应为 fast。"""
    from pathlib import Path
    from subtap.task.task import Task

    task = Task(input_file=Path("test.mp3"))
    assert task.to_policy_mode() == "fast"
