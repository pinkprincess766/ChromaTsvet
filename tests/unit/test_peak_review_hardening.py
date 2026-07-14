from types import SimpleNamespace

import pytest

from python_analyzer.analysis.peak_review import (
    PEAK_REVIEW_ACCEPTED,
    PEAK_REVIEW_REJECTED,
    PEAK_REVIEW_SUSPICIOUS,
    PeakReview,
    review_peak,
    review_summary,
    set_peak_review_status,
)


@pytest.mark.parametrize(
    ("peak", "expected_reason"),
    [
        (
            SimpleNamespace(
                frequency=float("nan"),
                position=float("inf"),
                intensity=1.0,
            ),
            "position",
        ),
        (
            SimpleNamespace(
                frequency=10.0,
                position=20.0,
                intensity=float("nan"),
            ),
            "intensity",
        ),
        (
            SimpleNamespace(
                frequency=None,
                position=None,
                intensity=1.0,
            ),
            "position",
        ),
    ],
)
def test_invalid_required_peak_fields_are_rejected(peak, expected_reason):
    review = review_peak(peak)

    assert review.status == PEAK_REVIEW_REJECTED
    assert expected_reason in review.reason


@pytest.mark.parametrize(
    ("peak", "expected_flag"),
    [
        (
            SimpleNamespace(frequency=10.0, intensity=1.0, snr=2.99),
            "low SNR",
        ),
        (
            SimpleNamespace(frequency=10.0, intensity=1.0, area=0.0),
            "non-positive area",
        ),
        (
            SimpleNamespace(frequency=10.0, intensity=1.0, area=-0.1),
            "non-positive area",
        ),
        (
            SimpleNamespace(frequency=10.0, intensity=1.0, width=0.0),
            "unknown width",
        ),
        (
            SimpleNamespace(frequency=10.0, intensity=1.0, width_hz=-1.0),
            "unknown width",
        ),
        (
            SimpleNamespace(frequency=10.0, intensity=1.0, is_global_max=True),
            "global maximum fallback",
        ),
    ],
)
def test_soft_peak_quality_problems_are_suspicious_not_rejected(peak, expected_flag):
    review = review_peak(peak)

    assert review.status == PEAK_REVIEW_SUSPICIOUS
    assert expected_flag in review.flags
    assert expected_flag in review.reason


@pytest.mark.parametrize(
    ("peak", "kwargs"),
    [
        (
            SimpleNamespace(
                frequency=10.0,
                intensity=1.0,
                snr=5.0,
            ),
            {"min_snr": 5.0},
        ),
        (
            SimpleNamespace(
                frequency=10.0,
                intensity=1.0,
                prominence=0.25,
            ),
            {"min_prominence": 0.25},
        ),
        (
            SimpleNamespace(
                frequency=10.0,
                intensity=1.0,
            ),
            {},
        ),
    ],
)
def test_threshold_boundaries_and_missing_optional_fields_are_accepted(peak, kwargs):
    review = review_peak(peak, **kwargs)

    assert review.status == PEAK_REVIEW_ACCEPTED
    assert review.flags == ()


def test_user_override_preserves_original_diagnostic_flags():
    original = review_peak(
        SimpleNamespace(
            frequency=10.0,
            intensity=1.0,
            snr=1.0,
            area=0.0,
        )
    )

    updated = set_peak_review_status(original, PEAK_REVIEW_REJECTED)

    assert updated.status == PEAK_REVIEW_REJECTED
    assert updated.flags == original.flags
    assert updated.user_modified is True


def test_unknown_review_status_counts_as_suspicious_in_summary():
    summary = review_summary(
        [
            PeakReview(PEAK_REVIEW_ACCEPTED, "accepted"),
            PeakReview("future-status", "unknown"),
        ]
    )

    assert summary[PEAK_REVIEW_ACCEPTED] == 1
    assert summary[PEAK_REVIEW_SUSPICIOUS] == 1
