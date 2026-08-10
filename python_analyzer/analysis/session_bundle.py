"""Save/load snapshots of one completed analysis session.

The session format is intentionally a snapshot, not a project file. It stores
the processed spectrum, peak review state, analysis settings, and report
metadata needed to inspect/export the result later without re-reading the
original instrument file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any

from python_analyzer.analysis.method_presets import (
    analysis_settings_from_dict,
    analysis_settings_to_dict,
)
from python_analyzer.analysis.models import AnalysisSettings
from python_analyzer.analysis.peak_review import (
    PEAK_REVIEW_STATUSES,
    PeakReview,
    review_peaks,
)


SESSION_SCHEMA_VERSION = 1
SESSION_FILE_FILTER = "ChromaTsvet Session (*.chromatsvet-session.json);;JSON (*.json)"
SESSION_SUFFIX = ".chromatsvet-session.json"
MAX_SESSION_POINTS = 2_000_000
MAX_SESSION_PEAKS = 100_000
MAX_SESSION_MATCHES = 1_000
MAX_TEXT_LENGTH = 500

_ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?P<prefix>[A-Za-z]:)?[/\\](?:[^/\\\s]+[/\\])*(?P<name>[^/\\\s]+)"
)


class SessionFormatError(ValueError):
    """Raised when a ChromaTsvet session file is malformed or unsafe."""


def build_analysis_session_payload(
    *,
    source_file_name: str,
    data_points_count: int,
    settings: AnalysisSettings,
    method_name: str,
    result: Mapping[str, Any],
    frequency_axis: Sequence[Any],
    spectrum: Sequence[Any],
    peaks: Sequence[Any],
    peak_reviews: Sequence[PeakReview],
    matches: Sequence[Any],
    app_version: str,
    rust_core_version: str,
    processing_passport_rows: Sequence[tuple[Any, Any]] = (),
) -> dict[str, Any]:
    """Build a JSON-safe session payload without source-path leakage."""

    clean_spectrum = _finite_float_list(spectrum, "spectrum")
    clean_frequency_axis = _finite_float_list(frequency_axis, "frequency_axis")
    if not clean_spectrum:
        raise SessionFormatError("session spectrum cannot be empty")
    if len(clean_frequency_axis) != len(clean_spectrum):
        raise SessionFormatError("frequency axis length must match spectrum length")

    clean_peaks = [
        _peak_to_dict(peak)
        for peak in _bounded_sequence(peaks, MAX_SESSION_PEAKS, "peaks")
    ]
    clean_reviews = [
        _review_to_dict(review)
        for review in _bounded_sequence(
            peak_reviews,
            MAX_SESSION_PEAKS,
            "peak_reviews",
        )
    ]
    if clean_reviews and len(clean_reviews) != len(clean_peaks):
        raise SessionFormatError("peak review count must match peak count")
    if not clean_reviews:
        clean_reviews = [_review_to_dict(review) for review in review_peaks(peaks, settings)]

    return {
        "schema_version": SESSION_SCHEMA_VERSION,
        "application": "ChromaTsvet",
        "app_version": _safe_text(app_version),
        "rust_core_version": _safe_text(rust_core_version),
        "source": {
            "file_name": _safe_file_name(source_file_name),
            "data_points_count": _bounded_int(data_points_count, 0, MAX_SESSION_POINTS),
        },
        "analysis": {
            "method_name": _safe_text(method_name or "custom"),
            "settings": analysis_settings_to_dict(settings),
            "processing_passport_rows": _rows_to_dicts(processing_passport_rows),
            "processing_warnings": _safe_text_list(result.get("processing_warnings", [])),
        },
        "result": {
            "spectrum": clean_spectrum,
            "frequency_axis": clean_frequency_axis,
            "sample_rate": _finite_or_none(result.get("sample_rate")),
            "normalized": bool(result.get("normalized", False)),
            "baseline_method": _safe_text(result.get("baseline_method", "")),
            "normalization": _safe_text(result.get("normalization", "")),
            "spectrum_smoothed": bool(result.get("spectrum_smoothed", False)),
            "spectrum_smoothing_method": _safe_text(
                result.get("spectrum_smoothing_method", "")
            ),
            "spectrum_smoothing_window": _bounded_int(
                result.get("spectrum_smoothing_window", 0),
                0,
                10_000,
            ),
            "peaks": clean_peaks,
            "peak_reviews": clean_reviews,
            "matches": [
                _match_to_dict(match)
                for match in _bounded_sequence(matches, MAX_SESSION_MATCHES, "matches")
            ],
        },
    }


def write_analysis_session(path: str | Path, payload: Mapping[str, Any]) -> None:
    """Write one session payload as deterministic UTF-8 JSON."""

    output_path = Path(path)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def read_analysis_session(path: str | Path) -> dict[str, Any]:
    """Read and validate a ChromaTsvet analysis session."""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SessionFormatError("session file is not valid JSON") from exc
    except UnicodeError as exc:
        raise SessionFormatError("session file must be UTF-8 JSON") from exc

    return normalize_analysis_session_payload(payload)


def normalize_analysis_session_payload(payload: Any) -> dict[str, Any]:
    """Return a validated payload with reconstructed peak/review/match objects."""

    if not isinstance(payload, Mapping):
        raise SessionFormatError("session root must be an object")
    if payload.get("schema_version") != SESSION_SCHEMA_VERSION:
        raise SessionFormatError("unsupported session schema version")
    if payload.get("application") != "ChromaTsvet":
        raise SessionFormatError("not a ChromaTsvet session file")

    source = _mapping(payload.get("source"), "source")
    analysis = _mapping(payload.get("analysis"), "analysis")
    result = _mapping(payload.get("result"), "result")

    spectrum = _finite_float_list(result.get("spectrum"), "spectrum")
    frequency_axis = _finite_float_list(result.get("frequency_axis"), "frequency_axis")
    if not spectrum:
        raise SessionFormatError("session spectrum cannot be empty")
    if len(frequency_axis) != len(spectrum):
        raise SessionFormatError("frequency axis length must match spectrum length")

    settings = analysis_settings_from_dict(_mapping(analysis.get("settings"), "settings"))
    peaks = [
        _peak_from_dict(item)
        for item in _bounded_sequence(result.get("peaks", []), MAX_SESSION_PEAKS, "peaks")
    ]
    reviews = [
        _review_from_dict(item)
        for item in _bounded_sequence(
            result.get("peak_reviews", []),
            MAX_SESSION_PEAKS,
            "peak_reviews",
        )
    ]
    if len(reviews) != len(peaks):
        raise SessionFormatError("peak review count must match peak count")

    matches = [
        _match_from_dict(item)
        for item in _bounded_sequence(
            result.get("matches", []),
            MAX_SESSION_MATCHES,
            "matches",
        )
    ]

    return {
        "schema_version": SESSION_SCHEMA_VERSION,
        "application": "ChromaTsvet",
        "app_version": _safe_text(payload.get("app_version", "")),
        "rust_core_version": _safe_text(payload.get("rust_core_version", "")),
        "source_file_name": _safe_file_name(source.get("file_name", "session")),
        "data_points_count": _bounded_int(
            source.get("data_points_count", 0),
            0,
            MAX_SESSION_POINTS,
        ),
        "method_name": _safe_text(analysis.get("method_name", "custom")),
        "settings": settings,
        "processing_passport_rows": _rows_from_payload(
            analysis.get("processing_passport_rows", [])
        ),
        "processing_warnings": _safe_text_list(analysis.get("processing_warnings", [])),
        "result": {
            "spectrum": spectrum,
            "frequency_axis": frequency_axis,
            "sample_rate": _finite_or_none(result.get("sample_rate")),
            "normalized": bool(result.get("normalized", False)),
            "baseline_method": _safe_text(result.get("baseline_method", "")),
            "normalization": _safe_text(result.get("normalization", "")),
            "spectrum_smoothed": bool(result.get("spectrum_smoothed", False)),
            "spectrum_smoothing_method": _safe_text(
                result.get("spectrum_smoothing_method", "")
            ),
            "spectrum_smoothing_window": _bounded_int(
                result.get("spectrum_smoothing_window", 0),
                0,
                10_000,
            ),
            "peaks": peaks,
            "peak_reviews": reviews,
            "matches": matches,
        },
    }


def session_output_path(path: str | Path) -> str:
    """Return ``path`` with the ChromaTsvet session suffix when missing."""

    output_path = Path(path)
    if output_path.suffix:
        return str(output_path)
    return str(output_path.with_suffix(SESSION_SUFFIX))


def _peak_to_dict(peak: Any) -> dict[str, Any]:
    return {
        "frequency": _finite_or_none(getattr(peak, "frequency", None)),
        "position": _finite_or_none(getattr(peak, "position", None)),
        "intensity": _finite_or_none(getattr(peak, "intensity", None)),
        "prominence": _finite_or_none(getattr(peak, "prominence", None)),
        "baseline_level": _finite_or_none(getattr(peak, "baseline_level", None)),
        "left_base": _finite_or_none(getattr(peak, "left_base", None)),
        "right_base": _finite_or_none(getattr(peak, "right_base", None)),
        "width": _finite_or_none(getattr(peak, "width", None)),
        "width_hz": _finite_or_none(getattr(peak, "width_hz", None)),
        "area": _finite_or_none(getattr(peak, "area", None)),
        "noise": _finite_or_none(getattr(peak, "noise", None)),
        "snr": _finite_or_none(getattr(peak, "snr", None)),
        "is_global_max": bool(getattr(peak, "is_global_max", False)),
        "source": _safe_text(getattr(peak, "source", "")),
    }


def _peak_from_dict(payload: Any) -> SimpleNamespace:
    peak = _mapping(payload, "peak")
    frequency = _finite_or_none(peak.get("frequency"))
    position = _finite_or_none(peak.get("position"))
    intensity = _finite_or_none(peak.get("intensity"))
    if frequency is None and position is None:
        raise SessionFormatError("peak is missing finite frequency/position")
    if intensity is None:
        raise SessionFormatError("peak is missing finite intensity")

    return SimpleNamespace(
        frequency=frequency if frequency is not None else position,
        position=position if position is not None else frequency,
        intensity=intensity,
        prominence=_finite_or_none(peak.get("prominence")),
        baseline_level=_finite_or_none(peak.get("baseline_level")),
        left_base=_finite_or_none(peak.get("left_base")),
        right_base=_finite_or_none(peak.get("right_base")),
        width=_finite_or_none(peak.get("width")),
        width_hz=_finite_or_none(peak.get("width_hz")),
        area=_finite_or_none(peak.get("area")),
        noise=_finite_or_none(peak.get("noise")),
        snr=_finite_or_none(peak.get("snr")),
        is_global_max=bool(peak.get("is_global_max", False)),
        source=_safe_text(peak.get("source", "")),
    )


def _review_to_dict(review: PeakReview) -> dict[str, Any]:
    status = review.status if review.status in PEAK_REVIEW_STATUSES else "suspicious"
    return {
        "status": status,
        "reason": _safe_text(review.reason),
        "flags": _safe_text_list(review.flags),
        "user_modified": bool(review.user_modified),
    }


def _review_from_dict(payload: Any) -> PeakReview:
    review = _mapping(payload, "peak_review")
    status = _safe_text(review.get("status", "suspicious")).lower()
    if status not in PEAK_REVIEW_STATUSES:
        status = "suspicious"
    return PeakReview(
        status=status,
        reason=_safe_text(review.get("reason", status)),
        flags=tuple(_safe_text_list(review.get("flags", []))),
        user_modified=bool(review.get("user_modified", False)),
    )


def _match_to_dict(match: Any) -> dict[str, Any]:
    return {
        "substance_name": _safe_text(getattr(match, "substance_name", "")),
        "formula": _safe_text(getattr(match, "formula", "")),
        "score": _finite_or_none(getattr(match, "score", 0.0)) or 0.0,
        "compared_points": _bounded_int(
            getattr(match, "compared_points", getattr(match, "matched_points", 0)),
            0,
            MAX_SESSION_PEAKS,
        ),
    }


def _match_from_dict(payload: Any) -> SimpleNamespace:
    match = _mapping(payload, "match")
    return SimpleNamespace(
        substance_name=_safe_text(match.get("substance_name", "")),
        formula=_safe_text(match.get("formula", "")),
        score=_finite_or_none(match.get("score")) or 0.0,
        compared_points=_bounded_int(match.get("compared_points", 0), 0, MAX_SESSION_PEAKS),
    )


def _finite_float_list(values: Any, field_name: str) -> list[float]:
    sequence = _bounded_sequence(values, MAX_SESSION_POINTS, field_name)
    result: list[float] = []
    for value in sequence:
        numeric_value = _finite_or_none(value)
        if numeric_value is None:
            raise SessionFormatError(f"{field_name} contains a non-finite value")
        result.append(numeric_value)
    return result


def _bounded_sequence(values: Any, maximum: int, field_name: str) -> Sequence[Any]:
    if values is None:
        return []
    if hasattr(values, "tolist"):
        values = values.tolist()
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise SessionFormatError(f"{field_name} must be a list")
    if len(values) > maximum:
        raise SessionFormatError(f"{field_name} is too large")
    return values


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SessionFormatError(f"{field_name} must be an object")
    return value


def _finite_or_none(value: Any) -> float | None:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric_value):
        return None
    return numeric_value


def _bounded_int(value: Any, default: int, maximum: int) -> int:
    try:
        numeric_value = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(maximum, numeric_value))


def _safe_file_name(value: Any) -> str:
    text = _safe_text(value or "session")
    return Path(text).name or "session"


def _safe_text(value: Any, max_length: int = MAX_TEXT_LENGTH) -> str:
    text = str("" if value is None else value).strip()
    text = _ABSOLUTE_PATH_PATTERN.sub(lambda match: f".../{match.group('name')}", text)
    return text[:max_length]


def _safe_text_list(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return []
    return [_safe_text(value) for value in values[:100]]


def _rows_to_dicts(rows: Sequence[tuple[Any, Any]]) -> list[dict[str, str]]:
    normalized_rows: list[dict[str, str]] = []
    for row in _bounded_sequence(rows, 1_000, "processing_passport_rows"):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)):
            raise SessionFormatError("processing passport row must be a label/value pair")
        if len(row) != 2:
            raise SessionFormatError("processing passport row must be a label/value pair")
        label, value = row
        normalized_rows.append({"label": _safe_text(label), "value": _safe_text(value)})
    return normalized_rows


def _rows_from_payload(rows: Any) -> list[tuple[str, str]]:
    normalized_rows: list[tuple[str, str]] = []
    for row in _bounded_sequence(rows, 1_000, "processing_passport_rows"):
        if not isinstance(row, Mapping):
            raise SessionFormatError("processing passport row must be an object")
        normalized_rows.append(
            (_safe_text(row.get("label", "")), _safe_text(row.get("value", "")))
        )
    return normalized_rows
