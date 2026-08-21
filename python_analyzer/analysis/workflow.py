"""Headless orchestration for one spectrum-analysis operation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from python_analyzer.analysis.frequency_axis import resolve_frequency_axis
from python_analyzer.analysis.models import AnalysisSettings
from python_analyzer.analysis.peak_review import PeakReview, review_peaks
from python_analyzer.analysis.runner import SignalProcessor, run_analysis


class AnalysisResultError(ValueError):
    """Raised when a processor returns an unsafe or malformed result."""


@dataclass(frozen=True)
class AnalysisOutcome:
    """Validated numerical output prepared for GUI or batch consumers."""

    result: dict[str, Any]
    spectrum: NDArray[np.float64]
    frequency_axis: NDArray[np.float64]
    peaks: list[Any]
    peak_reviews: list[PeakReview]


def run_analysis_workflow(
    signal: list[float],
    settings: AnalysisSettings,
    *,
    processor: SignalProcessor | None = None,
) -> AnalysisOutcome:
    """Run and validate one spectrum without importing Qt."""

    result = run_analysis(signal, settings, processor=processor)
    if not isinstance(result, dict):
        raise AnalysisResultError(
            "Analysis processor returned an invalid result container."
        )
    spectrum = _validated_spectrum(result)
    frequency_axis = resolve_frequency_axis(
        result,
        len(spectrum),
        sample_rate=settings.sample_rate,
        source_signal_len=len(signal),
    )
    peaks = _validated_peaks(result)
    return AnalysisOutcome(
        result=result,
        spectrum=spectrum,
        frequency_axis=frequency_axis,
        peaks=peaks,
        peak_reviews=review_peaks(peaks, settings),
    )


def _validated_spectrum(result: dict[str, Any]) -> NDArray[np.float64]:
    try:
        spectrum = np.asarray(result.get("spectrum", []), dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise AnalysisResultError(
            "Analysis processor returned a non-numeric spectrum."
        ) from exc

    if spectrum.ndim != 1:
        raise AnalysisResultError("Analysis processor returned a non-1D spectrum.")
    if spectrum.size and not np.all(np.isfinite(spectrum)):
        raise AnalysisResultError(
            "Analysis processor returned NaN or infinite spectrum values."
        )
    return np.ascontiguousarray(spectrum, dtype=np.float64)


def _validated_peaks(result: dict[str, Any]) -> list[Any]:
    raw_peaks = result.get("peaks", [])
    if raw_peaks is None or isinstance(raw_peaks, (str, bytes, bytearray)):
        raise AnalysisResultError("Analysis processor returned an invalid peak list.")
    try:
        return list(raw_peaks)
    except TypeError as exc:
        raise AnalysisResultError(
            "Analysis processor returned a non-iterable peak list."
        ) from exc
