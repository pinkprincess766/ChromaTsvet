"""Data models for analysis configuration and loaded data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AnalysisSettings:
    sample_rate: float
    filter_type: str
    filter_params: dict[str, Any]
    baseline_enabled: bool
    baseline_method: str
    peak_threshold: float
    peak_prominence: float
    peak_distance: int
    normalize_area: bool
    window_type: str = "hann"


@dataclass
class LoadedSpectrum:
    data: list[float]
    file_path: str | None
    file_name: str
