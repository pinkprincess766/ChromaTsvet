"""Adversarial structured-noise tests for peak detection."""

from __future__ import annotations

import numpy as np

import spectrometer_rust
from tests.support.adversarial_noise import with_structured_noise
from tests.support.synthetic_spectra import (
    clean_multiple_tones_case,
    clean_single_tone_case,
    create_synthetic_case,
    evaluate_case,
)


BASELINE_PROCESS_KWARGS = {
    "filter_type": "none",
    "window_type": "hann",
    "threshold": 0.01,
    "baseline": False,
    "prominence": 0.0,
    "distance": 1,
    "min_snr": 0.0,
}


def process_kwargs(**overrides):
    return {**BASELINE_PROCESS_KWARGS, **overrides}


def assert_quality(evaluated: dict, *, min_recall: float = 1.0, max_fp: int = 1) -> None:
    metrics = evaluated["metrics"]
    assert metrics["recall"] >= min_recall, evaluated
    assert metrics["fp"] <= max_fp, evaluated
    assert metrics["rmse_hz"] <= metrics["tolerance_hz"], evaluated


def assert_result_is_finite(evaluated: dict) -> None:
    result = evaluated["result"]
    spectrum = np.asarray(result["spectrum"], dtype=float)
    frequency_axis = np.asarray(result["frequency_axis"], dtype=float)
    assert np.all(np.isfinite(spectrum))
    assert np.all(np.isfinite(frequency_axis))
    for peak in result["peaks"]:
        assert np.isfinite(float(peak.frequency))
        assert np.isfinite(float(peak.intensity))
        assert np.isfinite(float(peak.snr))


def test_pink_noise_floor_preserves_expected_tones_without_many_false_peaks():
    case = with_structured_noise(
        clean_multiple_tones_case(),
        pink_scale=0.35,
        seed=101,
        description="multiple tones with deterministic pink noise floor",
    )

    evaluated = evaluate_case(
        case,
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.015, prominence=0.08, min_snr=1.8),
    )

    assert_quality(evaluated, max_fp=1)
    assert_result_is_finite(evaluated)


def test_low_frequency_baseline_wander_does_not_move_spectral_peak():
    case = with_structured_noise(
        clean_single_tone_case(),
        baseline_wander_amplitude=1.4,
        baseline_wander_frequency=0.5,
        description="single tone with low-frequency baseline wander",
    )

    evaluated = evaluate_case(
        case,
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.01, baseline=True, baseline_method="improved"),
    )

    assert_quality(evaluated, max_fp=1)
    assert_result_is_finite(evaluated)


def test_narrowband_interference_near_peak_is_not_promoted_over_true_tone():
    case = with_structured_noise(
        clean_single_tone_case(),
        interference_frequency=132.0,
        interference_amplitude=0.16,
        pink_scale=0.08,
        seed=202,
        description="single tone with nearby narrowband interference",
    )

    evaluated = evaluate_case(
        case,
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.006, prominence=0.06, min_snr=1.5),
    )

    assert_quality(evaluated, max_fp=1)
    assert_result_is_finite(evaluated)


def test_combined_structured_noise_keeps_release_floor_under_strict_filters():
    case = with_structured_noise(
        create_synthetic_case(
            [96.0, 224.0, 352.0],
            amplitudes=[1.0, 0.65, 0.35],
            description="three tones before structured perturbations",
        ),
        pink_scale=0.28,
        baseline_wander_amplitude=0.9,
        baseline_wander_frequency=0.65,
        interference_frequency=180.0,
        interference_amplitude=0.12,
        seed=303,
        description="three tones with pink noise, baseline wander, and interference",
    )

    evaluated = evaluate_case(
        case,
        spectrometer_rust.process_signal,
        **process_kwargs(
            threshold=0.012,
            prominence=0.06,
            min_snr=1.6,
            baseline=True,
            baseline_method="improved",
        ),
    )

    assert_quality(evaluated, max_fp=2)
    assert_result_is_finite(evaluated)
