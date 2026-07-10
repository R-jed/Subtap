import pytest
from pathlib import Path
from subtap.schemas.config import VADConfig, SubtapConfig
from subtap.core.workspace import Workspace
from subtap.core.vad import split_chunks


def test_vad_config_silero_field():
    """VADConfig should have use_silero_vad field with default True."""
    config = VADConfig()
    assert hasattr(config, "use_silero_vad")
    assert config.use_silero_vad is True


def test_vad_config_silero_false():
    """VADConfig should accept use_silero_vad=False."""
    config = VADConfig(use_silero_vad=False)
    assert config.use_silero_vad is False


def test_no_sentence_truncation():
    """Chunks should not truncate sentences at boundaries.

    Verifies that Silero VAD produces chunks with no undersized segments
    (which would indicate a sentence was split mid-speech).
    """
    test_audio = Path("/Users/qunqing/Downloads/ASR-SRT测试音频/短的演讲音频.wav")
    if not test_audio.exists():
        pytest.skip("测试音频不存在")

    config = SubtapConfig()
    config.audio.vad.use_silero_vad = True

    workspace = Workspace(config, base_dir=Path("work_test_vad_truncation"))
    workspace.ensure_dirs()
    import shutil
    shutil.copy2(test_audio, workspace.source_audio)

    chunks = split_chunks(workspace, config)

    # Must have chunks
    assert len(chunks) > 0, "至少应产生一个 chunk"

    # No chunk should be shorter than 1.0s — shorter chunks indicate
    # the VAD split mid-speech, truncating a sentence.
    for chunk in chunks:
        duration = chunk.end_sec - chunk.start_sec
        assert duration >= 1.0, (
            f"Chunk {chunk.chunk_id} 太短 ({duration:.2f}s)，可能截断了句子"
        )


def test_silero_vad_finds_natural_pauses():
    """Silero VAD should find natural pause points, not mechanical splits."""
    test_audio = Path("/Users/qunqing/Downloads/ASR-SRT测试音频/短的演讲音频.wav")
    if not test_audio.exists():
        pytest.skip("测试音频不存在")

    config = SubtapConfig()
    config.audio.vad.use_silero_vad = True
    config.audio.vad.max_chunk_sec = 10.0

    workspace = Workspace(config, base_dir=Path("work_test_vad"))
    workspace.ensure_dirs()
    # Copy test audio to workspace source location
    import shutil
    shutil.copy2(test_audio, workspace.source_audio)

    chunks = split_chunks(workspace, config)

    assert len(chunks) > 0, "应该至少有一个 chunk"

    # 验证每个 chunk 不超过 max_chunk_sec + 容差
    for chunk in chunks:
        duration = chunk.end_sec - chunk.start_sec
        assert duration <= config.audio.vad.max_chunk_sec + 1.0

    # 验证有自然停顿（chunk 时长不完全相同）
    durations = [c.end_sec - c.start_sec for c in chunks]
    unique_durations = set(round(d, 1) for d in durations)
    assert len(unique_durations) > 1, (
        f"应该有不同长度的 chunks，实际 durations={durations}"
    )
