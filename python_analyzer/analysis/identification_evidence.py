"""Conservative evidence summaries for peak-based reference matching.

The labels in this module describe the strength of a computational candidate
match. They are deliberately not chemical-identification claims.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from python_analyzer.analysis.models import PeakMatch


EVIDENCE_INSUFFICIENT = "insufficient"
EVIDENCE_WEAK = "weak"
EVIDENCE_MODERATE = "moderate"
EVIDENCE_STRONG = "strong"
EVIDENCE_LEGACY = "legacy"

MIN_WEAK_SCORE = 0.25
MIN_MODERATE_SCORE = 0.65
MIN_STRONG_SCORE = 0.85
MIN_MODERATE_MATCHES = 2
MIN_STRONG_MATCHES = 3
MIN_MODERATE_COVERAGE = 0.40
MIN_STRONG_COVERAGE = 0.60


@dataclass(frozen=True)
class MatchEvidence:
    """Finite, bounded diagnostics derived from one candidate match."""

    sample_coverage: float
    reference_coverage: float
    mean_frequency_error: float | None
    max_frequency_error: float | None
    evidence_level: str


def summarize_match_evidence(
    *,
    score: float,
    matches: Sequence[PeakMatch],
    unknown_peak_count: int,
    reference_peak_count: int,
) -> MatchEvidence:
    """Summarize evidence in O(M) time and O(1) auxiliary space."""

    matched_count = len(matches)
    sample_coverage = _coverage(matched_count, unknown_peak_count)
    reference_coverage = _coverage(matched_count, reference_peak_count)
    frequency_error_sum = 0.0
    frequency_error_count = 0
    max_frequency_error = None
    for match in matches:
        if not _is_finite(match.frequency_diff):
            continue
        frequency_error = abs(float(match.frequency_diff))
        frequency_error_sum += frequency_error
        frequency_error_count += 1
        max_frequency_error = (
            frequency_error
            if max_frequency_error is None
            else max(max_frequency_error, frequency_error)
        )
    mean_frequency_error = (
        frequency_error_sum / frequency_error_count
        if frequency_error_count
        else None
    )

    return MatchEvidence(
        sample_coverage=sample_coverage,
        reference_coverage=reference_coverage,
        mean_frequency_error=mean_frequency_error,
        max_frequency_error=max_frequency_error,
        evidence_level=classify_match_evidence(
            score=score,
            matched_count=matched_count,
            sample_coverage=sample_coverage,
            reference_coverage=reference_coverage,
        ),
    )


def classify_match_evidence(
    *,
    score: float,
    matched_count: int,
    sample_coverage: float,
    reference_coverage: float,
) -> str:
    """Return a conservative evidence band for an inspectable candidate.

    Coverage is required on both sides. In particular, one excellent pair is
    never enough for a strong or moderate candidate classification.
    """

    finite_score = _bounded_fraction(score)
    finite_sample_coverage = _bounded_fraction(sample_coverage)
    finite_reference_coverage = _bounded_fraction(reference_coverage)
    safe_match_count = max(0, int(matched_count))

    if (
        safe_match_count >= MIN_STRONG_MATCHES
        and finite_score >= MIN_STRONG_SCORE
        and finite_sample_coverage >= MIN_STRONG_COVERAGE
        and finite_reference_coverage >= MIN_STRONG_COVERAGE
    ):
        return EVIDENCE_STRONG
    if (
        safe_match_count >= MIN_MODERATE_MATCHES
        and finite_score >= MIN_MODERATE_SCORE
        and finite_sample_coverage >= MIN_MODERATE_COVERAGE
        and finite_reference_coverage >= MIN_MODERATE_COVERAGE
    ):
        return EVIDENCE_MODERATE
    if safe_match_count >= 1 and finite_score >= MIN_WEAK_SCORE:
        return EVIDENCE_WEAK
    return EVIDENCE_INSUFFICIENT


def _coverage(matched_count: int, total_count: int) -> float:
    if total_count <= 0:
        return 0.0
    return _bounded_fraction(max(0, matched_count) / total_count)


def _bounded_fraction(value: object) -> float:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(numeric_value):
        return 0.0
    return max(0.0, min(1.0, numeric_value))


def _is_finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
