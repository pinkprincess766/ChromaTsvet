"""Formatting helpers for the embedded analysis console.

The console is intentionally a user-facing diagnostic stream. It should explain
analysis risks without leaking private local paths or raw input data.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
import re
from typing import Any

from python_analyzer.analysis.peak_review import (
    PEAK_REVIEW_ACCEPTED,
    PEAK_REVIEW_REJECTED,
    PEAK_REVIEW_SUSPICIOUS,
    PeakReview,
)


MAX_DIAGNOSTIC_TEXT_LENGTH = 220
MAX_REVIEW_REASONS = 5

PROCESSING_WARNING_MESSAGES = {
    "invalid_sample_rate_fallback": (
        "invalid sample rate; Rust used its safe fallback value"
    ),
    "unknown_filter_fallback_none": (
        "unknown Rust filter name; Rust skipped fallback filtering"
    ),
    "unknown_window_fallback_rectangular": (
        "unknown FFT window; rectangular window was used"
    ),
    "unknown_baseline_method_fallback_improved": (
        "unknown baseline method; improved baseline correction was used"
    ),
    "unknown_smoothing_method_disabled": (
        "unknown spectrum smoothing method; smoothing was disabled"
    ),
    "short_signal_no_peak_detection": (
        "signal is too short for reliable peak detection"
    ),
    "area_normalization_skipped": (
        "area normalization was skipped because the integral was too small"
    ),
    "no_peaks_detected": "no peaks were detected after filtering criteria",
}

_POSIX_PATH_RE = re.compile(r"(?<![\w.-])/(?:[^/\s]+/)+([^/\s]+)")
_WINDOWS_PATH_RE = re.compile(r"(?<![\w.-])[A-Za-z]:\\(?:[^\\\s]+\\)+([^\\\s]+)")
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_diagnostic_text(value: Any) -> str:
    """Return short user-facing text with absolute local paths redacted."""

    text = _WHITESPACE_RE.sub(" ", str(value or "").strip())
    if not text:
        return ""

    text = _POSIX_PATH_RE.sub(r".../\1", text)
    text = _WINDOWS_PATH_RE.sub(r"...\\\1", text)
    if len(text) > MAX_DIAGNOSTIC_TEXT_LENGTH:
        text = f"{text[: MAX_DIAGNOSTIC_TEXT_LENGTH - 1]}..."
    return text


def processing_warning_messages(
    result: Mapping[str, Any] | None,
    *,
    source_label: str = "Processing",
) -> list[str]:
    """Format Rust processing warnings for the analysis console."""

    warnings = _warning_values(result)
    if not warnings:
        return []

    prefix = sanitize_diagnostic_text(source_label) or "Processing"
    messages: list[str] = []
    for warning in warnings:
        warning_key = sanitize_diagnostic_text(warning)
        if not warning_key:
            continue
        detail = PROCESSING_WARNING_MESSAGES.get(
            warning_key,
            f"Rust reported '{warning_key}'",
        )
        messages.append(f"{prefix} warning: {detail}")
    return messages


def peak_review_messages(reviews: Sequence[PeakReview] | None) -> list[str]:
    """Summarize peak review warnings without dumping raw peak values."""

    if not reviews:
        return []

    attention_reviews = [
        review for review in reviews if review.status != PEAK_REVIEW_ACCEPTED
    ]
    if not attention_reviews:
        return []

    status_counts = Counter(review.status for review in attention_reviews)
    count_parts = []
    suspicious = status_counts.get(PEAK_REVIEW_SUSPICIOUS, 0)
    rejected = status_counts.get(PEAK_REVIEW_REJECTED, 0)
    other = sum(
        count
        for status, count in status_counts.items()
        if status not in {PEAK_REVIEW_SUSPICIOUS, PEAK_REVIEW_REJECTED}
    )
    if suspicious:
        count_parts.append(f"{suspicious} suspicious")
    if rejected:
        count_parts.append(f"{rejected} rejected")
    if other:
        count_parts.append(f"{other} manually reviewed")

    reason_counts: Counter[str] = Counter()
    for review in attention_reviews:
        reason_values = review.flags or (review.reason,)
        for reason in reason_values:
            safe_reason = sanitize_diagnostic_text(reason)
            if safe_reason:
                reason_counts[safe_reason] += 1

    reasons = ", ".join(reason for reason, _ in reason_counts.most_common(MAX_REVIEW_REASONS))
    if len(reason_counts) > MAX_REVIEW_REASONS:
        reasons = f"{reasons}, ..."

    single_attention = len(attention_reviews) == 1
    peak_word = "peak" if single_attention else "peaks"
    verb = "requires" if single_attention else "require"
    count_text = ", ".join(count_parts) or f"{len(attention_reviews)} require attention"
    message = f"Peak review: {len(attention_reviews)} {peak_word} {verb} attention ({count_text})"
    if reasons:
        message = f"{message}; reasons: {reasons}"
    return [message]


def skipped_rows_message(
    file_label: str,
    *,
    valid_points: int,
    skipped_rows: Iterable[tuple[int, str]],
) -> str:
    """Format an import warning without echoing user-provided cell values."""

    skipped_line_numbers = [
        line_no
        for line_no, _ in skipped_rows
        if isinstance(line_no, int) and line_no > 0
    ]
    skipped_count = len(skipped_line_numbers)
    label = sanitize_diagnostic_text(file_label) or "selected file"
    line_preview = ", ".join(str(line_no) for line_no in skipped_line_numbers[:5])
    line_suffix = f"; first skipped lines: {line_preview}" if line_preview else ""
    return (
        f"Import warning: {label} loaded with {valid_points} valid points "
        f"and {skipped_count} skipped rows{line_suffix}"
    )


def _warning_values(result: Mapping[str, Any] | None) -> list[Any]:
    if not result:
        return []
    raw_warnings = result.get("processing_warnings", result.get("warnings", ()))
    if isinstance(raw_warnings, str):
        return [raw_warnings]
    if isinstance(raw_warnings, Sequence):
        return list(raw_warnings)
    return []
