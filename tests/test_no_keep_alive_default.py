"""Phase 22: no keep-alive or warm-up by default."""

from __future__ import annotations

from subtap.schemas.config import SubtapConfig


def test_models_do_not_keep_alive_or_warmup_by_default():
    """Default runtime must not keep models resident or warm them up."""
    config = SubtapConfig()

    assert config.asr.keep_model_alive is False
    assert config.asr.warmup is False
    assert config.align.keep_model_alive is False
    assert config.align.warmup is False
