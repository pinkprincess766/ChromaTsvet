"""CSV export for detected spectral peaks."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .spreadsheet_safety import safe_spreadsheet_cell


PEAK_CSV_HEADERS = [
    "source_file",
    "sample_rate_hz",
    "filter_type",
    "baseline",
    "normalization",
    "spectrum_smoothing",
    "spectrum_smoothing_method",
    "spectrum_smoothing_window",
    "peak_min_snr",
    "data_type",
    "peak_frequency_tolerance_hz",
    "frequency_hz",
    "position_bin",
    "intensity",
    "width_bins",
    "width_hz",
    "area",
    "snr",
    "review_status",
    "review_reason",
]

_METADATA_COLUMNS = PEAK_CSV_HEADERS[:11]


def write_peaks_csv(
    file_path: str | Path,
    peaks: Sequence[Any],
    metadata: Mapping[str, Any],
    peak_reviews: Sequence[Any] | None = None,
) -> None:
    """Write detected peaks as a flat, analysis-aware CSV table."""
    with Path(file_path).open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(PEAK_CSV_HEADERS)
        for index, peak in enumerate(peaks):
            review = _review_at(peak_reviews, index)
            row = [
                *(metadata.get(column, "") for column in _METADATA_COLUMNS),
                _peak_frequency(peak),
                _peak_value(peak, "position"),
                _peak_value(peak, "intensity"),
                _peak_value(peak, "width"),
                _peak_value(peak, "width_hz"),
                _peak_value(peak, "area"),
                _peak_value(peak, "snr"),
                getattr(review, "status", ""),
                getattr(review, "reason", ""),
            ]
            writer.writerow([safe_spreadsheet_cell(value) for value in row])


def _peak_value(peak: Any, name: str) -> Any:
    return getattr(peak, name, "")


def _peak_frequency(peak: Any) -> Any:
    frequency = getattr(peak, "frequency", None)
    try:
        frequency = float(frequency)
    except (TypeError, ValueError):
        frequency = None

    if frequency is not None and math.isfinite(frequency):
        return frequency
    return _peak_value(peak, "position")


def _review_at(peak_reviews: Sequence[Any] | None, index: int) -> Any:
    if peak_reviews is None or index >= len(peak_reviews):
        return None
    return peak_reviews[index]
