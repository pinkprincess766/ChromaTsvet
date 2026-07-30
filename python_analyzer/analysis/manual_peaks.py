"""Manual peak helpers for GUI-side review corrections."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True)
class EditablePeak:
    """Peak shape used for user-added or user-edited peak rows."""

    frequency: float
    position: float
    intensity: float
    width: float = 0.0
    width_hz: float = 0.0
    area: float = 0.0
    snr: float = 0.0
    source: str = "manual"


def editable_peak_from_values(
    *,
    frequency: Any,
    position: Any,
    intensity: Any,
    width: Any = 0.0,
    width_hz: Any = 0.0,
    area: Any = 0.0,
    snr: Any = 0.0,
    source: str = "manual",
) -> EditablePeak:
    """Create a finite editable peak or raise ValueError."""

    normalized_frequency = _required_finite_float(frequency, "frequency")
    normalized_position = _required_finite_float(position, "position")
    normalized_intensity = _required_finite_float(intensity, "intensity")
    return EditablePeak(
        frequency=max(0.0, normalized_frequency),
        position=max(0.0, normalized_position),
        intensity=normalized_intensity,
        width=max(0.0, _optional_finite_float(width)),
        width_hz=max(0.0, _optional_finite_float(width_hz)),
        area=max(0.0, _optional_finite_float(area)),
        snr=max(0.0, _optional_finite_float(snr)),
        source=str(source or "manual"),
    )


def _required_finite_float(value: Any, label: str) -> float:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(numeric_value):
        raise ValueError(f"{label} must be a finite number")
    return numeric_value


def _optional_finite_float(value: Any) -> float:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return numeric_value if math.isfinite(numeric_value) else 0.0
