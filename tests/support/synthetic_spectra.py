"""Synthetic spectrum harness for full-pipeline peak detection tests.

The Rust pipeline accepts a time-domain signal and computes the FFT internally,
so these helpers generate deterministic time-domain signals with known spectral
frequencies instead of injecting ready-made spectrum peaks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Callable

import numpy as np
from numpy.typing import NDArray


DEFAULT_SAMPLE_RATE = 1024.0
DEFAULT_DURATION_SECONDS = 2.0
DEFAULT_SEED = 42


@dataclass(frozen=True)
class SyntheticPeak:
    """Ground-truth sinusoidal component represented as a spectral peak."""

    frequency: float
    amplitude: float = 1.0
    phase: float = 0.0


@dataclass(frozen=True)
class SyntheticSpectrumCase:
    """A deterministic time-domain test case with spectral ground truth."""

    signal: NDArray[np.float64]
    expected_peaks: tuple[SyntheticPeak, ...]
    sample_rate: float
    description: str
    duration: float = field(init=False)

    def __post_init__(self) -> None:
        if self.signal.ndim != 1:
            raise ValueError("synthetic signal must be one-dimensional")
        if not math.isfinite(self.sample_rate) or self.sample_rate <= 0.0:
            raise ValueError("sample_rate must be a positive finite number")

        object.__setattr__(self, "duration", len(self.signal) / self.sample_rate)
        validate_frequencies_below_nyquist(
            [peak.frequency for peak in self.expected_peaks],
            self.sample_rate,
        )

    @property
    def expected_frequencies(self) -> list[float]:
        return [peak.frequency for peak in self.expected_peaks]

    @property
    def bin_width_hz(self) -> float:
        if len(self.signal) == 0:
            return 0.0
        return self.sample_rate / len(self.signal)


@dataclass(frozen=True)
class PeakMatch:
    """One matched detected/expected peak pair."""

    detected_frequency: float
    expected_frequency: float
    error_hz: float


@dataclass(frozen=True)
class PeakMatchMetrics:
    """Peak matching metrics for a synthetic case."""

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    rmse_hz: float
    tolerance_hz: float
    detected_count: int
    expected_count: int
    matches: tuple[PeakMatch, ...]
    unmatched_detected: tuple[float, ...]
    unmatched_expected: tuple[float, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "rmse_hz": round(self.rmse_hz, 6),
            "tolerance_hz": round(self.tolerance_hz, 6),
            "detected_count": self.detected_count,
            "expected_count": self.expected_count,
            "matches": [
                {
                    "detected_frequency": round(match.detected_frequency, 6),
                    "expected_frequency": round(match.expected_frequency, 6),
                    "error_hz": round(match.error_hz, 6),
                }
                for match in self.matches
            ],
            "unmatched_detected": [round(value, 6) for value in self.unmatched_detected],
            "unmatched_expected": [round(value, 6) for value in self.unmatched_expected],
        }


def validate_frequencies_below_nyquist(
    frequencies: list[float] | tuple[float, ...],
    sample_rate: float,
) -> None:
    if not math.isfinite(sample_rate) or sample_rate <= 0.0:
        raise ValueError("sample_rate must be a positive finite number")

    nyquist = sample_rate / 2.0
    for frequency in frequencies:
        if not math.isfinite(frequency) or frequency <= 0.0:
            raise ValueError("frequencies must be positive finite numbers")
        if frequency >= nyquist:
            raise ValueError(
                f"frequency {frequency:g} Hz must be below Nyquist ({nyquist:g} Hz)"
            )


def generate_time_domain_signal(
    peaks: list[SyntheticPeak] | tuple[SyntheticPeak, ...],
    *,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    duration: float = DEFAULT_DURATION_SECONDS,
    noise_level: float = 0.0,
    baseline_slope: float = 0.0,
    baseline_offset: float = 0.0,
    spike_times_amplitudes: list[tuple[float, float]] | None = None,
    seed: int | None = DEFAULT_SEED,
) -> NDArray[np.float64]:
    """Generate a deterministic time-domain signal from spectral components."""
    validate_frequencies_below_nyquist(
        [peak.frequency for peak in peaks],
        sample_rate,
    )
    if not math.isfinite(duration) or duration <= 0.0:
        raise ValueError("duration must be a positive finite number")
    if not math.isfinite(noise_level) or noise_level < 0.0:
        raise ValueError("noise_level must be a non-negative finite number")
    if not math.isfinite(baseline_slope) or not math.isfinite(baseline_offset):
        raise ValueError("baseline parameters must be finite")

    sample_count = int(round(sample_rate * duration))
    if sample_count <= 0:
        raise ValueError("synthetic case must contain at least one sample")

    time_axis = np.arange(sample_count, dtype=np.float64) / sample_rate
    signal = np.full(sample_count, baseline_offset, dtype=np.float64)

    for peak in peaks:
        if not math.isfinite(peak.amplitude) or not math.isfinite(peak.phase):
            raise ValueError("peak amplitude and phase must be finite")
        signal += peak.amplitude * np.sin(
            2.0 * np.pi * peak.frequency * time_axis + peak.phase
        )

    if abs(baseline_slope) > 1e-12:
        signal += baseline_slope * time_axis

    if noise_level > 0.0:
        rng = np.random.default_rng(seed)
        signal += rng.normal(0.0, noise_level, size=sample_count)

    if spike_times_amplitudes:
        for time_sec, amplitude in spike_times_amplitudes:
            if not math.isfinite(time_sec) or not math.isfinite(amplitude):
                raise ValueError("spike time and amplitude must be finite")
            index = int(round(time_sec * sample_rate))
            if 0 <= index < sample_count:
                signal[index] += amplitude

    return signal.astype(np.float64, copy=False)


def create_synthetic_case(
    frequencies: list[float] | tuple[float, ...],
    *,
    amplitudes: list[float] | tuple[float, ...] | None = None,
    phases: list[float] | tuple[float, ...] | None = None,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    duration: float = DEFAULT_DURATION_SECONDS,
    noise_level: float = 0.0,
    baseline_slope: float = 0.0,
    baseline_offset: float = 0.0,
    spike_times_amplitudes: list[tuple[float, float]] | None = None,
    description: str = "",
    seed: int | None = DEFAULT_SEED,
) -> SyntheticSpectrumCase:
    """Create a deterministic synthetic case and its frequency ground truth."""
    if amplitudes is None:
        amplitudes = [1.0] * len(frequencies)
    if phases is None:
        phases = [0.0] * len(frequencies)
    if len(amplitudes) != len(frequencies):
        raise ValueError("amplitudes length must match frequencies length")
    if len(phases) != len(frequencies):
        raise ValueError("phases length must match frequencies length")

    expected_peaks = tuple(
        SyntheticPeak(float(frequency), float(amplitude), float(phase))
        for frequency, amplitude, phase in zip(frequencies, amplitudes, phases)
    )
    signal = generate_time_domain_signal(
        expected_peaks,
        sample_rate=sample_rate,
        duration=duration,
        noise_level=noise_level,
        baseline_slope=baseline_slope,
        baseline_offset=baseline_offset,
        spike_times_amplitudes=spike_times_amplitudes,
        seed=seed,
    )

    return SyntheticSpectrumCase(
        signal=signal,
        expected_peaks=expected_peaks,
        sample_rate=sample_rate,
        description=description or f"{len(expected_peaks)} tone(s)",
    )


def clean_single_tone_case() -> SyntheticSpectrumCase:
    return create_synthetic_case(
        [128.0],
        description="clean single tone at 128 Hz",
    )


def clean_multiple_tones_case() -> SyntheticSpectrumCase:
    return create_synthetic_case(
        [128.0, 256.0, 384.0],
        amplitudes=[1.0, 0.75, 0.55],
        description="clean multiple tones below Nyquist",
    )


def close_frequencies_case() -> SyntheticSpectrumCase:
    return create_synthetic_case(
        [128.0, 136.0],
        amplitudes=[1.0, 0.85],
        description="close frequencies with 8 Hz separation",
    )


def noisy_low_snr_case() -> SyntheticSpectrumCase:
    return create_synthetic_case(
        [128.0, 256.0],
        amplitudes=[1.0, 0.75],
        noise_level=0.35,
        description="noisy low-SNR signal with two tones",
    )


def pure_noise_case() -> SyntheticSpectrumCase:
    return create_synthetic_case(
        [],
        noise_level=0.6,
        description="pure noise false-positive control",
    )


def baseline_drift_case() -> SyntheticSpectrumCase:
    return create_synthetic_case(
        [128.0],
        baseline_slope=0.02,
        baseline_offset=0.25,
        description="tone with linear time-domain baseline drift",
    )


def spiky_artifacts_case() -> SyntheticSpectrumCase:
    return create_synthetic_case(
        [200.0],
        spike_times_amplitudes=[(0.5, 8.0), (1.2, -6.0)],
        description="tone with strong impulse artifacts",
    )


def hostile_nan_case() -> SyntheticSpectrumCase:
    case = create_synthetic_case([128.0], description="hostile input with NaN segment")
    signal = case.signal.copy()
    signal[150:170] = np.nan
    return SyntheticSpectrumCase(
        signal=signal,
        expected_peaks=case.expected_peaks,
        sample_rate=case.sample_rate,
        description=case.description,
    )


def hostile_inf_case() -> SyntheticSpectrumCase:
    case = create_synthetic_case([128.0], description="hostile input with Inf samples")
    signal = case.signal.copy()
    signal[300] = np.inf
    signal[400] = -np.inf
    return SyntheticSpectrumCase(
        signal=signal,
        expected_peaks=case.expected_peaks,
        sample_rate=case.sample_rate,
        description=case.description,
    )


def finite_peak_frequencies(peaks: list[Any]) -> list[float]:
    frequencies: list[float] = []
    for peak in peaks:
        try:
            frequency = float(getattr(peak, "frequency"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(frequency):
            frequencies.append(frequency)
    return frequencies


def match_peaks(
    detected_frequencies: list[float],
    expected_frequencies: list[float],
    tolerance_hz: float,
) -> PeakMatchMetrics:
    """One-to-one peak matching by increasing frequency error."""
    finite_detected = sorted(
        float(frequency)
        for frequency in detected_frequencies
        if math.isfinite(float(frequency))
    )
    finite_expected = sorted(
        float(frequency)
        for frequency in expected_frequencies
        if math.isfinite(float(frequency))
    )
    if not math.isfinite(tolerance_hz) or tolerance_hz < 0.0:
        raise ValueError("tolerance_hz must be a non-negative finite number")

    candidates: list[tuple[float, int, int]] = []
    for detected_index, detected in enumerate(finite_detected):
        for expected_index, expected in enumerate(finite_expected):
            error = abs(detected - expected)
            if error <= tolerance_hz:
                candidates.append((error, detected_index, expected_index))

    used_detected: set[int] = set()
    used_expected: set[int] = set()
    matches: list[PeakMatch] = []
    for error, detected_index, expected_index in sorted(candidates):
        if detected_index in used_detected or expected_index in used_expected:
            continue
        used_detected.add(detected_index)
        used_expected.add(expected_index)
        matches.append(
            PeakMatch(
                detected_frequency=finite_detected[detected_index],
                expected_frequency=finite_expected[expected_index],
                error_hz=error,
            )
        )

    tp = len(matches)
    fp = len(finite_detected) - tp
    fn = len(finite_expected) - tp
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    squared_errors = [match.error_hz**2 for match in matches]
    rmse = math.sqrt(sum(squared_errors) / len(squared_errors)) if squared_errors else 0.0

    return PeakMatchMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        tp=tp,
        fp=fp,
        fn=fn,
        rmse_hz=rmse,
        tolerance_hz=tolerance_hz,
        detected_count=len(finite_detected),
        expected_count=len(finite_expected),
        matches=tuple(matches),
        unmatched_detected=tuple(
            frequency
            for index, frequency in enumerate(finite_detected)
            if index not in used_detected
        ),
        unmatched_expected=tuple(
            frequency
            for index, frequency in enumerate(finite_expected)
            if index not in used_expected
        ),
    )


def tolerance_from_case(
    case: SyntheticSpectrumCase,
    result: dict[str, Any],
    explicit_tolerance_hz: float | None = None,
) -> float:
    if explicit_tolerance_hz is not None:
        if not math.isfinite(explicit_tolerance_hz) or explicit_tolerance_hz < 0.0:
            raise ValueError("explicit tolerance must be a non-negative finite number")
        return explicit_tolerance_hz

    frequency_axis = result.get("frequency_axis", [])
    if len(frequency_axis) >= 2:
        bin_width = abs(float(frequency_axis[1]) - float(frequency_axis[0]))
    else:
        bin_width = case.bin_width_hz
    return max(1.5 * bin_width, 1e-9)


def evaluate_case(
    case: SyntheticSpectrumCase,
    process_signal: Callable[..., dict[str, Any]],
    frequency_tolerance_hz: float | None = None,
    **process_kwargs: Any,
) -> dict[str, Any]:
    """Run ``process_signal`` and return output plus strict matching metrics."""
    result: dict[str, Any] = process_signal(
        data=case.signal.tolist(),
        sample_rate=case.sample_rate,
        **process_kwargs,
    )
    detected_frequencies = finite_peak_frequencies(result.get("peaks", []))
    tolerance_hz = tolerance_from_case(case, result, frequency_tolerance_hz)
    metrics = match_peaks(
        detected_frequencies,
        case.expected_frequencies,
        tolerance_hz,
    )

    return {
        "description": case.description,
        "result": result,
        "metrics": metrics.as_dict(),
        "detected_frequencies": [round(frequency, 6) for frequency in detected_frequencies],
        "expected_frequencies": case.expected_frequencies,
        "tolerance_used_hz": tolerance_hz,
    }
