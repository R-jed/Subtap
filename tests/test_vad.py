import pytest
import numpy as np
import wave
from pathlib import Path
from types import SimpleNamespace

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


def test_vad_config_rejects_unknown_sensitivity():
    """Unknown sensitivity names must fail instead of silently using normal."""
    with pytest.raises(ValueError):
        VADConfig(sensitivity="typo")


def test_vad_config_rejects_legacy_chunk_limit():
    """The removed mechanical chunk limit must fail with a clear config error."""
    with pytest.raises(ValueError, match="max_chunk_sec.*已移除"):
        VADConfig.model_validate({"max_chunk_sec": 30})


def test_silero_vad_uses_bundled_sherpa_model_and_normalized_pcm(monkeypatch):
    """The packaged Silero backend must preserve its public VAD settings."""
    from pydub import AudioSegment

    import subtap.core.vad as vad

    captured = SimpleNamespace(peak=0.0, config=None, buffer_size=0.0)

    class FakeConfig:
        def __init__(self):
            self.silero_vad = SimpleNamespace()

    class FakeDetector:
        def __init__(self, config, buffer_size_in_seconds):
            captured.config = config
            captured.buffer_size = buffer_size_in_seconds
            self._segments = [
                SimpleNamespace(start=512, samples=np.zeros(512, dtype=np.float32))
            ]

        def accept_waveform(self, samples):
            captured.peak = max(captured.peak, float(np.abs(samples).max()))

        def flush(self):
            pass

        def empty(self):
            return not self._segments

        @property
        def front(self):
            return self._segments[0]

        def pop(self):
            self._segments.pop(0)

    pcm = np.zeros(1600, dtype=np.int32)
    pcm[:3] = [0, 2**30, -(2**30)]
    audio = AudioSegment(
        data=pcm.tobytes(),
        sample_width=4,
        frame_rate=16000,
        channels=1,
    )
    monkeypatch.setattr(
        vad,
        "sherpa_onnx",
        SimpleNamespace(
            VadModelConfig=FakeConfig,
            VoiceActivityDetector=FakeDetector,
        ),
    )

    segments = vad._get_speech_segments_silero(
        audio,
        threshold=0.7,
        min_silence_ms=300,
        min_speech_duration_ms=400,
    )

    assert captured.peak <= 1.0
    assert captured.config.silero_vad.threshold == 0.7
    assert captured.config.silero_vad.min_silence_duration == 0.3
    assert captured.config.silero_vad.min_speech_duration == 0.4
    assert captured.config.silero_vad.window_size == 512
    assert captured.buffer_size >= len(audio) / 1000
    assert segments == [[0.002, 0.094]]


# ---------------------------------------------------------------------------
# Silero VAD integration tests
# ---------------------------------------------------------------------------


def test_no_sentence_truncation(monkeypatch, speech_with_pauses: Path):
    """Chunks should not truncate sentences at boundaries.

    Verifies that Silero VAD produces chunks with no undersized segments
    (which would indicate a sentence was split mid-speech).
    """
    config = SubtapConfig()
    config.audio.vad.use_silero_vad = True

    workspace = Workspace(
        config, base_dir=Path("tests/fixtures/workspaces/work_test_vad_truncation")
    )
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(speech_with_pauses, workspace.source_audio)
    monkeypatch.setattr(
        "subtap.core.vad._get_speech_segments_silero",
        lambda *args, **kwargs: [[0.0, 1.5], [2.5, 4.0]],
    )

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


def test_silero_vad_finds_natural_pauses(monkeypatch, speech_with_pauses: Path):
    """Silero VAD should find natural pause points, not mechanical splits."""
    config = SubtapConfig()
    config.audio.vad.use_silero_vad = True

    workspace = Workspace(
        config, base_dir=Path("tests/fixtures/workspaces/work_test_vad")
    )
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(speech_with_pauses, workspace.source_audio)
    monkeypatch.setattr(
        "subtap.core.vad._get_speech_segments_silero",
        lambda *args, **kwargs: [[0.0, 1.5], [2.5, 4.0]],
    )

    chunks = split_chunks(workspace, config)

    assert len(chunks) > 0, "应该至少有一个 chunk"

    assert [(chunk.start_sec, chunk.end_sec) for chunk in chunks] == [
        (0.0, 1.5),
        (2.5, 4.0),
    ]


