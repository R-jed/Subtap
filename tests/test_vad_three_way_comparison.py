"""Three-way VAD comparison: Intelligent VAD vs webrtcvad vs Silero VAD."""

import tempfile
import time
from pathlib import Path
from dataclasses import dataclass

import numpy as np
from pydub import AudioSegment

from subtap.core.vad import split_chunks as intelligent_vad
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig


@dataclass
class VADResult:
    """VAD test result."""
    name: str
    chunks: int
    time_sec: float
    segments: list[tuple[float, float]]


def create_test_audio_with_speech_gaps(duration_sec: float = 15.0) -> AudioSegment:
    """Create test audio with known speech/silence pattern.

    Pattern:
    - 0-2s: silence
    - 2-5s: speech
    - 5-7s: silence
    - 7-10s: speech
    - 10-12s: silence
    - 12-15s: speech
    """
    sample_rate = 16000
    samples = np.zeros(int(sample_rate * duration_sec), dtype=np.float32)

    # Add speech segments at known positions
    # Speech at 2-5 seconds
    samples[2*sample_rate:5*sample_rate] = np.random.randn(3*sample_rate).astype(np.float32) * 0.5

    # Speech at 7-10 seconds
    samples[7*sample_rate:10*sample_rate] = np.random.randn(3*sample_rate).astype(np.float32) * 0.5

    # Speech at 12-15 seconds
    samples[12*sample_rate:15*sample_rate] = np.random.randn(3*sample_rate).astype(np.float32) * 0.5

    # Convert to AudioSegment
    audio = AudioSegment(
        samples.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=1,
    )

    return audio


