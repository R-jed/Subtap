"""Authoritative external-processing policy for Subtap.

Single source of truth for every path that can send audio or subtitle text
outside the local machine.  All CLI, TUI, batch, resume, retry, and observer
paths consume this policy object rather than duplicating logic.

Policy precedence (highest first):
  1. local_only=True — denies every remote feature regardless of other flags
  2. enhance=off     — denies clean-stage LLM features (proofread, hotword)
  3. enhance=local   — denies clean-stage LLM features
  4. enhance=api     — permits clean-stage LLM features per resolved booleans
  5. remote_asr      — evaluated separately, subject to local_only + disclosure
  6. translation     — evaluated separately, subject to local_only + disclosure
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional


class EnhanceMode(enum.StrEnum):
    """Typed enhance mode replacing loosely validated strings."""

    OFF = "off"
    LOCAL = "local"
    API = "api"


class ExternalDataKind(enum.StrEnum):
    """What kind of user data leaves the local machine."""

    AUDIO = "audio"
    SUBTITLE_TEXT = "subtitle_text"


# ── public contract values ────────────────────────────────────

_ALL_ENHANCE_MODES: set[str] = {m.value for m in EnhanceMode}

_REMOTE_ASR_BACKENDS: set[str] = {"http-asr"}


def is_remote_asr_backend(backend: str) -> bool:
    """Return whether *backend* transmits audio externally."""
    return backend in _REMOTE_ASR_BACKENDS


def parse_enhance_mode(value: Optional[str]) -> EnhanceMode:
    """Parse and validate an enhance-mode string.

    Raises ``ValueError`` for unknown values so callers fail early
    rather than silently defaulting.
    """
    if value is None:
        return EnhanceMode.LOCAL
    try:
        return EnhanceMode(value)
    except ValueError:
        raise ValueError(
            f"--enhance 必须是 {'/'.join(_ALL_ENHANCE_MODES)}" f"，收到：{value!r}"
        )


@dataclass(frozen=True)
class ExternalProcessingPolicy:
    """Immutable policy governing all external-processing decisions.

    Every field represents a resolved boolean — the result of evaluating
    local_only, enhance_mode, independent feature flags, and backend
    selection against each other at the policy boundary.  Downstream code
    reads these booleans; it never re-resolves string-based flags.

    Truth table (simplified; see architecture docs for full matrix):

    local_only  enhance   remote_asr  proofread  hotword  translation
    ─────────────────────────────────────────────────────────────────
    False       off       False       False      False    False
    False       local     False       False      False    False
    False       api       varies*     bool       bool     bool
    True        *         Denied      Denied     Denied   Denied

    * remote_asr is True when local_only is False AND the selected ASR
      backend is a remote backend (e.g. ``http-asr``).
    """

    local_only: bool
    enhance_mode: EnhanceMode
    remote_asr: bool
    llm_proofread: bool
    llm_hotword: bool
    translation: bool

    # ── derived properties ────────────────────────────────────

    @property
    def sends_audio(self) -> bool:
        """Any external service receives raw audio data."""
        return self.remote_asr

    @property
    def sends_text(self) -> bool:
        """Any external service receives subtitle text."""
        return self.llm_proofread or self.llm_hotword or self.translation

    @property
    def sends_external_data(self) -> bool:
        return self.sends_audio or self.sends_text

    # ── enforcement methods ───────────────────────────────────

    def assert_remote_asr_allowed(self) -> None:
        """Raise if this policy forbids external ASR."""
        if self.local_only:
            _raise_local_only("远程 ASR")
        if not self.remote_asr:
            raise ExternalProcessingError("ASR 后端为本地模式，禁止使用远程 ASR")

    def assert_clean_llm_allowed(self) -> None:
        """Raise if this policy forbids clean-stage LLM backends."""
        if self.local_only:
            _raise_local_only("远程 AI 校对/热词替换")
        if not self.llm_proofread and not self.llm_hotword:
            raise ExternalProcessingError("当前增强模式不支持远程 AI 校对/热词替换")

    def assert_translation_allowed(self) -> None:
        """Raise if this policy forbids remote translation."""
        if self.local_only:
            _raise_local_only("翻译")
        if not self.translation:
            raise ExternalProcessingError("当前配置禁止翻译")

    # ── disclosure text ──────────────────────────────────────

    def disclosure_lines(self) -> list[str]:
        """Return user-facing disclosure lines for this policy.

        Returns an empty list when no external processing is active.
        """
        lines: list[str] = []
        if self.remote_asr:
            lines.append("⚠ 音频将发送至外部 ASR 服务进行识别。")
        if self.sends_text:
            lines.append("⚠ 字幕文本将发送至外部 LLM 服务进行处理。")
        return lines


# ── policy builder ────────────────────────────────────────────


def build_policy(
    *,
    local_only: bool,
    enhance_mode: Optional[str],
    asr_backend: str = "mlx-qwen-asr",
    llm_proofread: Optional[bool] = None,
    llm_hotword: Optional[bool] = None,
    translation: bool = False,
) -> ExternalProcessingPolicy:
    """Resolve every policy field from its inputs.

    All callers (CLI, batch, TUI, resume) converge on this function so
    that policy resolution is never duplicated.
    """
    mode = parse_enhance_mode(enhance_mode)

    # Remote ASR
    remote_asr = (not local_only) and is_remote_asr_backend(asr_backend)

    # LLM proofread/hotword — only when api mode permits
    if local_only or mode in (EnhanceMode.OFF, EnhanceMode.LOCAL):
        resolved_proofread = False
        resolved_hotword = False
    else:  # mode == api
        resolved_proofread = True if llm_proofread is None else llm_proofread
        resolved_hotword = True if llm_hotword is None else llm_hotword

    # Translation
    resolved_translation = (not local_only) and translation

    return ExternalProcessingPolicy(
        local_only=local_only,
        enhance_mode=mode,
        remote_asr=remote_asr,
        llm_proofread=resolved_proofread,
        llm_hotword=resolved_hotword,
        translation=resolved_translation,
    )


# ── errors ────────────────────────────────────────────────────


class ExternalProcessingError(RuntimeError):
    """An invalid or denied external-processing combination was requested."""

    pass


class MissingExternalProcessingPolicyError(RuntimeError):
    """An external-capable stage was invoked without an authoritative policy.

    Signals an internal programming or orchestration defect — the caller
    must construct and propagate an ExternalProcessingPolicy before execution.
    """


def _raise_local_only(feature: str) -> None:
    raise ExternalProcessingError(f"--local-only 模式禁止使用 {feature}")
