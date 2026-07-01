"""Comparison test for different VAD implementations."""

import tempfile
import time
from pathlib import Path

import numpy as np
from pydub import AudioSegment

from subtap.core.vad import split_chunks as intelligent_vad
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig


def create_test_audio(duration_sec: float = 10.0) -> AudioSegment:
    """Create test audio with speech and silence segments.

    Args:
        duration_sec: Total duration in seconds

    Returns:
        AudioSegment with known speech/silence pattern
    """
    sample_rate = 16000
    samples = np.zeros(int(sample_rate * duration_sec), dtype=np.float32)

    # Add speech segments at known positions
    # Speech at 1-3 seconds
    samples[sample_rate:3*sample_rate] = np.random.randn(2*sample_rate).astype(np.float32) * 0.5

    # Speech at 5-8 seconds
    samples[5*sample_rate:8*sample_rate] = np.random.randn(3*sample_rate).astype(np.float32) * 0.5

    # Convert to AudioSegment
    audio = AudioSegment(
        samples.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=1,
    )

    return audio


def test_intelligent_vad_basic():
    """Test intelligent VAD with basic audio."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(SubtapConfig(), Path(tmpdir))
        workspace.root.mkdir(parents=True, exist_ok=True)
        workspace.audio_dir.mkdir(parents=True, exist_ok=True)
        workspace.chunks_dir.mkdir(parents=True, exist_ok=True)

        # Create test audio
        audio = create_test_audio(10.0)
        source_path = workspace.audio_dir / "source.wav"
        audio.export(str(source_path), format="wav")

        # Test with different sensitivities
        for sensitivity in ["low", "normal", "high"]:
            config = SubtapConfig()
            config.audio.vad.sensitivity = sensitivity

            start_time = time.time()
            chunks = intelligent_vad(workspace, config)
            elapsed = time.time() - start_time

            print(f"\nSensitivity: {sensitivity}")
            print(f"  Chunks: {len(chunks)}")
            print(f"  Time: {elapsed:.3f}s")

            for i, chunk in enumerate(chunks):
                print(f"  Chunk {i}: {chunk.start_sec:.3f}s - {chunk.end_sec:.3f}s")

            # Verify chunks are valid
            assert len(chunks) > 0
            for chunk in chunks:
                chunk_path = workspace.root / chunk.path
                assert chunk_path.exists()


def test_vad_comparison_with_real_audio():
    """Compare VAD implementations with real audio files."""
    import os

    # Find test audio files
    test_audio_dir = Path("/Users/qunqing/Downloads/ASR-SRT测试音频")

    if not test_audio_dir.exists():
        print(f"Test audio directory not found: {test_audio_dir}")
        return

    audio_files = list(test_audio_dir.glob("*.wav")) + list(test_audio_dir.glob("*.mp3"))

    if not audio_files:
        print("No audio files found in test directory")
        return

    print(f"\nFound {len(audio_files)} audio files for comparison")

    for audio_file in audio_files[:3]:  # Test with first 3 files
        print(f"\n{'='*60}")
        print(f"Testing: {audio_file.name}")
        print('='*60)

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Workspace(SubtapConfig(), Path(tmpdir))
            workspace.root.mkdir(parents=True, exist_ok=True)
            workspace.audio_dir.mkdir(parents=True, exist_ok=True)
            workspace.chunks_dir.mkdir(parents=True, exist_ok=True)

            # Load and convert audio
            if audio_file.suffix == '.mp3':
                audio = AudioSegment.from_mp3(str(audio_file))
            else:
                audio = AudioSegment.from_wav(str(audio_file))

            # Convert to 16kHz mono
            audio = audio.set_frame_rate(16000).set_channels(1)

            source_path = workspace.audio_dir / "source.wav"
            audio.export(str(source_path), format="wav")

            # Test intelligent VAD with different sensitivities
            for sensitivity in ["low", "normal", "high"]:
                config = SubtapConfig()
                config.audio.vad.sensitivity = sensitivity

                start_time = time.time()
                chunks = intelligent_vad(workspace, config)
                elapsed = time.time() - start_time

                print(f"\nSensitivity: {sensitivity}")
                print(f"  Chunks: {len(chunks)}")
                print(f"  Time: {elapsed:.3f}s")

                # Print first few chunks
                for i, chunk in enumerate(chunks[:5]):
                    print(f"  Chunk {i}: {chunk.start_sec:.3f}s - {chunk.end_sec:.3f}s")
                if len(chunks) > 5:
                    print(f"  ... and {len(chunks) - 5} more chunks")


if __name__ == "__main__":
    print("Running VAD comparison tests...")
    test_intelligent_vad_basic()
    test_vad_comparison_with_real_audio()
