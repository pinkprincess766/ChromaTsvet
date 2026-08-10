"""Peak-feature matching independent from SQLite and GUI code."""

from __future__ import annotations

import math

from python_analyzer.analysis.models import ReferencePeak, PeakMatch


DEFAULT_DATA_TYPE = "generic"
ALLOWED_DATA_TYPE_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
DATA_TYPE_CHOICES = (
    ("Generic", "generic"),
    ("IR", "ir"),
    ("Raman", "raman"),
    ("Mass spectrometry", "ms"),
    ("UV-Vis", "uv_vis"),
    ("Fluorescence", "fluorescence"),
)
ALLOWED_DATA_TYPES = {value for _, value in DATA_TYPE_CHOICES}

FREQUENCY_SCORE_WEIGHT = 0.65
INTENSITY_SCORE_WEIGHT = 0.25
AREA_SCORE_WEIGHT = 0.10
WIDTH_SCORE_WEIGHT = 0.0
LOG_RATIO_SCALE = math.log(4.0)
LOG_RATIO_EPSILON = 1e-12


def normalize_data_type(data_type: object) -> str:
    value = str(data_type or DEFAULT_DATA_TYPE).strip().lower()
    if not value:
        return DEFAULT_DATA_TYPE

    normalized = "".join(char for char in value if char in ALLOWED_DATA_TYPE_CHARS)
    normalized = normalized[:32] or DEFAULT_DATA_TYPE
    return normalized if normalized in ALLOWED_DATA_TYPES else DEFAULT_DATA_TYPE


def normalize_reference_peaks(peaks: list[object]) -> list[ReferencePeak]:
    normalized_peaks = []
    for peak in peaks:
        reference_peak = peak_to_reference_peak(peak)
        if reference_peak is not None:
            normalized_peaks.append(reference_peak)
    return normalized_peaks


def peak_to_reference_peak(peak: object) -> ReferencePeak | None:
    frequency = _peak_value(peak, "frequency", None)
    if frequency is None:
        frequency = _peak_value(peak, "position", None)
    intensity = _peak_value(peak, "intensity", None)

    if frequency is None or intensity is None:
        return None

    frequency = _finite_float(frequency)
    intensity = _finite_float(intensity)
    if frequency is None or intensity is None:
        return None

    width = _finite_float(_peak_value(peak, "width", 0.0), default=0.0)
    width_hz = _finite_float(_peak_value(peak, "width_hz", 0.0), default=0.0)
    area = _finite_float(_peak_value(peak, "area", 0.0), default=0.0)
    snr = _finite_float(_peak_value(peak, "snr", 0.0), default=0.0)

    return ReferencePeak(
        frequency=frequency,
        intensity=max(0.0, intensity),
        width=max(0.0, width),
        width_hz=max(0.0, width_hz),
        area=max(0.0, area),
        snr=max(0.0, snr),
    )


def find_peak_matches(
    unknown_peaks: list[dict | ReferencePeak],
    reference_peaks: list[ReferencePeak],
    frequency_tolerance: float = 5.0,
    frequency_weight: float = FREQUENCY_SCORE_WEIGHT,
    intensity_weight: float = INTENSITY_SCORE_WEIGHT,
    area_weight: float = AREA_SCORE_WEIGHT,
    width_weight: float = WIDTH_SCORE_WEIGHT,
) -> list[PeakMatch]:
    """Match unknown and reference peaks with one-to-one frequency candidates."""

    frequency_tolerance = _finite_float(frequency_tolerance, default=0.0) or 0.0
    if frequency_tolerance <= 0.0:
        return []

    weights = _score_weights(
        frequency_weight,
        intensity_weight,
        area_weight,
        width_weight,
    )

    unknown_normalized = normalize_reference_peaks(unknown_peaks)
    reference_normalized = normalize_reference_peaks(reference_peaks)
    candidates = build_peak_match_candidates(
        unknown_normalized,
        reference_normalized,
        frequency_tolerance,
        weights,
    )
    return select_one_to_one_peak_matches(
        unknown_normalized,
        reference_normalized,
        candidates,
    )


def build_peak_match_candidates(
    unknown_peaks: list[ReferencePeak],
    reference_peaks: list[ReferencePeak],
    frequency_tolerance: float,
    weights: dict[str, float] | None = None,
) -> list[tuple[float, float, int, int, float, float]]:
    """Build candidate matches inside a tolerance window.

    Sorting both lists keeps candidate generation proportional to the number of
    in-window pairs: O(U log U + R log R + K), where K is admitted candidates.
    """

    weights = weights or _score_weights()
    unknown_sorted = sorted(
        enumerate(unknown_peaks),
        key=lambda item: item[1].frequency,
    )
    reference_sorted = sorted(
        enumerate(reference_peaks),
        key=lambda item: item[1].frequency,
    )

    candidates = []
    window_left = 0
    window_right = 0
    for unknown_index, unknown_peak in unknown_sorted:
        min_frequency = unknown_peak.frequency - frequency_tolerance
        max_frequency = unknown_peak.frequency + frequency_tolerance

        while (
            window_left < len(reference_sorted)
            and reference_sorted[window_left][1].frequency < min_frequency
        ):
            window_left += 1
        while (
            window_right < len(reference_sorted)
            and reference_sorted[window_right][1].frequency <= max_frequency
        ):
            window_right += 1

        for reference_index, reference_peak in reference_sorted[window_left:window_right]:
            candidate = _score_peak_pair(
                unknown_index,
                unknown_peak,
                reference_index,
                reference_peak,
                frequency_tolerance,
                weights,
            )
            if candidate is not None:
                candidates.append(candidate)

    return candidates