def test_intelligent_vad(audio_path: Path, sensitivity: str = "normal") -> VADResult:
    """Test our intelligent VAD."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(SubtapConfig(), Path(tmpdir))
        workspace.root.mkdir(parents=True, exist_ok=True)
        workspace.audio_dir.mkdir(parents=True, exist_ok=True)
        workspace.chunks_dir.mkdir(parents=True, exist_ok=True)

        # Load audio
        audio = AudioSegment.from_wav(str(audio_path))

        # Save to workspace
        source_path = workspace.audio_dir / "source.wav"
        audio.export(str(source_path), format="wav")

        config = SubtapConfig()
        config.audio.vad.sensitivity = sensitivity

        start_time = time.time()
        chunks = intelligent_vad(workspace, config)
        elapsed = time.time() - start_time

        segments = [(chunk.start_sec, chunk.end_sec) for chunk in chunks]

        return VADResult(
            name=f"Intelligent VAD ({sensitivity})",
            chunks=len(chunks),
            time_sec=elapsed,
            segments=segments,
        )


def test_webrtcvad(audio_path: Path, aggressiveness: int = 2) -> VADResult:
    """Test webrtcvad."""
    import webrtcvad

    # Load audio
    audio = AudioSegment.from_wav(str(audio_path))

    # Convert to 16kHz mono 16-bit
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

    # Get raw audio data
    raw_data = audio.raw_data
    sample_rate = audio.frame_rate

    # Create VAD
    vad = webrtcvad.Vad(aggressiveness)

    # Frame duration: 30ms
    frame_duration_ms = 30
    frame_size = int(sample_rate * frame_duration_ms / 1000) * 2  # 2 bytes per sample

    # Detect speech frames
    speech_frames = []
    for i in range(0, len(raw_data) - frame_size, frame_size):
        frame = raw_data[i:i + frame_size]
        is_speech = vad.is_speech(frame, sample_rate)
        speech_frames.append(is_speech)

    # Convert frames to segments
    segments = []
    in_speech = False
    start_sec = 0.0

    for i, is_speech in enumerate(speech_frames):
        current_sec = i * frame_duration_ms / 1000

        if not in_speech and is_speech:
            in_speech = True
            start_sec = current_sec
        elif in_speech and not is_speech:
            in_speech = False
            segments.append((start_sec, current_sec))

    if in_speech:
        segments.append((start_sec, len(speech_frames) * frame_duration_ms / 1000))

    return VADResult(
        name=f"webrtcvad (aggressiveness={aggressiveness})",
        chunks=len(segments),
        time_sec=0.0,  # webrtcvad is very fast
        segments=segments,
    )


def test_silero_vad(audio_path: Path, threshold: float = 0.5) -> VADResult:
    """Test Silero VAD."""
    import torch
    from silero_vad import load_silero_vad, read_audio, get_speech_timestamps

    # Load model
    model = load_silero_vad()

    # Read audio
    wav = read_audio(str(audio_path), sampling_rate=16000)

    # Get speech timestamps
    start_time = time.time()
    speech_timestamps = get_speech_timestamps(
        wav,
        model,
        threshold=threshold,
        sampling_rate=16000,
    )
    elapsed = time.time() - start_time

    # Convert to segments
    segments = []
    for ts in speech_timestamps:
        start_sec = ts['start'] / 16000
        end_sec = ts['end'] / 16000
        segments.append((start_sec, end_sec))

    return VADResult(
        name=f"Silero VAD (threshold={threshold})",
        chunks=len(segments),
        time_sec=elapsed,
        segments=segments,
    )


def run_comparison(audio_path: Path, audio_name: str):
    """Run three-way comparison on an audio file."""
    print(f"\n{'='*80}")
    print(f"音频文件: {audio_name}")
    print('='*80)

    results = []

    # Test Intelligent VAD
    for sensitivity in ["low", "normal", "high"]:
        result = test_intelligent_vad(audio_path, sensitivity)
        results.append(result)

    # Test webrtcvad
    for aggressiveness in [0, 1, 2, 3]:
        result = test_webrtcvad(audio_path, aggressiveness)
        results.append(result)

    # Test Silero VAD
    for threshold in [0.3, 0.5, 0.7]:
        result = test_silero_vad(audio_path, threshold)
        results.append(result)

    # Print results table
    print(f"\n{'名称':<35} {'分段数':>8} {'耗时(s)':>10}")
    print("-" * 60)
    for r in results:
        print(f"{r.name:<35} {r.chunks:>8} {r.time_sec:>10.3f}")

    # Print detailed segments for key configurations
    print(f"\n详细分段（前5个）:")
    key_configs = [
        "Intelligent VAD (normal)",
        "webrtcvad (aggressiveness=2)",
        "Silero VAD (threshold=0.5)",
    ]
    for config_name in key_configs:
        for r in results:
            if r.name == config_name:
                print(f"\n{r.name}:")
                for i, (start, end) in enumerate(r.segments[:5]):
                    print(f"  段{i}: {start:.3f}s - {end:.3f}s (时长: {end-start:.3f}s)")
                if len(r.segments) > 5:
                    print(f"  ... 还有 {len(r.segments) - 5} 个分段")
                break


def main():
    """Main comparison function."""
    print("="*80)
    print("三者VAD效果对比测试")
    print("="*80)

    # Test with synthetic audio
    print("\n[1] 合成测试音频（已知语音/静音模式）")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        audio = create_test_audio_with_speech_gaps(15.0)
        audio.export(str(tmp_path), format="wav")
        run_comparison(tmp_path, "合成测试音频（15秒，3段语音）")
        tmp_path.unlink()

    # Test with real audio files
    test_audio_dir = Path("/Users/qunqing/Downloads/ASR-SRT测试音频")

    if test_audio_dir.exists():
        audio_files = list(test_audio_dir.glob("*.wav")) + list(test_audio_dir.glob("*.mp3"))

        if audio_files:
            print(f"\n[2] 真实音频文件测试")
            for audio_file in audio_files[:3]:  # Test with first 3 files
                # Convert to WAV if needed
                if audio_file.suffix == '.mp3':
                    audio = AudioSegment.from_mp3(str(audio_file))
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                        tmp_path = Path(tmp.name)
                        audio = audio.set_frame_rate(16000).set_channels(1)
                        audio.export(str(tmp_path), format="wav")
                        run_comparison(tmp_path, audio_file.name)
                        tmp_path.unlink()
                else:
                    run_comparison(audio_file, audio_file.name)

    print("\n" + "="*80)
    print("对比测试完成")
    print("="*80)


if __name__ == "__main__":
    main()
