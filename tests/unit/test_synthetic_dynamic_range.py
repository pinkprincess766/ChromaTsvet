"""Adversarial dynamic-range tests for peak detection."""

from __future__ import annotations

import numpy as np

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


def assert_detects_all_expected(evaluated: dict, *, max_fp: int = 0) -> None:
    metrics = evaluated["metrics"]
    assert metrics["recall"] == 1.0, evaluated
    assert metrics["fp"] <= max_fp, evaluated
    assert metrics["rmse_hz"] <= metrics["tolerance_hz"], evaluated


def assert_peak_outputs_are_finite(evaluated: dict) -> None:
    for peak in evaluated["result"]["peaks"]:
        assert np.isfinite(float(peak.frequency))
        assert np.isfinite(float(peak.intensity))
        assert np.isfinite(float(peak.area))
        assert np.isfinite(float(peak.snr))


def test_two_percent_peak_is_detected_when_well_separated_from_dominant_peak():
    case = create_synthetic_case(
        [96.0, 352.0],
        amplitudes=[1.0, 0.02],
        duration=4.0,
        description="1:0.02 dynamic range with separated peaks",
    )

    evaluated = evaluate_case(
        case,
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.0008, prominence=0.0015),
    )

    assert_detects_all_expected(evaluated)
    assert_peak_outputs_are_finite(evaluated)


def test_weak_peak_near_strong_peak_survives_prominence_filtering():
    case = create_synthetic_case(
        [128.0, 144.0],
        amplitudes=[1.0, 0.035],
        duration=4.0,
        description="weak peak near dominant peak",
    )

    evaluated = evaluate_case(
        case,
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.0008, prominence=0.0015, distance=1),
    )

    assert_detects_all_expected(evaluated)
    assert_peak_outputs_are_finite(evaluated)


def test_multiple_weak_peaks_are_not_lost_after_area_normalization():
    case = create_synthetic_case(
        [96.0, 224.0, 384.0],
        amplitudes=[1.0, 0.05, 0.02],
        duration=4.0,
        description="multiple weak peaks under area normalization",
    )

    evaluated = evaluate_case(
        case,
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.0005, prominence=0.0005, normalize=True),
    )

    assert_detects_all_expected(evaluated)
    assert_peak_outputs_are_finite(evaluated)


def test_one_percent_peak_is_tracked_as_nightmare_regression_floor():
    case = create_synthetic_case(
        [128.0, 320.0],
        amplitudes=[1.0, 0.01],
        duration=8.0,
        description="1:0.01 dynamic range nightmare floor",
    )

    evaluated = evaluate_case(
        case,
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.0002, prominence=0.0002),
    )

    assert_detects_all_expected(evaluated)
    assert_peak_outputs_are_finite(evaluated)
