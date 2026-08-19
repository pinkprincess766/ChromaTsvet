"""Pure analysis runner for spectral data processing.

Contains the core computation logic (filtering + Rust pipeline)
without any UI concerns.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from python_analyzer.analysis import filters
from python_analyzer.analysis.models import AnalysisSettings


SignalProcessor = Callable[..., dict[str, Any]]


def build_process_signal_kwargs(
    filtered_signal: Any,
    settings: AnalysisSettings,
) -> dict[str, Any]:
    """Build the explicit Python-to-Rust processing contract.

    Filtering remains Python-owned. The Rust pipeline therefore receives the
    already filtered signal with ``filter_type='none'``.
    """
    process_kwargs: dict[str, Any] = {
        "data": (
            filtered_signal.tolist()
            if hasattr(filtered_signal, "tolist")
            else list(filtered_signal)
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

    return process_kwargs


def _default_signal_processor(**kwargs: Any) -> dict[str, Any]:
    """Load the native extension only when the production processor is used."""
    import spectrometer_rust  # type: ignore

    return spectrometer_rust.process_signal(**kwargs)


def run_analysis(
    data: list[float],
    settings: AnalysisSettings,
    *,
    processor: SignalProcessor | None = None,
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

    process_kwargs = build_process_signal_kwargs(filtered_data, settings)
    signal_processor = (
        processor if processor is not None else _default_signal_processor
    )
    return signal_processor(**process_kwargs)
