import pytest
import numpy as np
import wave
from pathlib import Path

from subtap.schemas.config import VADConfig, SubtapConfig
from subtap.core.workspace import Workspace
from subtap.core.vad import split_chunks, VADError


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int = 16000) -> None:
    """Write int16 numpy array to a mono WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.astype(np.int16).tobytes())


def _make_speech_samples(duration_ms: int, sample_rate: int = 16000) -> np.ndarray:
    """Generate a sine-wave 'speech' signal as int16 samples."""
    t = np.linspace(
        0, duration_ms / 1000.0, int(sample_rate * duration_ms / 1000), endpoint=False
    )
    return (np.sin(2 * np.pi * 440 * t) * 30000).astype(np.int16)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def speech_with_pauses(tmp_path: Path) -> Path:
    """Generate a synthetic audio file: speech burst + silence + speech burst.

    Resulting WAV: ~4 seconds total, with two ~1.5s speech segments separated
    by a ~1s silence gap.
    """
    speech_a = _make_speech_samples(1500)
    silence = np.zeros(16000, dtype=np.int16)  # 1s silence
    speech_b = _make_speech_samples(1500)

    samples = np.concatenate([speech_a, silence, speech_b])
    path = tmp_path / "test_speech.wav"
    _write_wav(path, samples)
    return path


@pytest.fixture()
def single_burst(tmp_path: Path) -> Path:
    """Generate a short single speech burst (~0.8s)."""
    samples = _make_speech_samples(800)
    path = tmp_path / "single_burst.wav"
    _write_wav(path, samples)
    return path


# ---------------------------------------------------------------------------
# VADConfig tests
# ---------------------------------------------------------------------------


def test_vad_config_silero_field():
    """VADConfig should have use_silero_vad field with default True."""
    config = VADConfig()
    assert hasattr(config, "use_silero_vad")
    assert config.use_silero_vad is True


def test_vad_config_silero_false():
    """VADConfig should accept use_silero_vad=False."""
    config = VADConfig(use_silero_vad=False)
    assert config.use_silero_vad is False


def test_vad_config_default_threshold():
    """VADConfig should have silero_threshold default of 0.5."""
    config = VADConfig()
    assert config.silero_threshold == 0.5


def test_vad_config_custom_threshold():
    """VADConfig should accept custom silero_threshold."""
    config = VADConfig(silero_threshold=0.7)
    assert config.silero_threshold == 0.7


def test_vad_config_default_min_speech():
    """VADConfig should have silero_min_speech_duration_ms default of 250."""
    config = VADConfig()
    assert config.silero_min_speech_duration_ms == 250


def test_vad_config_custom_min_speech():
    """VADConfig should accept custom silero_min_speech_duration_ms."""
    config = VADConfig(silero_min_speech_duration_ms=400)
    assert config.silero_min_speech_duration_ms == 400


# ---------------------------------------------------------------------------
# Silero VAD integration tests
# ---------------------------------------------------------------------------


def test_no_sentence_truncation(speech_with_pauses: Path):
    """Chunks should not truncate sentences at boundaries.

    Verifies that Silero VAD produces chunks with no undersized segments
    (which would indicate a sentence was split mid-speech).
    """
    config = SubtapConfig()
    config.audio.vad.use_silero_vad = True

    workspace = Workspace(config, base_dir=Path("tests/fixtures/workspaces/work_test_vad_truncation"))
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(speech_with_pauses, workspace.source_audio)

    chunks = split_chunks(workspace, config)

    # Must have chunks
    assert len(chunks) > 0, "至少应产生一个 chunk"

    # No chunk should be shorter than 0.5s — our synthetic audio has
    # 1.5s speech segments, so nothing should be tiny.
    for chunk in chunks:
        duration = chunk.end_sec - chunk.start_sec
        assert (
            duration >= 0.5
        ), f"Chunk {chunk.chunk_id} 太短 ({duration:.2f}s)，可能截断了句子"


def test_silero_vad_finds_natural_pauses(speech_with_pauses: Path):
    """Silero VAD should find natural pause points, not mechanical splits."""
    config = SubtapConfig()
    config.audio.vad.use_silero_vad = True
    config.audio.vad.max_chunk_sec = 3.0

    workspace = Workspace(config, base_dir=Path("tests/fixtures/workspaces/work_test_vad"))
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(speech_with_pauses, workspace.source_audio)

    chunks = split_chunks(workspace, config)

    assert len(chunks) > 0, "应该至少有一个 chunk"

    # 验证每个 chunk 不超过 max_chunk_sec + 容差
    for chunk in chunks:
        duration = chunk.end_sec - chunk.start_sec
        assert duration <= config.audio.vad.max_chunk_sec + 1.0


def test_silero_vad_single_burst(single_burst: Path):
    """Silero VAD should handle a single short speech segment."""
    config = SubtapConfig()
    config.audio.vad.use_silero_vad = True

    workspace = Workspace(config, base_dir=Path("tests/fixtures/workspaces/work_test_vad_single"))
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(single_burst, workspace.source_audio)

    chunks = split_chunks(workspace, config)

    # Even a short burst should produce at least one chunk
    assert len(chunks) >= 1, "短音频也应至少产生一个 chunk"


def test_vad_error_on_missing_file():
    """split_chunks should raise VADError for a nonexistent audio file."""
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=Path("tests/fixtures/workspaces/work_test_vad_missing"))
    workspace.ensure_dirs()

    with pytest.raises(VADError, match="音频文件加载失败"):
        split_chunks(workspace, config)


def test_vad_error_on_corrupt_file(tmp_path: Path):
    """split_chunks should raise VADError for a corrupt audio file."""
    corrupt = tmp_path / "corrupt.wav"
    corrupt.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt NOT_A_WAV")

    config = SubtapConfig()
    workspace = Workspace(config, base_dir=Path("tests/fixtures/workspaces/work_test_vad_corrupt"))
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(corrupt, workspace.source_audio)

    with pytest.raises(VADError, match="音频文件加载失败"):
        split_chunks(workspace, config)


# ---------------------------------------------------------------------------
# pydub fallback tests
# ---------------------------------------------------------------------------


def test_pydub_fallback_speech_with_pauses(speech_with_pauses: Path):
    """pydub fallback should also produce chunks from speech + silence audio."""
    config = SubtapConfig()
    config.audio.vad.use_silero_vad = False

    workspace = Workspace(config, base_dir=Path("tests/fixtures/workspaces/work_test_pydub"))
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(speech_with_pauses, workspace.source_audio)

    chunks = split_chunks(workspace, config)

    assert len(chunks) > 0, "pydub fallback 应至少产生一个 chunk"

    for chunk in chunks:
        duration = chunk.end_sec - chunk.start_sec
        assert duration >= 0.5, f"Chunk {chunk.chunk_id} 太短 ({duration:.2f}s)"


def test_pydub_fallback_single_burst(single_burst: Path):
    """pydub fallback should handle a single short speech segment."""
    config = SubtapConfig()
    config.audio.vad.use_silero_vad = False

    workspace = Workspace(config, base_dir=Path("tests/fixtures/workspaces/work_test_pydub_single"))
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(single_burst, workspace.source_audio)

    chunks = split_chunks(workspace, config)

    assert len(chunks) >= 1, "pydub fallback 短音频也应至少产生一个 chunk"
