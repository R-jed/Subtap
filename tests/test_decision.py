"""Tests for the decision engine."""

from subtap.engine.decision import PipelineDecision, PipelineMode


class TestPipelineMode:
    """Test PipelineMode enum."""

    def test_no_hybrid_mode(self):
        """HYBRID mode should not exist."""
        assert not hasattr(PipelineMode, "HYBRID")

    def test_only_fast_and_quality(self):
        """Only FAST and QUALITY modes should exist."""
        assert set(PipelineMode) == {PipelineMode.FAST, PipelineMode.QUALITY}


class TestPipelineDecision:
    """Test PipelineDecision creation and routing."""

    def test_fast_mode_uses_small_model(self):
        """Fast mode should use asr_0.6b model."""
        decision = PipelineDecision.from_mode("fast")
        assert decision.asr_model == "asr_0.6b"

    def test_quality_mode_uses_large_model(self):
        """Quality mode should use asr_1.7b model."""
        decision = PipelineDecision.from_mode("quality")
        assert decision.asr_model == "asr_1.7b"

    def test_fast_mode_config(self):
        """Fast mode should have correct configuration."""
        decision = PipelineDecision.from_mode("fast")
        assert decision.mode == PipelineMode.FAST
        assert decision.asr_model == "asr_0.6b"
        assert decision.use_llm is False
        assert decision.skip_clean is False
        assert decision.skip_align is False
        assert decision.use_spacy is True
        assert decision.use_fuzzy_match is False

    def test_quality_mode_config(self):
        """Quality mode should have correct configuration."""
        decision = PipelineDecision.from_mode("quality")
        assert decision.mode == PipelineMode.QUALITY
        assert decision.asr_model == "asr_1.7b"
        assert decision.use_llm is True
        assert decision.skip_clean is False
        assert decision.skip_align is False
        assert decision.use_spacy is True
        assert decision.use_fuzzy_match is True

    def test_all_modes_run_clean(self):
        """All modes should run clean stage (skip_clean=False)."""
        for mode in ("fast", "quality"):
            decision = PipelineDecision.from_mode(mode)
            assert decision.should_run_clean() is True, f"{mode} should run clean"

    def test_all_modes_run_align(self):
        """All modes should run align stage (skip_align=False)."""
        for mode in ("fast", "quality"):
            decision = PipelineDecision.from_mode(mode)
            assert decision.should_run_align() is True, f"{mode} should run align"

    def test_no_hybrid_mode(self):
        """HYBRID should not be a valid mode."""
        assert "hybrid" not in [m.value for m in PipelineMode]

    def test_invalid_mode_defaults_to_fast(self):
        """Invalid mode string should default to FAST."""
        decision = PipelineDecision.from_mode("invalid")
        assert decision.mode == PipelineMode.FAST
        assert decision.asr_model == "asr_0.6b"
        assert decision.skip_clean is False
        assert decision.skip_align is False
        assert decision.use_spacy is True

    def test_should_use_llm_fast(self):
        """Fast mode should not use LLM."""
        decision = PipelineDecision.from_mode("fast")
        assert decision.should_use_llm() is False

    def test_should_use_llm_quality(self):
        """Quality mode should use LLM."""
        decision = PipelineDecision.from_mode("quality")
        assert decision.should_use_llm() is True

    def test_should_use_spacy_all_modes(self):
        """All modes should use spaCy."""
        for mode in ("fast", "quality"):
            decision = PipelineDecision.from_mode(mode)
            assert decision.should_use_spacy() is True, f"{mode} should use spacy"

    def test_should_use_fuzzy_match_fast(self):
        """Fast mode should not use fuzzy matching."""
        decision = PipelineDecision.from_mode("fast")
        assert decision.should_use_fuzzy_match() is False

    def test_should_use_fuzzy_match_quality(self):
        """Quality mode should use fuzzy matching."""
        decision = PipelineDecision.from_mode("quality")
        assert decision.should_use_fuzzy_match() is True
