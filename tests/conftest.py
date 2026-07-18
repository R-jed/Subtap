"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from subtap.schemas.config import SubtapConfig, VADConfig, AudioConfig, WorkspaceConfig


def pytest_configure(config):
    """Configure asyncio mode for all async tests."""
    config._inicache["asyncio_mode"] = "auto"


@pytest.fixture
def sample_wav(tmp_path: Path) -> Path:
    """Create a synthetic WAV file with speech-like segments and silence."""
    # 0.5s tone, 0.6s silence, 0.5s tone (should produce 2+ chunks)
    tone1 = Sine(440).to_audio_segment(duration=500)
    silence = AudioSegment.silent(duration=600)
    tone2 = Sine(880).to_audio_segment(duration=500)

    audio = tone1 + silence + tone2
    audio = audio.set_frame_rate(16000).set_channels(1)

    wav_path = tmp_path / "test.wav"
    audio.export(str(wav_path), format="wav")
    return wav_path


@pytest.fixture
def test_config(tmp_path: Path) -> SubtapConfig:
    """Config pointing to a temporary workspace."""
    return SubtapConfig(
        audio=AudioConfig(
            sample_rate=16000,
            channels=1,
            format="wav",
            vad=VADConfig(
                use_silero_vad=False,
                min_silence_sec=0.4,
            ),
        ),
        workspace=WorkspaceConfig(
            root=str(tmp_path / "work"),
            keep_intermediate=True,
        ),
    )


@pytest.fixture
def local_config(tmp_path: Path) -> SubtapConfig:
    """纯本地配置，禁用所有 LLM 功能"""
    return SubtapConfig(
        llm_proofread=False,
        llm_hotword=False,
        translate_to="",
        workspace=WorkspaceConfig(
            root=str(tmp_path / "work"),
            keep_intermediate=True,
        ),
        asr={"backend": "mock-asr"},
        align={"backend": "mock-align"},
    )


@pytest.fixture
def skip_runtime_model_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep pipeline-focused tests independent from installed local models."""
    monkeypatch.setattr(
        "subtap.core.models.validate_runtime_models", lambda _config: None
    )


@pytest.fixture
def workspace(local_config: SubtapConfig):
    """创建工作空间"""
    from subtap.core.workspace import Workspace

    ws = Workspace(local_config)
    ws.ensure_dirs()
    return ws


@pytest.fixture
def sample_audio() -> Path:
    """使用真实测试素材（本地开发环境）"""
    path = Path("/Users/qunqing/Downloads/ASR-SRT测试音频/高质量中文语音.mp3")
    if not path.exists():
        pytest.skip("本地测试素材不存在，跳过集成测试")
    return path
