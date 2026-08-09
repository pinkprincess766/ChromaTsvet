"""Human-review helpers for detected peaks.

The Rust core owns peak detection. This module adds a small, explicit review
layer for the GUI so users can accept or reject individual detections without
changing the numerical pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any, Iterable


PEAK_REVIEW_ACCEPTED = "accepted"
PEAK_REVIEW_SUSPICIOUS = "suspicious"
PEAK_REVIEW_REJECTED = "rejected"
PEAK_REVIEW_MANUAL = "manual"

PEAK_REVIEW_STATUSES = (
    PEAK_REVIEW_ACCEPTED,
    PEAK_REVIEW_SUSPICIOUS,
    PEAK_REVIEW_REJECTED,
    PEAK_REVIEW_MANUAL,
)

DEFAULT_LOW_SNR_WARNING = 3.0
OVERLAP_DISTANCE_WIDTH_FACTOR = 1.25
SHOULDER_DISTANCE_WIDTH_FACTOR = 2.0
SHOULDER_STRENGTH_RATIO = 0.35
POSSIBLE_OVERLAP_FLAG = "possible overlap"
POSSIBLE_SHOULDER_FLAG = "possible shoulder"


@dataclass(frozen=True)
class PeakReview:
    """Review state attached to one detected peak."""

    status: str
    reason: str
    flags: tuple[str, ...] = ()
    user_modified: bool = False


def review_peaks(peaks: Iterable[Any], settings: Any | None = None) -> list[PeakReview]:
    """Return review diagnostics for a sequence of detected peaks."""

    peak_list = list(peaks)
    min_snr = _finite_setting(settings, "peak_min_snr", 0.0)
    min_prominence = _finite_setting(settings, "peak_prominence", 0.0)
    reviews = [
        review_peak(
            peak,
            min_snr=min_snr,
            min_prominence=min_prominence,
        )
        for peak in peak_list
    ]
    overlap_flags = _overlap_review_flags(peak_list, reviews)
    return [
        _merge_review_flags(review, flags)
        for review, flags in zip(reviews, overlap_flags)
    ]


def review_peak(
    peak: Any,
    *,
    min_snr: float = 0.0,
    min_prominence: float = 0.0,
) -> PeakReview:
    """Classify one peak as accepted, suspicious, or rejected.

    The classifier is intentionally conservative: invalid coordinates are
    rejected, while soft quality concerns become warnings for human review.
    """

    flags: list[str] = []

    frequency = _peak_frequency(peak)
    position = _finite_attr(peak, "position")
    intensity = _finite_attr(peak, "intensity")

    if frequency is None and position is None:
        return PeakReview(
            PEAK_REVIEW_REJECTED,
            "missing finite peak position",
            ("invalid_position",),
        )
    if intensity is None:
        return PeakReview(
            PEAK_REVIEW_REJECTED,
            "missing finite peak intensity",
            ("invalid_intensity",),
        )

    snr = _finite_attr(peak, "snr")
    if snr is not None:
        if min_snr > 0.0 and snr < min_snr:
            flags.append("below configured SNR")
        elif 0.0 <= snr < DEFAULT_LOW_SNR_WARNING:
            flags.append("low SNR")

    prominence = _finite_attr(peak, "prominence")
    if prominence is not None:
        if min_prominence > 0.0 and prominence < min_prominence:
            flags.append("below configured prominence")
        elif prominence <= 0.0:
            flags.append("non-positive prominence")

    area = _finite_attr(peak, "area")
    if area is not None and area <= 0.0:
        flags.append("non-positive area")

    width = _finite_attr(peak, "width")
    width_hz = _finite_attr(peak, "width_hz")
    if (width is not None and width <= 0.0) or (width_hz is not None and width_hz <= 0.0):
        flags.append("unknown width")

    if bool(getattr(peak, "is_global_max", False)):
        flags.append("global maximum fallback")

    if flags:
        return PeakReview(PEAK_REVIEW_SUSPICIOUS, "; ".join(flags), tuple(flags))
    return PeakReview(PEAK_REVIEW_ACCEPTED, "accepted", ())


def set_peak_review_status(review: PeakReview, status: str) -> PeakReview:
    """Return a user-modified review with a validated status."""

    normalized_status = str(status or "").strip().lower()
    if normalized_status not in PEAK_REVIEW_STATUSES:
        normalized_status = PEAK_REVIEW_SUSPICIOUS
    reason = review.reason
    if normalized_status == PEAK_REVIEW_ACCEPTED:
        reason = "accepted by user"
    elif normalized_status == PEAK_REVIEW_REJECTED:
        reason = "rejected by user"
    elif normalized_status == PEAK_REVIEW_MANUAL:
        reason = "manual review"
    return replace(
        review,
        status=normalized_status,
        reason=reason,
        user_modified=True,
    )


def review_summary(reviews: Iterable[PeakReview]) -> dict[str, int]:
    """Count review states for status-bar summaries and tests."""

    summary = {status: 0 for status in PEAK_REVIEW_STATUSES}
    for review in reviews:
        status = review.status if review.status in summary else PEAK_REVIEW_SUSPICIOUS
        summary[status] += 1
    return summary


def is_peak_review_exportable(review: PeakReview | None) -> bool:
    """Return True when a reviewed peak should remain in downstream reference data."""

    if review is None:
        return True
    return review.status != PEAK_REVIEW_REJECTED


def _finite_setting(settings: Any | None, name: str, default: float) -> float:
    if settings is None:
        return default
    value = getattr(settings, name, default)
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric_value):
        return default
    return max(0.0, numeric_value)


def _finite_attr(peak: Any, name: str) -> float | None:
    value = getattr(peak, name, None)
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric_value):
        return None
    return numeric_value


def _peak_frequency(peak: Any) -> float | None:
    frequency = _finite_attr(peak, "frequency")
    if frequency is not None:
        return frequency
    return _finite_attr(peak, "position")


def _overlap_review_flags(
    peaks: list[Any],
    reviews: list[PeakReview],
) -> list[list[str]]:
    """Return conservative overlap/shoulder flags for neighboring peaks.

    This is a review heuristic, not deconvolution: it warns humans when two
    already-detected peaks are closer than their measured widths can justify.
    """

    flags = [[] for _ in peaks]
    measurable_peaks: list[tuple[int, float, float, float | None]] = []
    for index, (peak, review) in enumerate(zip(peaks, reviews)):
        if review.status == PEAK_REVIEW_REJECTED:
            continue
        coordinate_and_width = _overlap_coordinate_and_width(peak)
        if coordinate_and_width is None:
            continue
        coordinate, width = coordinate_and_width
        measurable_peaks.append((index, coordinate, width, _peak_strength(peak)))

    measurable_peaks.sort(key=lambda item: item[1])
    for left, right in zip(measurable_peaks, measurable_peaks[1:]):
        left_index, left_coordinate, left_width, left_strength = left
        right_index, right_coordinate, right_width, right_strength = right
        distance = abs(right_coordinate - left_coordinate)
        average_width = (left_width + right_width) * 0.5
        if average_width <= 0.0:
            continue

        if distance <= average_width * OVERLAP_DISTANCE_WIDTH_FACTOR:
            flags[left_index].append(POSSIBLE_OVERLAP_FLAG)
            flags[right_index].append(POSSIBLE_OVERLAP_FLAG)
            continue

        if distance > average_width * SHOULDER_DISTANCE_WIDTH_FACTOR:
            continue
        if left_strength is None or right_strength is None:
            continue

        weak_strength = min(left_strength, right_strength)
        strong_strength = max(left_strength, right_strength)
        if strong_strength <= 0.0:
            continue
        if weak_strength / strong_strength <= SHOULDER_STRENGTH_RATIO:
            weak_index = left_index if left_strength <= right_strength else right_index
            flags[weak_index].append(POSSIBLE_SHOULDER_FLAG)

    return flags


def _overlap_coordinate_and_width(peak: Any) -> tuple[float, float] | None:
    frequency = _finite_attr(peak, "frequency")
    width_hz = _finite_attr(peak, "width_hz")
    if frequency is not None and width_hz is not None and width_hz > 0.0:
        return frequency, width_hz

    position = _finite_attr(peak, "position")
    width = _finite_attr(peak, "width")
    if position is not None and width is not None and width > 0.0:
        return position, width
    return None


def _peak_strength(peak: Any) -> float | None:
    prominence = _finite_attr(peak, "prominence")
    if prominence is not None and prominence > 0.0:
        return prominence

    intensity = _finite_attr(peak, "intensity")
    if intensity is not None and intensity > 0.0:
        return intensity
    return None


def _merge_review_flags(review: PeakReview, flags: list[str]) -> PeakReview:
    if not flags:
        return review
    if review.status == PEAK_REVIEW_REJECTED:
        return review

    merged_flags = tuple(dict.fromkeys([*review.flags, *flags]))
    return PeakReview(
        PEAK_REVIEW_SUSPICIOUS,
        "; ".join(merged_flags),
        merged_flags,
        user_modified=review.user_modified,
    )
