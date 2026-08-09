from types import SimpleNamespace

from python_analyzer.analysis.peak_review import (
    PEAK_REVIEW_ACCEPTED,
    PEAK_REVIEW_REJECTED,
    PEAK_REVIEW_SUSPICIOUS,
    POSSIBLE_OVERLAP_FLAG,
    POSSIBLE_SHOULDER_FLAG,
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


def test_well_separated_peaks_do_not_get_overlap_warning():
    peaks = [
        SimpleNamespace(
            frequency=100.0,
            position=10.0,
            intensity=1.0,
            prominence=0.8,
            width=2.0,
            width_hz=5.0,
            area=4.0,
            snr=20.0,
        ),
        SimpleNamespace(
            frequency=135.0,
            position=20.0,
            intensity=0.9,
            prominence=0.7,
            width=2.0,
            width_hz=5.0,
            area=3.5,
            snr=18.0,
        ),
    ]

    reviews = review_peaks(peaks)

    assert [review.status for review in reviews] == [
        PEAK_REVIEW_ACCEPTED,
        PEAK_REVIEW_ACCEPTED,
    ]
    assert all(POSSIBLE_OVERLAP_FLAG not in review.flags for review in reviews)
    assert all(POSSIBLE_SHOULDER_FLAG not in review.flags for review in reviews)


def test_close_peaks_are_marked_as_possible_overlap():
    peaks = [
        SimpleNamespace(
            frequency=100.0,
            position=10.0,
            intensity=1.0,
            prominence=0.8,
            width=2.0,
            width_hz=6.0,
            area=4.0,
            snr=20.0,
        ),
        SimpleNamespace(
            frequency=106.0,
            position=12.0,
            intensity=0.9,
            prominence=0.7,
            width=2.0,
            width_hz=6.0,
            area=3.5,
            snr=18.0,
        ),
    ]

    reviews = review_peaks(peaks)

    assert [review.status for review in reviews] == [
        PEAK_REVIEW_SUSPICIOUS,
        PEAK_REVIEW_SUSPICIOUS,
    ]
    assert all(POSSIBLE_OVERLAP_FLAG in review.flags for review in reviews)


def test_weak_peak_near_strong_peak_is_marked_as_possible_shoulder():
    peaks = [
        SimpleNamespace(
            frequency=100.0,
            position=10.0,
            intensity=1.0,
            prominence=1.0,
            width=2.0,
            width_hz=6.0,
            area=6.0,
            snr=30.0,
        ),
        SimpleNamespace(
            frequency=111.0,
            position=14.0,
            intensity=0.25,
            prominence=0.2,
            width=2.0,
            width_hz=6.0,
            area=1.2,
            snr=12.0,
        ),
    ]

    reviews = review_peaks(peaks)

    assert reviews[0].status == PEAK_REVIEW_ACCEPTED
    assert POSSIBLE_SHOULDER_FLAG not in reviews[0].flags
    assert reviews[1].status == PEAK_REVIEW_SUSPICIOUS
    assert POSSIBLE_SHOULDER_FLAG in reviews[1].flags
    assert POSSIBLE_OVERLAP_FLAG not in reviews[1].flags


def test_unknown_width_does_not_create_overlap_warning():
    peaks = [
        SimpleNamespace(
            frequency=100.0,
            intensity=1.0,
            prominence=1.0,
            width=0.0,
            width_hz=0.0,
            area=6.0,
            snr=30.0,
        ),
        SimpleNamespace(
            frequency=101.0,
            intensity=0.9,
            prominence=0.8,
            width=0.0,
            width_hz=0.0,
            area=5.0,
            snr=25.0,
        ),
    ]

    reviews = review_peaks(peaks)

    assert all(review.status == PEAK_REVIEW_SUSPICIOUS for review in reviews)
    assert all("unknown width" in review.flags for review in reviews)
    assert all(POSSIBLE_OVERLAP_FLAG not in review.flags for review in reviews)
    assert all(POSSIBLE_SHOULDER_FLAG not in review.flags for review in reviews)


def test_user_override_updates_status_and_summary():
    original = review_peak(SimpleNamespace(frequency=10.0, intensity=1.0, snr=20.0))

    updated = set_peak_review_status(original, PEAK_REVIEW_REJECTED)
    summary = review_summary([original, updated])

    assert updated.status == PEAK_REVIEW_REJECTED
    assert updated.user_modified is True
    assert summary[PEAK_REVIEW_ACCEPTED] == 1
    assert summary[PEAK_REVIEW_REJECTED] == 1
