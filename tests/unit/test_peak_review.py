from types import SimpleNamespace

from python_analyzer.analysis.peak_review import (
    PEAK_REVIEW_ACCEPTED,
    PEAK_REVIEW_REJECTED,
    PEAK_REVIEW_SUSPICIOUS,
    review_peak,
    review_peaks,
    review_summary,
    set_peak_review_status,
)
from python_analyzer.analysis.models import AnalysisSettings


def test_valid_peak_is_accepted():
    peak = SimpleNamespace(
        frequency=12.5,
        position=25.0,
        intensity=0.9,
        width=2.0,
        area=1.5,
        snr=12.0,
        prominence=0.2,
    )

    review = review_peak(peak, min_snr=3.0, min_prominence=0.05)

    assert review.status == PEAK_REVIEW_ACCEPTED
    assert review.reason == "accepted"


def test_invalid_peak_coordinates_are_rejected():
    peak = SimpleNamespace(
        frequency=float("nan"),
        position=float("inf"),
        intensity=0.9,
    )

    review = review_peak(peak)

    assert review.status == PEAK_REVIEW_REJECTED
    assert "position" in review.reason


def test_low_snr_and_prominence_are_suspicious_not_rejected():
    peak = SimpleNamespace(
        frequency=40.0,
        intensity=0.3,
        snr=1.5,
        prominence=0.01,
        width=0.0,
    )

    review = review_peak(peak, min_snr=5.0, min_prominence=0.1)

    assert review.status == PEAK_REVIEW_SUSPICIOUS
    assert "SNR" in review.reason
    assert "prominence" in review.reason


def test_review_peaks_uses_analysis_settings_thresholds():
    settings = AnalysisSettings(
        sample_rate=1000.0,
        filter_type="none",
        filter_params={},
        baseline_enabled=True,
        baseline_method="improved",
        peak_threshold=0.05,
        peak_prominence=0.2,
        peak_distance=1,
        normalize_area=False,
        peak_min_snr=10.0,
    )
    peaks = [
        SimpleNamespace(frequency=10.0, intensity=1.0, snr=12.0, prominence=0.4),
        SimpleNamespace(frequency=20.0, intensity=0.8, snr=4.0, prominence=0.4),
    ]

    reviews = review_peaks(peaks, settings)

    assert [review.status for review in reviews] == [
        PEAK_REVIEW_ACCEPTED,
        PEAK_REVIEW_SUSPICIOUS,
    ]


def test_user_override_updates_status_and_summary():
    original = review_peak(SimpleNamespace(frequency=10.0, intensity=1.0, snr=20.0))

    updated = set_peak_review_status(original, PEAK_REVIEW_REJECTED)
    summary = review_summary([original, updated])

    assert updated.status == PEAK_REVIEW_REJECTED
    assert updated.user_modified is True
    assert summary[PEAK_REVIEW_ACCEPTED] == 1
    assert summary[PEAK_REVIEW_REJECTED] == 1
