"""Tests for intelligent VAD algorithm."""

import numpy as np
import pytest
from pydub import AudioSegment

from subtap.core.vad_utils import (
    calculate_frame_energy,
    calculate_zero_crossing_rate,
    calculate_spectral_centroid,
    calculate_vad_probability,
)


def test_calculate_frame_energy():
    """Energy calculation should return values between 0 and 1."""
    # Create test audio with known energy
    samples = np.random.randn(16000).astype(np.float32)  # 1 second
    audio = AudioSegment(
        samples.tobytes(),
        frame_rate=16000,
        sample_width=2,
        channels=1,
    )

    energy = calculate_frame_energy(audio, frame_duration_ms=30)

    # Should return array of probabilities
    assert isinstance(energy, np.ndarray)
    assert len(energy) > 0
    assert all(0 <= e <= 1 for e in energy)


def test_calculate_zero_crossing_rate():
    """ZCR should detect signal transitions."""
    # Sine wave should have low ZCR
    t = np.linspace(0, 1, 16000)
    sine = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    audio_sine = AudioSegment(
        sine.tobytes(),
        frame_rate=16000,
        sample_width=2,
        channels=1,
    )

    # White noise should have high ZCR
    noise = np.random.randn(16000).astype(np.float32)
    audio_noise = AudioSegment(
        noise.tobytes(),
        frame_rate=16000,
        sample_width=2,
        channels=1,
    )

    zcr_sine = calculate_zero_crossing_rate(audio_sine, frame_duration_ms=30)
    zcr_noise = calculate_zero_crossing_rate(audio_noise, frame_duration_ms=30)

    # Noise should have higher ZCR than sine
    assert np.mean(zcr_noise) > np.mean(zcr_sine)


def test_calculate_spectral_centroid():
    """Spectral centroid should distinguish tonal vs noisy signals."""
    # Low frequency sine
    t = np.linspace(0, 1, 16000)
    low_freq = np.sin(2 * np.pi * 200 * t).astype(np.float32)
    audio_low = AudioSegment(
        low_freq.tobytes(),
        frame_rate=16000,
        sample_width=2,
        channels=1,
    )

    # High frequency sine
    high_freq = np.sin(2 * np.pi * 4000 * t).astype(np.float32)
    audio_high = AudioSegment(
        high_freq.tobytes(),
        frame_rate=16000,
        sample_width=2,
        channels=1,
    )

    centroid_low = calculate_spectral_centroid(audio_low, frame_duration_ms=30)
    centroid_high = calculate_spectral_centroid(audio_high, frame_duration_ms=30)

    # High frequency should have higher centroid
    assert np.mean(centroid_high) > np.mean(centroid_low)


def test_calculate_vad_probability():
    """VAD probability should combine features correctly."""
    # Create test features
    energy = np.array([0.8, 0.2, 0.9, 0.1])
    zcr = np.array([0.3, 0.7, 0.2, 0.8])
    spectral = np.array([0.5, 0.5, 0.6, 0.4])

    probability = calculate_vad_probability(energy, zcr, spectral)

    # Should return array of probabilities
    assert isinstance(probability, np.ndarray)
    assert len(probability) == 4
    assert all(0 <= p <= 1 for p in probability)

    # High energy + low ZCR + medium spectral = high probability
    # Low energy + high ZCR + medium spectral = low probability
    assert probability[0] > probability[1]
    assert probability[2] > probability[3]
