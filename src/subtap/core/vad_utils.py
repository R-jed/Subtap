"""Intelligent VAD utilities with multi-feature fusion."""

from __future__ import annotations

import numpy as np
from pydub import AudioSegment


def calculate_frame_energy(
    audio: AudioSegment,
    frame_duration_ms: int = 30,
) -> np.ndarray:
    """Calculate normalized frame energy.

    Args:
        audio: Input audio segment
        frame_duration_ms: Frame duration in milliseconds

    Returns:
        Array of normalized energy values (0-1)
    """
    # Convert to numpy array
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)

    # Calculate frame size in samples
    frame_size = int(audio.frame_rate * frame_duration_ms / 1000)

    # Calculate number of frames
    num_frames = len(samples) // frame_size

    if num_frames == 0:
        return np.array([0.0])

    # Reshape to frames
    frames = samples[:num_frames * frame_size].reshape(num_frames, frame_size)

    # Calculate RMS energy for each frame
    energy = np.sqrt(np.mean(frames ** 2, axis=1))

    # Normalize to 0-1
    if np.max(energy) > 0:
        energy = energy / np.max(energy)

    return energy


def calculate_zero_crossing_rate(
    audio: AudioSegment,
    frame_duration_ms: int = 30,
) -> np.ndarray:
    """Calculate zero crossing rate.

    Args:
        audio: Input audio segment
        frame_duration_ms: Frame duration in milliseconds

    Returns:
        Array of ZCR values (normalized to 0-1)
    """
    # Convert to numpy array
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)

    # Calculate frame size in samples
    frame_size = int(audio.frame_rate * frame_duration_ms / 1000)

    # Calculate number of frames
    num_frames = len(samples) // frame_size

    if num_frames == 0:
        return np.array([0.0])

    # Reshape to frames
    frames = samples[:num_frames * frame_size].reshape(num_frames, frame_size)

    # Calculate ZCR for each frame
    zcr = np.zeros(num_frames)
    for i in range(num_frames):
        # Count zero crossings
        crossings = np.sum(np.diff(np.sign(frames[i])) != 0)
        zcr[i] = crossings / frame_size

    # Normalize to 0-1 (max ZCR is 1.0 for white noise)
    zcr = np.clip(zcr * 2, 0, 1)  # Scale up for better discrimination

    return zcr


def calculate_spectral_centroid(
    audio: AudioSegment,
    frame_duration_ms: int = 30,
) -> np.ndarray:
    """Calculate spectral centroid.

    Args:
        audio: Input audio segment
        frame_duration_ms: Frame duration in milliseconds

    Returns:
        Array of normalized spectral centroid values (0-1)
    """
    # Convert to numpy array
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)

    # Calculate frame size in samples
    frame_size = int(audio.frame_rate * frame_duration_ms / 1000)

    # Calculate number of frames
    num_frames = len(samples) // frame_size

    if num_frames == 0:
        return np.array([0.0])

    # Reshape to frames
    frames = samples[:num_frames * frame_size].reshape(num_frames, frame_size)

    # Calculate spectral centroid for each frame
    centroid = np.zeros(num_frames)
    for i in range(num_frames):
        # Compute FFT
        spectrum = np.abs(np.fft.rfft(frames[i]))
        freqs = np.fft.rfftfreq(frame_size, 1.0 / audio.frame_rate)

        # Calculate spectral centroid
        if np.sum(spectrum) > 0:
            centroid[i] = np.sum(freqs * spectrum) / np.sum(spectrum)

    # Normalize to 0-1 (assuming max frequency is Nyquist)
    max_freq = audio.frame_rate / 2
    centroid = centroid / max_freq

    return centroid


def calculate_vad_probability(
    energy: np.ndarray,
    zcr: np.ndarray,
    spectral: np.ndarray,
    energy_weight: float = 0.5,
    zcr_weight: float = 0.3,
    spectral_weight: float = 0.2,
) -> np.ndarray:
    """Calculate VAD probability from multiple features.

    Args:
        energy: Normalized energy values
        zcr: Normalized zero crossing rate
        spectral: Normalized spectral centroid
        energy_weight: Weight for energy feature
        zcr_weight: Weight for ZCR feature (inverted: low ZCR = speech)
        spectral_weight: Weight for spectral centroid

    Returns:
        Array of VAD probabilities (0-1)
    """
    # Invert ZCR (low ZCR = speech, high ZCR = noise/silence)
    zcr_inverted = 1.0 - zcr

    # Combine features with weights
    probability = (
        energy_weight * energy +
        zcr_weight * zcr_inverted +
        spectral_weight * spectral
    )

    # Clip to 0-1
    probability = np.clip(probability, 0, 1)

    return probability


def get_thresholds_for_sensitivity(
    sensitivity: str,
) -> tuple[float, float]:
    """Get enter/exit thresholds for given sensitivity.

    Args:
        sensitivity: Sensitivity level (low/normal/high)

    Returns:
        Tuple of (enter_threshold, exit_threshold)
    """
    thresholds = {
        "low": (0.65, 0.55),
        "normal": (0.55, 0.45),
        "high": (0.45, 0.35),
    }

    return thresholds.get(sensitivity, thresholds["normal"])