def test_silero_vad_single_burst(monkeypatch, single_burst: Path):
    """Silero VAD should handle a single short speech segment."""
    config = SubtapConfig()
    config.audio.vad.use_silero_vad = True

    workspace = Workspace(
        config, base_dir=Path("tests/fixtures/workspaces/work_test_vad_single")
    )
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(single_burst, workspace.source_audio)
    monkeypatch.setattr(
        "subtap.core.vad._get_speech_segments_silero",
        lambda *args, **kwargs: [[0.0, 0.8]],
    )

    chunks = split_chunks(workspace, config)

    # Even a short burst should produce at least one chunk
    assert len(chunks) >= 1, "短音频也应至少产生一个 chunk"


def test_vad_error_on_missing_file():
    """split_chunks should raise VADError for a nonexistent audio file."""
    config = SubtapConfig()
    workspace = Workspace(
        config, base_dir=Path("tests/fixtures/workspaces/work_test_vad_missing")
    )
    workspace.ensure_dirs()

    with pytest.raises(VADError, match="音频文件加载失败"):
        split_chunks(workspace, config)


def test_vad_error_on_corrupt_file(tmp_path: Path):
    """split_chunks should raise VADError for a corrupt audio file."""
    corrupt = tmp_path / "corrupt.wav"
    corrupt.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt NOT_A_WAV")

    config = SubtapConfig()
    workspace = Workspace(
        config, base_dir=Path("tests/fixtures/workspaces/work_test_vad_corrupt")
    )
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

    workspace = Workspace(
        config, base_dir=Path("tests/fixtures/workspaces/work_test_pydub")
    )
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

    workspace = Workspace(
        config, base_dir=Path("tests/fixtures/workspaces/work_test_pydub_single")
    )
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(single_burst, workspace.source_audio)

    chunks = split_chunks(workspace, config)

    assert len(chunks) >= 1, "pydub fallback 短音频也应至少产生一个 chunk"


def test_silero_vad_enforces_max_chunk_duration(monkeypatch, tmp_path: Path):
    """A long Silero speech region must still respect the shared chunk limit."""
    source = tmp_path / "long_speech.wav"
    _write_wav(source, _make_speech_samples(5000))

    config = SubtapConfig()
    config.audio.vad.use_silero_vad = True
    monkeypatch.setattr("subtap.core.vad._FORCED_ALIGNER_MAX_SEC", 1.5)
    monkeypatch.setattr("subtap.core.vad._LOW_ENERGY_SEARCH_SEC", 0.25)

    workspace = Workspace(config, base_dir=tmp_path / "workspace")
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(source, workspace.source_audio)
    monkeypatch.setattr(
        "subtap.core.vad._get_speech_segments_silero",
        lambda *args, **kwargs: [[0.0, 4.8]],
    )

    chunks = split_chunks(workspace, config)

    assert len(chunks) > 1
    assert all(chunk.end_sec - chunk.start_sec <= 1.5 for chunk in chunks)
    assert chunks[0].start_sec == 0.0
    assert chunks[-1].end_sec == 4.8
    assert all(
        current.end_sec == following.start_sec
        for current, following in zip(chunks, chunks[1:])
    )


def test_silero_vad_never_exceeds_aligner_limit(monkeypatch, tmp_path: Path):
    """A low-energy point after the limit must not create an oversized chunk."""
    source = tmp_path / "late_pause.wav"
    samples = np.concatenate(
        [
            _make_speech_samples(3500),
            np.zeros(300 * 16, dtype=np.int16),
            _make_speech_samples(1200),
        ]
    )
    _write_wav(source, samples)

    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "workspace")
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(source, workspace.source_audio)
    monkeypatch.setattr("subtap.core.vad._FORCED_ALIGNER_MAX_SEC", 3.0)
    monkeypatch.setattr("subtap.core.vad._LOW_ENERGY_SEARCH_SEC", 0.5, raising=False)
    monkeypatch.setattr(
        "subtap.core.vad._get_speech_segments_silero",
        lambda *args, **kwargs: [[0.0, 5.0]],
    )

    chunks = split_chunks(workspace, config)

    assert all(chunk.end_sec - chunk.start_sec <= 3.0 for chunk in chunks)


