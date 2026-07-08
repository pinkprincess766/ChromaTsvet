"""Synthetic full-pipeline tests for Rust peak detection."""

from __future__ import annotations

import math

import numpy as np
import pytest

import spectrometer_rust
from tests.support.synthetic_spectra import (
    PeakDetectionQualityCase,
    baseline_drift_case,
    clean_multiple_tones_case,
    clean_single_tone_case,
    close_frequencies_case,
    create_synthetic_case,
    evaluate_case,
    evaluate_quality_suite,
    fractional_bin_case,
    high_sample_rate_case,
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


QUALITY_BENCHMARK_CASES = (
    PeakDetectionQualityCase(
        name="clean-single-tone",
        case=clean_single_tone_case(),
        process_kwargs=process_kwargs(),
        min_precision=1.0,
        min_recall=1.0,
        min_f1=1.0,
        max_false_positives=0,
        max_rmse_hz=0.0,
    ),
    PeakDetectionQualityCase(
        name="clean-multiple-tones",
        case=clean_multiple_tones_case(),
        process_kwargs=process_kwargs(),
        min_precision=1.0,
        min_recall=1.0,
        min_f1=1.0,
        max_false_positives=0,
        max_rmse_hz=0.0,
    ),
    PeakDetectionQualityCase(
        name="close-frequencies",
        case=close_frequencies_case(),
        process_kwargs=process_kwargs(threshold=0.005, distance=1),
        min_precision=1.0,
        min_recall=1.0,
        min_f1=1.0,
        max_false_positives=0,
        max_rmse_hz=0.0,
    ),
    PeakDetectionQualityCase(
        name="fractional-bin-tone",
        case=fractional_bin_case(),
        process_kwargs=process_kwargs(threshold=0.001),
        min_precision=1.0,
        min_recall=1.0,
        min_f1=1.0,
        max_false_positives=0,
        max_rmse_hz=0.5,
    ),
    PeakDetectionQualityCase(
        name="noisy-low-snr",
        case=noisy_low_snr_case(),
        process_kwargs=process_kwargs(threshold=0.02, prominence=0.08, min_snr=2.0),
        min_precision=1.0,
        min_recall=1.0,
        min_f1=1.0,
        max_false_positives=0,
        max_rmse_hz=0.0,
    ),
    PeakDetectionQualityCase(
        name="baseline-drift",
        case=baseline_drift_case(),
        process_kwargs=process_kwargs(
            baseline=True,
            baseline_method="improved",
            threshold=0.01,
        ),
        min_precision=1.0,
        min_recall=1.0,
        min_f1=1.0,
        max_false_positives=0,
        max_rmse_hz=0.0,
    ),
    PeakDetectionQualityCase(
        name="spiky-artifacts",
        case=spiky_artifacts_case(),
        process_kwargs=process_kwargs(threshold=0.03, prominence=0.08, min_snr=1.5),
        min_precision=1.0,
        min_recall=1.0,
        min_f1=1.0,
        max_false_positives=0,
        max_rmse_hz=0.0,
    ),
    PeakDetectionQualityCase(
        name="high-sample-rate",
        case=high_sample_rate_case(),
        process_kwargs=process_kwargs(threshold=0.005),
        min_precision=1.0,
        min_recall=1.0,
        min_f1=1.0,
        max_false_positives=0,
        max_rmse_hz=0.0,
    ),
)


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


def assert_frequency_axis_invariants(result: dict, *, sample_rate: float, source_len: int) -> None:
    spectrum = np.asarray(result["spectrum"], dtype=float)
    frequency_axis = np.asarray(result["frequency_axis"], dtype=float)
    bin_width = sample_rate / source_len

    assert frequency_axis.size == spectrum.size
    assert frequency_axis[0] == pytest.approx(0.0)
    assert np.all(np.diff(frequency_axis) > 0.0)
    np.testing.assert_allclose(np.diff(frequency_axis), bin_width, rtol=1e-12, atol=1e-12)
    assert frequency_axis[-1] <= sample_rate / 2.0 + bin_width * 0.5

    for peak in result["peaks"]:
        assert 0.0 <= peak.frequency <= sample_rate / 2.0 + bin_width * 0.5
        assert peak.frequency == pytest.approx(peak.position * bin_width)
        assert peak.width_hz == pytest.approx(peak.width * bin_width)


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


def leakage_energy_ratio(result: dict, *, main_lobe_half_width_bins: int = 2) -> float:
    spectrum = np.asarray(result["spectrum"], dtype=float)
    peak = max(result["peaks"], key=lambda candidate: candidate.intensity)
    center = int(round(float(peak.position)))
    main_lobe = np.zeros_like(spectrum, dtype=bool)
    left = max(0, center - main_lobe_half_width_bins)
    right = min(spectrum.size, center + main_lobe_half_width_bins + 1)
    main_lobe[left:right] = True

    total_energy = float(np.sum(spectrum**2))
    if total_energy <= 0.0:
        return 0.0
    leakage_energy = float(np.sum(spectrum[~main_lobe] ** 2))
    return leakage_energy / total_energy


def test_peak_detection_quality_benchmark_suite_meets_release_floor():
    suite = evaluate_quality_suite(
        QUALITY_BENCHMARK_CASES,
        spectrometer_rust.process_signal,
    )

    assert suite.failed_cases == (), suite.as_dict()
    assert suite.precision >= 1.0, suite.as_dict()
    assert suite.recall >= 1.0, suite.as_dict()
    assert suite.f1 >= 1.0, suite.as_dict()
    assert suite.fp == 0, suite.as_dict()


def test_peak_detection_quality_suite_preserves_frequency_invariants():
    suite = evaluate_quality_suite(
        QUALITY_BENCHMARK_CASES,
        spectrometer_rust.process_signal,
    )

    for evaluation in suite.evaluations:
        case = evaluation.quality_case.case
        assert_finite_pipeline_result(evaluation.result)
        assert_frequency_axis_invariants(
            evaluation.result,
            sample_rate=case.sample_rate,
            source_len=len(case.signal),
        )


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


@pytest.mark.parametrize(
    ("sample_rate", "frequency", "duration"),
    [
        (800.0, 125.0, 2.0),
        (2048.0, 320.0, 1.0),
        (4096.0, 640.0, 1.0),
    ],
)
def test_sample_rate_controls_frequency_axis_and_peak_units(
    sample_rate: float,
    frequency: float,
    duration: float,
):
    case = create_synthetic_case(
        [frequency],
        sample_rate=sample_rate,
        duration=duration,
        description=f"{frequency:g} Hz tone at {sample_rate:g} Hz sample rate",
    )
    evaluated = evaluate_case(
        case,
        spectrometer_rust.process_signal,
        **process_kwargs(threshold=0.005),
    )

    assert evaluated["result"]["sample_rate"] == sample_rate
    assert_metrics(
        evaluated,
        min_precision=1.0,
        min_recall=1.0,
        max_false_positives=0,
    )
    assert_frequency_axis_invariants(
        evaluated["result"],
        sample_rate=sample_rate,
        source_len=len(case.signal),
    )


def test_fft_window_reduces_far_leakage_without_moving_frequency_axis():
    case = fractional_bin_case()

    rectangular = spectrometer_rust.process_signal(
        data=case.signal.tolist(),
        sample_rate=case.sample_rate,
        **process_kwargs(window_type="rectangular", threshold=0.001),
    )
    hann = spectrometer_rust.process_signal(
        data=case.signal.tolist(),
        sample_rate=case.sample_rate,
        **process_kwargs(window_type="hann", threshold=0.001),
    )
    hamming = spectrometer_rust.process_signal(
        data=case.signal.tolist(),
        sample_rate=case.sample_rate,
        **process_kwargs(window_type="hamming", threshold=0.001),
    )

    np.testing.assert_allclose(
        np.asarray(rectangular["frequency_axis"], dtype=float),
        np.asarray(hann["frequency_axis"], dtype=float),
    )
    np.testing.assert_allclose(
        np.asarray(rectangular["frequency_axis"], dtype=float),
        np.asarray(hamming["frequency_axis"], dtype=float),
    )

    rectangular_leakage = leakage_energy_ratio(rectangular)
    hann_leakage = leakage_energy_ratio(hann)
    hamming_leakage = leakage_energy_ratio(hamming)

    assert hann_leakage < rectangular_leakage * 0.05
    assert hamming_leakage < rectangular_leakage * 0.05


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
