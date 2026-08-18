"""Build reusable report data from an analysis session state."""

from __future__ import annotations

from datetime import datetime
import math
import re
from typing import Any

from python_analyzer.analysis.peak_review import (
    PEAK_REVIEW_ACCEPTED,
    PEAK_REVIEW_REJECTED,
    review_summary,
)
from python_analyzer.analysis.processing_passport import build_processing_passport
from python_analyzer.analysis.session_state import AnalysisSessionState
from python_analyzer.exporters.pdf_report import PDFMatchRow, PDFReportData


_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
MAX_REPORT_MATCH_TEXT = 200


def build_report_data(
    state: AnalysisSessionState,
    *,
    app_version: str,
    rust_core_version: str,
    generated_at: datetime | None = None,
) -> PDFReportData:
    """Build report rows without reading Qt tables or mutable window state."""

    generated_at = generated_at or datetime.now()
    peaks = list(state.peaks)
    source_file_name = state.source_file_name
    summary_rows: list[tuple[str, Any]] = [
        ("Date", f"{generated_at:%Y-%m-%d %H:%M}"),
        ("App version", app_version),
        ("Rust core", rust_core_version),
        ("Source file", source_file_name),
        ("Data points", str(state.data_points_count)),
        ("Peaks found", str(len(peaks))),
    ]

    accepted_peaks = None
    rejected_peaks = None
    if state.peak_reviews:
        counts = review_summary(state.peak_reviews)
        accepted_peaks = counts[PEAK_REVIEW_ACCEPTED]
        rejected_peaks = counts[PEAK_REVIEW_REJECTED]
        summary_rows.extend(
            [
                ("Accepted peaks", str(accepted_peaks)),
                ("Rejected peaks", str(rejected_peaks)),
            ]
        )

    settings = state.settings
    result = state.result
    baseline_description = (
        settings.baseline_method if settings.baseline_enabled else "disabled"
    )
    normalization_description = "area" if result.get("normalized") else "disabled"
    smoothing_description = (
        f"{settings.spectrum_smoothing_method}/{settings.spectrum_smoothing_window}"
        if settings.spectrum_smoothing_enabled
        else "disabled"
    )
    parameter_rows = [
        ("Analysis method", state.method_name or "custom"),
        ("Sample rate", f"{settings.sample_rate:g} Hz"),
        ("FFT window", settings.window_type),
        ("Signal filter", settings.filter_type),
        ("Filter params", settings.filter_params),
        ("Baseline", baseline_description),
        ("Spectrum smoothing", smoothing_description),
        ("Normalization", normalization_description),
        ("Data type", settings.data_type),
        ("Peak tolerance", f"{settings.peak_frequency_tolerance:g} Hz"),
        ("Threshold", f"{settings.peak_threshold:.3f}"),
        (
            "Prominence",
            "automatic"
            if settings.peak_prominence == 0
            else f"{settings.peak_prominence:g}",
        ),
        (
            "Minimum SNR",
            "disabled" if settings.peak_min_snr == 0 else f"{settings.peak_min_snr:g}",
        ),
        ("Distance", f"{settings.peak_distance} points"),
    ]
    processing_passport = build_processing_passport(
        settings=settings,
        result=result,
        source_file_name=source_file_name,
        data_points_count=state.data_points_count,
        peaks_count=len(peaks),
        app_version=app_version,
        rust_core_version=rust_core_version,
        generated_at=generated_at,
        method_name=state.method_name or "custom",
        accepted_peaks=accepted_peaks,
        rejected_peaks=rejected_peaks,
    )

    return PDFReportData(
        title="ChromaTsvet Analysis Report",
        subtitle="Spectral data and chromatogram analysis",
        summary_rows=summary_rows,
        parameter_rows=parameter_rows,
        processing_passport_rows=list(processing_passport.rows),
        peaks=peaks,
        matches=[_match_to_pdf_row(match) for match in state.matches],
        source_file_name=source_file_name,
        data_points_count=state.data_points_count,
        peaks_count=len(peaks),
    )


def _match_to_pdf_row(match: Any) -> PDFMatchRow:
    method = str(getattr(match, "method", "legacy_cosine"))
    is_peak_match = method == "peak"
    return PDFMatchRow(
        substance_name=_safe_report_text(getattr(match, "substance_name", "")),
        formula=_safe_report_text(getattr(match, "formula", "")),
        score=_format_number(getattr(match, "score", None), 3),
        compared_points=str(
            getattr(match, "compared_points", getattr(match, "matched_points", ""))
        ),
        method="peak" if is_peak_match else "legacy cosine",
        evidence_level=_safe_report_text(
            getattr(match, "evidence_level", "legacy" if not is_peak_match else "insufficient")
        ),
        sample_coverage=(
            _format_percent(getattr(match, "sample_coverage", None))
            if is_peak_match
            else "n/a"
        ),
        reference_coverage=(
            _format_percent(getattr(match, "reference_coverage", None))
            if is_peak_match
            else "n/a"
        ),
        mean_frequency_error=(
            _format_number(getattr(match, "mean_frequency_error", None), 4)
            if is_peak_match
            else "n/a"
        ),
    )


def _format_percent(value: Any) -> str:
    numeric_value = _finite_number(value)
    if numeric_value is None:
        return "n/a"
    return f"{max(0.0, min(1.0, numeric_value)) * 100:.1f}%"


def _format_number(value: Any, precision: int) -> str:
    numeric_value = _finite_number(value)
    return "n/a" if numeric_value is None else f"{numeric_value:.{precision}f}"


def _finite_number(value: Any) -> float | None:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    return numeric_value if math.isfinite(numeric_value) else None


def _safe_report_text(value: Any) -> str:
    text = _CONTROL_CHARACTER_PATTERN.sub(" ", str("" if value is None else value))
    return " ".join(text.split())[:MAX_REPORT_MATCH_TEXT]
