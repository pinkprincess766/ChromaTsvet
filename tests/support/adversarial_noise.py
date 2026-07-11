"""Deterministic structured-noise helpers for synthetic spectrum tests."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from tests.support.synthetic_spectra import SyntheticSpectrumCase


def pink_noise(
    sample_count: int,
    *,
    scale: float,
    seed: int = 4242,
) -> NDArray[np.float64]:
    """Create deterministic 1/f-like noise with a controlled standard deviation."""
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    if not math.isfinite(scale) or scale < 0.0:
        raise ValueError("scale must be a non-negative finite number")
    if scale == 0.0:
        return np.zeros(sample_count, dtype=np.float64)

    rng = np.random.default_rng(seed)
    frequency_count = sample_count // 2 + 1
    magnitudes = np.ones(frequency_count, dtype=np.float64)
    if frequency_count > 1:
        bins = np.arange(1, frequency_count, dtype=np.float64)
        magnitudes[1:] = 1.0 / np.sqrt(bins)

    phases = rng.uniform(0.0, 2.0 * np.pi, size=frequency_count)
    spectrum = magnitudes * np.exp(1j * phases)
    spectrum[0] = 0.0
    noise = np.fft.irfft(spectrum, n=sample_count).astype(np.float64, copy=False)
    std = float(np.std(noise))
    if std <= 0.0 or not math.isfinite(std):
        return np.zeros(sample_count, dtype=np.float64)
    return noise / std * scale


def sinusoid(
    sample_count: int,
    sample_rate: float,
    *,
    frequency: float,
    amplitude: float,
    phase: float = 0.0,
) -> NDArray[np.float64]:
    """Create one deterministic sinusoidal perturbation."""
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    for value, name in (
        (sample_rate, "sample_rate"),
        (frequency, "frequency"),
        (amplitude, "amplitude"),
        (phase, "phase"),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if sample_rate <= 0.0:
        raise ValueError("sample_rate must be positive")
    if frequency <= 0.0 or frequency >= sample_rate / 2.0:
        raise ValueError("frequency must be inside the open Nyquist interval")

    time_axis = np.arange(sample_count, dtype=np.float64) / sample_rate
    return amplitude * np.sin(2.0 * np.pi * frequency * time_axis + phase)


def with_structured_noise(
    case: SyntheticSpectrumCase,
    *,
    pink_scale: float = 0.0,
    baseline_wander_amplitude: float = 0.0,
    baseline_wander_frequency: float = 0.75,
    interference_frequency: float | None = None,
    interference_amplitude: float = 0.0,
    seed: int = 4242,
    description: str | None = None,
) -> SyntheticSpectrumCase:
    """Return a copy of ``case`` with deterministic non-white perturbations."""
    signal = case.signal.astype(np.float64, copy=True)
    sample_count = len(signal)

    signal += pink_noise(sample_count, scale=pink_scale, seed=seed)

    if baseline_wander_amplitude:
        signal += sinusoid(
            sample_count,
            case.sample_rate,
            frequency=baseline_wander_frequency,
            amplitude=baseline_wander_amplitude,
            phase=0.3,
        )

    if interference_frequency is not None and interference_amplitude:
        signal += sinusoid(
            sample_count,
            case.sample_rate,
            frequency=interference_frequency,
            amplitude=interference_amplitude,
            phase=1.1,
        )

    return SyntheticSpectrumCase(
        signal=signal,
        expected_peaks=case.expected_peaks,
        sample_rate=case.sample_rate,
        description=description or f"{case.description} with structured noise",
    )
