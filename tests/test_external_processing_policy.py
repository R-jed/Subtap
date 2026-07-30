"""Tests for ExternalProcessingPolicy — the authoritative policy object."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from subtap.runtime.external_policy import (
    EnhanceMode,
    ExternalProcessingError,
    ExternalProcessingPolicy,
    build_policy,
    parse_enhance_mode,
    is_remote_asr_backend,
)


class TestParseEnhanceMode:
    def test_valid_modes(self) -> None:
        assert parse_enhance_mode("off") == EnhanceMode.OFF
        assert parse_enhance_mode("local") == EnhanceMode.LOCAL
        assert parse_enhance_mode("api") == EnhanceMode.API

    def test_none_defaults_to_local(self) -> None:
        assert parse_enhance_mode(None) == EnhanceMode.LOCAL

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="--enhance"):
            parse_enhance_mode("remote")


class TestIsRemoteAsrBackend:
    def test_http_asr_is_remote(self) -> None:
        assert is_remote_asr_backend("http-asr") is True

    def test_local_is_not_remote(self) -> None:
        assert is_remote_asr_backend("mlx-qwen-asr") is False

    def test_unknown_is_not_remote(self) -> None:
        assert is_remote_asr_backend("unknown") is False


class TestBuildPolicy:
    """Table-driven tests for the authoritative truth table."""

    @pytest.mark.parametrize(
        (
            "local_only",
            "enhance",
            "remote_asr",
            "in_proof",
            "in_hotword",
            "in_trans",
            "out_proof",
            "out_hotword",
            "out_trans",
        ),
        [
            # off/local: everything stays local regardless of flags
            (False, "off", False, None, None, False, False, False, False),
            (False, "local", False, None, None, False, False, False, False),
            (False, "off", False, True, True, False, False, False, False),
            # api: no explicit LLM flags → enable by default
            (False, "api", False, None, None, False, True, True, False),
            # api: explicit False → keep False
            (False, "api", False, True, None, False, True, True, False),
            (False, "api", False, True, False, False, True, False, False),
            (False, "api", False, False, True, False, False, True, False),
            # local + remote ASR backend
            (False, "local", True, None, None, False, False, False, False),
            (False, "off", True, None, None, False, False, False, False),
            # api + remote ASR + translation
            (False, "api", True, None, None, True, True, True, True),
            # local-only is a hard deny regardless of flags
            (True, "api", False, None, None, False, False, False, False),
            (True, "off", False, None, None, False, False, False, False),
            (True, "local", False, None, None, False, False, False, False),
            (True, "api", False, True, True, True, False, False, False),
            # local with remote ASR option
            (False, "local", True, None, None, True, False, False, True),
        ],
    )
    def test_policy_truth_table(
        self,
        local_only: bool,
        enhance: str,
        remote_asr: bool,
        in_proof: bool | None,
        in_hotword: bool | None,
        in_trans: bool,
        out_proof: bool,
        out_hotword: bool,
        out_trans: bool,
    ) -> None:
        """Verify the policy resolves correctly for each combination."""
        policy = build_policy(
            local_only=local_only,
            enhance_mode=enhance,
            asr_backend="http-asr" if remote_asr else "mlx-qwen-asr",
            llm_proofread=in_proof,
            llm_hotword=in_hotword,
            translation=in_trans,
        )
        assert policy.local_only == local_only
        assert policy.enhance_mode == EnhanceMode(enhance)
        assert policy.remote_asr == remote_asr
        assert policy.llm_proofread == out_proof
        assert policy.llm_hotword == out_hotword
        assert policy.translation == out_trans

    def test_api_with_remote_asr(self) -> None:
        """api mode + http-asr backend = both audio and text external."""
        policy = build_policy(
            local_only=False,
            enhance_mode="api",
            asr_backend="http-asr",
            translation=True,
        )
        assert policy.sends_audio
        assert policy.sends_text
        assert policy.sends_external_data

    def test_local_only_rejects_api(self) -> None:
        """local-only + api = no remote features."""
        policy = build_policy(
            local_only=True,
            enhance_mode="api",
            asr_backend="http-asr",
            llm_proofread=True,
            llm_hotword=True,
            translation=True,
        )
        assert not policy.remote_asr
        assert not policy.llm_proofread
        assert not policy.llm_hotword
        assert not policy.translation

    def test_local_off_with_explicit_llm_flags_stays_local(self) -> None:
        """--enhance local + --llm-proofread must not enable remote."""
        policy = build_policy(
            local_only=False,
            enhance_mode="local",
            llm_proofread=True,
            llm_hotword=True,
        )
        assert not policy.llm_proofread
        assert not policy.llm_hotword

    def test_disclosure_off_local(self) -> None:
        """off/local produces no disclosure lines."""
        for mode in ("off", "local"):
            policy = build_policy(local_only=False, enhance_mode=mode)
            assert policy.disclosure_lines() == []

    def test_disclosure_api(self) -> None:
        """api mode produces text disclosure."""
        policy = build_policy(local_only=False, enhance_mode="api")
        lines = policy.disclosure_lines()
        assert len(lines) == 1
        assert "字幕文本" in lines[0]

    def test_disclosure_remote_asr(self) -> None:
        """http-asr backend produces audio disclosure."""
        policy = build_policy(
            local_only=False,
            enhance_mode="local",
            asr_backend="http-asr",
        )
        lines = policy.disclosure_lines()
        assert len(lines) == 1
        assert "音频" in lines[0]

    def test_disclosure_remote_asr_and_api(self) -> None:
        """Both audio and text disclosures when both active."""
        policy = build_policy(
            local_only=False,
            enhance_mode="api",
            asr_backend="http-asr",
            translation=True,
        )
        lines = policy.disclosure_lines()
        assert len(lines) == 2


class TestPolicyEnforcement:
    def test_assert_remote_asr_allowed_local_only(self) -> None:
        policy = build_policy(local_only=True, enhance_mode="local")
        with pytest.raises(ExternalProcessingError, match="local-only"):
            policy.assert_remote_asr_allowed()

    def test_assert_remote_asr_allowed_denied(self) -> None:
        policy = build_policy(local_only=False, enhance_mode="local")
        with pytest.raises(ExternalProcessingError, match="远程 ASR"):
            policy.assert_remote_asr_allowed()

    def test_assert_remote_asr_allowed_ok(self) -> None:
        policy = build_policy(
            local_only=False,
            enhance_mode="local",
            asr_backend="http-asr",
        )
        # Should not raise
        policy.assert_remote_asr_allowed()

    def test_assert_clean_llm_allowed_off(self) -> None:
        policy = build_policy(local_only=False, enhance_mode="off")
        with pytest.raises(ExternalProcessingError):
            policy.assert_clean_llm_allowed()

    def test_assert_clean_llm_allowed_local(self) -> None:
        policy = build_policy(local_only=False, enhance_mode="local")
        with pytest.raises(ExternalProcessingError):
            policy.assert_clean_llm_allowed()

    def test_assert_clean_llm_allowed_local_only(self) -> None:
        policy = build_policy(local_only=True, enhance_mode="api")
        with pytest.raises(ExternalProcessingError, match="local-only"):
            policy.assert_clean_llm_allowed()

    def test_assert_clean_llm_allowed_api(self) -> None:
        policy = build_policy(local_only=False, enhance_mode="api")
        # Should not raise
        policy.assert_clean_llm_allowed()

    def test_assert_translation_allowed_local_only(self) -> None:
        policy = build_policy(local_only=True, enhance_mode="local", translation=True)
        with pytest.raises(ExternalProcessingError, match="local-only"):
            policy.assert_translation_allowed()

    def test_assert_translation_allowed_ok(self) -> None:
        policy = build_policy(local_only=False, enhance_mode="local", translation=True)
        # Should not raise
        policy.assert_translation_allowed()

    def test_assert_translation_allowed_not_requested(self) -> None:
        policy = build_policy(local_only=False, enhance_mode="local")
        with pytest.raises(ExternalProcessingError, match="禁止翻译"):
            policy.assert_translation_allowed()