def test_silero_vad_preserves_short_detected_speech(monkeypatch, tmp_path: Path):
    """A valid short utterance must not disappear beside longer speech."""
    source = tmp_path / "short_and_long.wav"
    _write_wav(source, _make_speech_samples(4000))

    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "workspace")
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(source, workspace.source_audio)
    monkeypatch.setattr(
        "subtap.core.vad._get_speech_segments_silero",
        lambda *args, **kwargs: [[0.0, 0.8], [2.0, 3.5]],
    )

    chunks = split_chunks(workspace, config)

    assert [(chunk.start_sec, chunk.end_sec) for chunk in chunks] == [
        (0.0, 0.8),
        (2.0, 3.5),
    ]


def test_silero_vad_rejects_audio_without_speech(monkeypatch, tmp_path: Path):
    """No detected speech must fail instead of transcribing the whole file."""
    source = tmp_path / "silence.wav"
    _write_wav(source, np.zeros(32000, dtype=np.int16))

    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "workspace")
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(source, workspace.source_audio)
    monkeypatch.setattr(
        "subtap.core.vad._get_speech_segments_silero",
        lambda *args, **kwargs: [],
    )

    with pytest.raises(VADError, match="未检测到语音"):
        split_chunks(workspace, config)


def test_silero_vad_rejects_invalid_speech_interval(monkeypatch, tmp_path: Path):
    """Invalid detector timestamps must fail before empty chunks are exported."""
    source = tmp_path / "speech.wav"
    _write_wav(source, _make_speech_samples(2000))

    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "workspace")
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(source, workspace.source_audio)
    monkeypatch.setattr(
        "subtap.core.vad._get_speech_segments_silero",
        lambda *args, **kwargs: [[1.5, 1.0]],
    )

    with pytest.raises(VADError, match="无效语音区间"):
        split_chunks(workspace, config)


def test_silero_vad_prefers_a_pause_before_hard_limit(monkeypatch, tmp_path: Path):
    """An oversized speech region should split at nearby silence, not speech."""
    source = tmp_path / "speech_with_short_pause.wav"
    samples = np.concatenate(
        [
            _make_speech_samples(2000),
            np.zeros(300 * 16, dtype=np.int16),
            _make_speech_samples(2700),
        ]
    )
    _write_wav(source, samples)

    config = SubtapConfig()
    monkeypatch.setattr("subtap.core.vad._FORCED_ALIGNER_MAX_SEC", 3.0)
    monkeypatch.setattr("subtap.core.vad._LOW_ENERGY_SEARCH_SEC", 1.0)
    workspace = Workspace(config, base_dir=tmp_path / "workspace")
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(source, workspace.source_audio)
    monkeypatch.setattr(
        "subtap.core.vad._get_speech_segments_silero",
        lambda *args, **kwargs: [[0.0, 5.0]],
    )

    chunks = split_chunks(workspace, config)

    assert 2.0 <= chunks[0].end_sec <= 2.3
    assert chunks[-1].end_sec == 5.0
    assert all(chunk.end_sec - chunk.start_sec <= 3.0 for chunk in chunks)


def test_silero_vad_keeps_continuous_speech_below_aligner_limit(
    monkeypatch, tmp_path: Path
):
    """VAD must not impose 30-second cuts below the aligner's real limit."""
    source = tmp_path / "continuous_speech.wav"
    _write_wav(source, _make_speech_samples(31000))

    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "workspace")
    workspace.ensure_dirs()
    import shutil

    shutil.copy2(source, workspace.source_audio)
    monkeypatch.setattr(
        "subtap.core.vad._get_speech_segments_silero",
        lambda *args, **kwargs: [[0.0, 31.0]],
    )

    chunks = split_chunks(workspace, config)

    assert [(chunk.start_sec, chunk.end_sec) for chunk in chunks] == [(0.0, 31.0)]