def select_one_to_one_peak_matches(
    unknown_peaks: list[ReferencePeak],
    reference_peaks: list[ReferencePeak],
    candidates: list[tuple[float, float, int, int, float, float]],
) -> list[PeakMatch]:
    matches: list[PeakMatch] = []
    used_unknown: set[int] = set()
    used_reference: set[int] = set()
    for (
        negative_score,
        frequency_diff,
        unknown_index,
        reference_index,
        intensity_ratio,
        score,
    ) in sorted(candidates):
        if unknown_index in used_unknown or reference_index in used_reference:
            continue

        used_unknown.add(unknown_index)
        used_reference.add(reference_index)
        unknown_peak = unknown_peaks[unknown_index]
        reference_peak = reference_peaks[reference_index]
        matches.append(
            PeakMatch(
                unknown_frequency=unknown_peak.frequency,
                reference_frequency=reference_peak.frequency,
                frequency_diff=frequency_diff,
                intensity_ratio=intensity_ratio,
                score=round(score, 3),
                unknown_index=unknown_index,
                reference_index=reference_index,
            )
        )

    return matches


def compute_peak_based_score(
    matches: list[PeakMatch],
    num_unknown_peaks: int,
    num_reference_peaks: int,
    unmatched_penalty: float = 0.3,
) -> float:
    """Compute overall score from matches, penalizing unmatched peaks."""

    if not matches:
        return 0.0

    avg_match_score = sum(match.score for match in matches) / len(matches)
    match_ratio = len(matches) / max(num_unknown_peaks, 1)
    coverage = len(matches) / max(num_reference_peaks, 1)

    penalty = unmatched_penalty * (1 - min(match_ratio, coverage))
    final_score = avg_match_score * (1 - penalty)

    return max(0.0, min(1.0, round(final_score, 3)))


def _peak_value(peak: object, field_name: str, default: object = None) -> object:
    if isinstance(peak, dict):
        return peak.get(field_name, default)
    return getattr(peak, field_name, default)


def _finite_float(value: object, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _score_peak_pair(
    unknown_index: int,
    unknown_peak: ReferencePeak,
    reference_index: int,
    reference_peak: ReferencePeak,
    frequency_tolerance: float,
    weights: dict[str, float],
) -> tuple[float, float, int, int, float, float] | None:
    frequency_diff = abs(unknown_peak.frequency - reference_peak.frequency)
    if frequency_diff > frequency_tolerance:
        return None

    frequency_score = max(0.0, 1.0 - (frequency_diff / frequency_tolerance))
    intensity_ratio = _safe_ratio(unknown_peak.intensity, reference_peak.intensity)
    score_parts = [("frequency", frequency_score)]
    score_parts.append(
        (
            "intensity",
            _log_ratio_score(unknown_peak.intensity, reference_peak.intensity),
        )
    )

    if unknown_peak.area > 0.0 and reference_peak.area > 0.0:
        score_parts.append(("area", _log_ratio_score(unknown_peak.area, reference_peak.area)))
    if unknown_peak.width_hz > 0.0 and reference_peak.width_hz > 0.0:
        score_parts.append(
            ("width", _log_ratio_score(unknown_peak.width_hz, reference_peak.width_hz))
        )

    score = _weighted_score(score_parts, weights)
    return (-score, frequency_diff, unknown_index, reference_index, intensity_ratio, score)


def _score_weights(
    frequency_weight: float = FREQUENCY_SCORE_WEIGHT,
    intensity_weight: float = INTENSITY_SCORE_WEIGHT,
    area_weight: float = AREA_SCORE_WEIGHT,
    width_weight: float = WIDTH_SCORE_WEIGHT,
) -> dict[str, float]:
    return {
        "frequency": max(0.0, _finite_float(frequency_weight, 0.0) or 0.0),
        "intensity": max(0.0, _finite_float(intensity_weight, 0.0) or 0.0),
        "area": max(0.0, _finite_float(area_weight, 0.0) or 0.0),
        "width": max(0.0, _finite_float(width_weight, 0.0) or 0.0),
    }


def _weighted_score(score_parts: list[tuple[str, float]], weights: dict[str, float]) -> float:
    numerator = 0.0
    denominator = 0.0
    for name, score in score_parts:
        weight = weights.get(name, 0.0)
        if weight <= 0.0:
            continue
        numerator += weight * max(0.0, min(1.0, score))
        denominator += weight

    return numerator / denominator if denominator > 0.0 else 0.0


def _log_ratio_score(left: float, right: float) -> float:
    ratio_error = abs(
        math.log(
            (max(0.0, left) + LOG_RATIO_EPSILON)
            / (max(0.0, right) + LOG_RATIO_EPSILON)
        )
    )
    return max(0.0, 1.0 - (ratio_error / LOG_RATIO_SCALE))


def _safe_ratio(left: float, right: float) -> float:
    return (left + LOG_RATIO_EPSILON) / (right + LOG_RATIO_EPSILON)
