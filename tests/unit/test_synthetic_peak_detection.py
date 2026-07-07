"""Synthetic full-pipeline tests for Rust peak detection."""

from __future__ import annotations

import math

import numpy as np
import pytest

import spectrometer_rust
from tests.support.synthetic_spectra import (
    baseline_drift_case,
    clean_multiple_tones_case,
    clean_single_tone_case,
    close_frequencies_case,
    create_synthetic_case,
    evaluate_case,
    hostile_inf_case,
    hostile_nan_case,
    match_peaks,
    noisy_low_snr_case,
    pure_noise_case,
    spiky_artifacts_case,
)


BASELINE_PROCESS_KWARGS = {
    "filter_type": "none",
    "window_type": "rectangular",
    "threshold": 0.01,
    "baseline": False,
    "prominence": 0.0,
    "distance": 1,
    "min_snr": 0.0,
}


def process_kwargs(**overrides):
    return {**BASELINE_PROCESS_KWARGS, **overrides}


def assert_finite_pipeline_result(result: dict) -> None:
    spectrum = np.asarray(result["spectrum"], dtype=float)
    frequency_axis = np.asarray(result["frequency_axis"], dtype=float)
    assert spectrum.size > 0
    assert frequency_axis.size == spectrum.size
    assert np.all(np.isfinite(spectrum))
    assert np.all(np.isfinite(frequency_axis))
    for peak in result["peaks"]:
        assert math.isfinite(float(peak.frequency))
        assert math.isfinite(float(peak.intensity))
        assert math.isfinite(float(peak.width_hz))
        assert math.isfinite(float(peak.area))
        assert math.isfinite(float(peak.snr))


def assert_metrics(
    evaluated: dict,
    *,
    min_precision: float,
    min_recall: float,
    max_false_positives: int,
) -> None:
    metrics = evaluated["metrics"]
    assert metrics["precision"] >= min_precision, evaluated
    assert metrics["recall"] >= min_recall, evaluated
    assert metrics["fp"] <= max_false_positives, evaluated
    assert metrics["fn"] == metrics["expected_count"] - metrics["tp"]
    assert metrics["rmse_hz"] <= metrics["tolerance_hz"], evaluated


def test_clean_single_tone_is_detected_without_false_positives():
    evaluated = evaluate_case(
        clean_single_tone_case(),
        spectrometer_rust.process_signal,
        **process_kwargs(),
    )

    assert_metrics(
        evaluated,
        min_precision=1.0,
        min_recall=1.0,
        max_false_positives=0,
    )
    assert_finite_pipeline_result(evaluated["result"])


def test_clean_multiple_tones_below_nyquist_are_all_detected():
    evaluated = evaluate_case(
        clean_multiple_tones_case(),
        spectrometer_rust.process_signal,
        **process_kwargs(),
    )

    assert_metrics(
        evaluated,
        min_precision=1.0,
        min_recall=1.0,
        max_false_positives=0,
    )


def test_close_frequencies_are_resolved_with_bin_width_tolerance():
    evaluated = evaluate_case(
        close_frequencies_case(),
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.005, distance=1),
    )

    assert_metrics(
        evaluated,
        min_precision=1.0,
        min_recall=1.0,
        max_false_positives=0,
    )


def test_noisy_low_snr_keeps_expected_peaks_with_snr_and_prominence_filters():
    evaluated = evaluate_case(
        noisy_low_snr_case(),
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.02, prominence=0.08, min_snr=2.0),
    )

    assert_metrics(
        evaluated,
        min_precision=1.0,
        min_recall=1.0,
        max_false_positives=0,
    )


def test_pure_noise_has_bounded_false_positives_under_strict_filters():
    evaluated = evaluate_case(
        pure_noise_case(),
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.08, prominence=0.2, min_snr=3.0),
    )

    metrics = evaluated["metrics"]
    assert metrics["tp"] == 0
    assert metrics["fn"] == 0
    # The current Rust semantics intentionally keep the global maximum as a
    # fallback, so pure noise may still produce one finite "least bad" peak.
    assert metrics["fp"] <= 1, evaluated


def test_baseline_drift_still_preserves_main_tone():
    evaluated = evaluate_case(
        baseline_drift_case(),
        spectrometer_rust.process_signal,
        **process_kwargs(baseline=True, baseline_method="improved", threshold=0.01),
    )

    assert_metrics(
        evaluated,
        min_precision=1.0,
        min_recall=1.0,
        max_false_positives=0,
    )


def test_spiky_artifacts_do_not_hide_main_tone_or_emit_many_false_peaks():
    evaluated = evaluate_case(
        spiky_artifacts_case(),
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.03, prominence=0.08, min_snr=1.5),
    )

    assert_metrics(
        evaluated,
        min_precision=1.0,
        min_recall=1.0,
        max_false_positives=0,
    )
    assert_finite_pipeline_result(evaluated["result"])


def test_hostile_nan_input_returns_only_finite_outputs():
    evaluated = evaluate_case(
        hostile_nan_case(),
        spectrometer_rust.process_signal,
        **process_kwargs(),
    )

    assert_finite_pipeline_result(evaluated["result"])
    assert evaluated["metrics"]["recall"] == 1.0


def test_hostile_inf_input_returns_only_finite_outputs():
    evaluated = evaluate_case(
        hostile_inf_case(),
        spectrometer_rust.process_signal,
        **process_kwargs(),
    )

    assert_finite_pipeline_result(evaluated["result"])
    assert evaluated["metrics"]["recall"] == 1.0


def test_frequency_at_or_above_nyquist_is_rejected():
    with pytest.raises(ValueError, match="below Nyquist"):
        create_synthetic_case([512.0], sample_rate=1024.0)


def test_matcher_uses_one_to_one_pairs_and_true_rmse():
    metrics = match_peaks(
        detected_frequencies=[99.0, 101.0, 104.0],
        expected_frequencies=[100.0, 105.0],
        tolerance_hz=2.0,
    )

    assert metrics.tp == 2
    assert metrics.fp == 1
    assert metrics.fn == 0
    assert metrics.rmse_hz == pytest.approx(1.0)
