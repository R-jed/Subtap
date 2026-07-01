"""Phase 22: no keep-alive by default."""

from __future__ import annotations

from subtap.schemas.config import SubtapConfig


def test_models_do_not_keep_alive_by_default():
    """Default runtime must not keep models resident."""
    config = SubtapConfig()

    assert config.asr.keep_model_alive is False
    assert config.align.keep_model_alive is False
