"""Frequency-axis validation shared by analysis and visualization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from numpy.typing import NDArray


def resolve_frequency_axis(
    result: Mapping[str, Any],
    spectrum_len: int,
    *,
    sample_rate: Any = None,
    source_signal_len: Any = None,
) -> NDArray[np.float64]:
    """Return a finite frequency axis or rebuild it from trusted metadata."""

    try:
        frequency_axis = np.asarray(
            result.get("frequency_axis", []),
            dtype=np.float64,
        )
    except (TypeError, ValueError):
        frequency_axis = np.asarray([], dtype=np.float64)

    if (
        frequency_axis.ndim != 1
        or len(frequency_axis) != spectrum_len
        or not np.all(np.isfinite(frequency_axis))
        or (frequency_axis.size and frequency_axis[0] < 0.0)
        or (frequency_axis.size > 1 and not np.all(np.diff(frequency_axis) > 0.0))
    ):
        fallback_sample_rate = result.get("sample_rate", sample_rate)
        if fallback_sample_rate is None:
            fallback_sample_rate = sample_rate
        return rebuild_frequency_axis(
            spectrum_len,
            fallback_sample_rate,
            source_signal_len,
        )
    return frequency_axis


def rebuild_frequency_axis(
    spectrum_len: int,
    sample_rate: Any,
    source_signal_len: Any,
) -> NDArray[np.float64]:
    """Rebuild an FFT axis using ``bin_width = sample_rate / signal_len``."""

    if spectrum_len == 0:
        return np.asarray([], dtype=np.float64)

    try:
        sample_rate_value = float(sample_rate)
        source_length_value = int(source_signal_len)
    except (TypeError, ValueError):
        raise ValueError(
            "Frequency axis is missing or invalid and cannot be rebuilt "
            "without sample_rate and source_signal_len."
        ) from None

    if (
        not np.isfinite(sample_rate_value)
        or sample_rate_value <= 0.0
        or source_length_value <= 0
        or spectrum_len > source_length_value
    ):
        raise ValueError(
            "Frequency axis is missing or invalid and fallback metadata is invalid."
        )

    bin_width = sample_rate_value / source_length_value
    return np.arange(spectrum_len, dtype=np.float64) * bin_width
