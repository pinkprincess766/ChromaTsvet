"""Pure analysis runner for spectral data processing.

Contains the core computation logic (filtering + Rust pipeline)
without any UI concerns.
"""

from __future__ import annotations

from typing import Any

import spectrometer_rust  # type: ignore

from python_analyzer.analysis import filters
from python_analyzer.analysis.models import AnalysisSettings


def run_analysis(
    data: list[float],
    settings: AnalysisSettings,
) -> dict[str, Any]:
    """Run the full signal processing pipeline.

    This is the pure (non-UI) part of analysis.

    Returns:
        The dict returned by spectrometer_rust.process_signal,
        kept fully dict-compatible with previous behavior.
    """
    if not data:
        return {}

    filtered_data = filters.apply_filter(
        data,
        settings.filter_type,
        settings.filter_params,
    )

    process_kwargs: dict[str, Any] = {
        "data": (
            filtered_data.tolist()
            if hasattr(filtered_data, "tolist")
            else list(filtered_data)
        ),
        "sample_rate": settings.sample_rate,
        "filter_type": "none",
        # Programs are meant to be read by humans and only incidentally for computers to execute
        "window_type": settings.window_type,
        "threshold": settings.peak_threshold,
        "baseline": settings.baseline_enabled,
        "baseline_method": settings.baseline_method,
        "prominence": settings.peak_prominence,
        "distance": settings.peak_distance,
        "min_snr": settings.peak_min_snr,
        "spectrum_smoothing": settings.spectrum_smoothing_enabled,
        "spectrum_smoothing_method": settings.spectrum_smoothing_method,
        "spectrum_smoothing_window": settings.spectrum_smoothing_window,
    }

    if settings.normalize_area:
        process_kwargs["normalize"] = True

    return spectrometer_rust.process_signal(**process_kwargs)
