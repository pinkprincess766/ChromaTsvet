"""Resolution-limit tests for peak detection behavior."""

from __future__ import annotations

import math

import numpy as np
import pytest

import spectrometer_rust
from tests.support.synthetic_spectra import create_synthetic_case, evaluate_case


BASELINE_PROCESS_KWARGS = {
    "filter_type": "none",
    "window_type": "hann",
    "threshold": 0.001,
    "baseline": False,
    "prominence": 0.0,
    "distance": 1,
    "min_snr": 0.0,
}


def process_kwargs(**overrides):
    return {**BASELINE_PROCESS_KWARGS, **overrides}


def finite_peak_frequencies(result: dict) -> list[float]:
    frequencies: list[float] = []
    for peak in result["peaks"]:
        frequency = float(peak.frequency)
        if math.isfinite(frequency):
            frequencies.append(frequency)
    return frequencies


def assert_frequency_axis_bin_width(result: dict, *, sample_rate: float, source_len: int) -> None:
    frequency_axis = np.asarray(result["frequency_axis"], dtype=float)
    assert frequency_axis.size == len(result["spectrum"])
    assert frequency_axis[0] == pytest.approx(0.0)
    np.testing.assert_allclose(
        np.diff(frequency_axis),
        sample_rate / source_len,
        rtol=1e-12,
        atol=1e-12,
    )


def test_sub_bin_peak_cluster_stays_bounded_instead_of_hallucinating_resolution():
    case = create_synthetic_case(
        [128.0, 128.3],
        amplitudes=[1.0, 0.8],
        duration=2.0,
        description="two peaks closer than one FFT bin",
    )

    result = spectrometer_rust.process_signal(
        data=case.signal.tolist(),
        sample_rate=case.sample_rate,
        **process_kwargs(threshold=0.0005, prominence=0.0005),
    )

    frequencies = finite_peak_frequencies(result)
    cluster_hits = [frequency for frequency in frequencies if 126.0 <= frequency <= 130.0]

    assert_frequency_axis_bin_width(
        result,
        sample_rate=case.sample_rate,
        source_len=len(case.signal),
    )
    assert len(cluster_hits) >= 1
    assert len(cluster_hits) <= 2
    assert len(frequencies) <= 3


def test_short_signal_with_close_peaks_keeps_false_resolution_bounded():
    case = create_synthetic_case(
        [128.0, 131.0],
        amplitudes=[1.0, 0.8],
        duration=0.5,
        description="short signal with close peaks and coarse FFT bins",
    )

    result = spectrometer_rust.process_signal(
        data=case.signal.tolist(),
        sample_rate=case.sample_rate,
        **process_kwargs(threshold=0.0008, prominence=0.001),
    )

    frequencies = finite_peak_frequencies(result)
    cluster_hits = [frequency for frequency in frequencies if 124.0 <= frequency <= 136.0]

    assert_frequency_axis_bin_width(
        result,
        sample_rate=case.sample_rate,
        source_len=len(case.signal),
    )
    assert cluster_hits
    assert len(cluster_hits) <= 3
    assert len(frequencies) <= 4


def test_min_distance_intentionally_suppresses_unresolvable_nearby_peaks():
    case = create_synthetic_case(
        [128.0, 132.0],
        amplitudes=[1.0, 0.85],
        duration=4.0,
        description="close peaks under explicit minimum-distance suppression",
    )

    result = spectrometer_rust.process_signal(
        data=case.signal.tolist(),
        sample_rate=case.sample_rate,
        **process_kwargs(threshold=0.0008, prominence=0.001, distance=32),
    )

    frequencies = finite_peak_frequencies(result)
    cluster_hits = [frequency for frequency in frequencies if 124.0 <= frequency <= 136.0]

    assert len(cluster_hits) == 1
    assert len(frequencies) <= 2


def test_longer_signal_resolves_close_peaks_that_short_signal_cannot_claim():
    case = create_synthetic_case(
        [128.0, 129.0],
        amplitudes=[1.0, 0.8],
        duration=8.0,
        description="long signal resolves one-Hz-separated peaks",
    )

    evaluated = evaluate_case(
        case,
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.0005, prominence=0.0005, distance=1),
    )

    metrics = evaluated["metrics"]
    assert metrics["recall"] == 1.0, evaluated
    assert metrics["fp"] == 0, evaluated
    assert metrics["rmse_hz"] <= metrics["tolerance_hz"], evaluated
    assert_frequency_axis_bin_width(
        evaluated["result"],
        sample_rate=case.sample_rate,
        source_len=len(case.signal),
    )
