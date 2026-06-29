"""Phase 19: 验证产品边界 — 不包含第三方 ASR API。"""

from __future__ import annotations

import re

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text for reliable string matching."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_cli_help_no_api_asr():
    """CLI help 不应出现 API ASR 相关选项。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output).lower()
    # 不应出现第三方 ASR 选项
    assert "--asr" not in help_text or "api" not in help_text
    assert "deepgram" not in help_text
    assert "assemblyai" not in help_text
    assert "openai" not in help_text or "asr" not in help_text


def test_cli_help_no_hybrid():
    """CLI help 中 hybrid 只应出现在 hotword-mode 选项中。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output).lower()
    # hybrid 只在 hotword-mode 选项中出现
    assert "hybrid" not in help_text or "hotword" in help_text


def test_cli_help_no_custom_url_asr():
    """CLI help 不应出现自定义 ASR URL 选项。"""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    help_text = _strip_ansi(result.output).lower()
    assert "--asr-url" not in help_text
    assert "--custom-asr" not in help_text


def test_decision_no_third_party_asr():
    """PipelineDecision 不应包含第三方 ASR 相关字段。"""
    from subtap.engine.decision import PipelineDecision

    decision = PipelineDecision.from_mode("fast")
    # 不应有 provider 字段指向第三方
    assert not hasattr(decision, "asr_provider") or getattr(
        decision, "asr_provider", None
    ) in (None, "qwen3_mlx")


def test_config_no_api_asr_backend():
    """Config 不应包含 API ASR 后端选项。"""
    from subtap.schemas.config import ASRConfig

    config = ASRConfig()
    # 默认后端应是本地 MLX
    assert config.backend == "mlx-qwen-asr"
