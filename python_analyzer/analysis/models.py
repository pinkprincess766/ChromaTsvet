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
    peak_min_snr: float = 0.0
    window_type: str = "hann"
    spectrum_smoothing_enabled: bool = False
    spectrum_smoothing_method: str = "savgol"
    spectrum_smoothing_window: int = 7
    peak_frequency_tolerance: float = 5.0  # Hz or appropriate units for peak matching
    data_type: str = "generic"  # e.g. "ir", "raman", "ms", "fluorescence"


@dataclass
class LoadedSpectrum:
    data: list[float]
    file_path: str | None
    file_name: str


@dataclass
class ReferencePeak:
    """A peak feature stored for a reference compound."""
    # Science is what we understand well enough to explain to a computer. Art is everything else we do
    frequency: float
    intensity: float
    width: float = 0.0
    width_hz: float = 0.0
    area: float = 0.0
    snr: float = 0.0


@dataclass
class PeakMatch:
    """Result of matching one unknown peak to one reference peak."""
    unknown_frequency: float
    reference_frequency: float
    frequency_diff: float
    intensity_ratio: float
    score: float
    unknown_index: int = -1
    reference_index: int = -1


@dataclass
class PeakBasedMatchResult:
    """Result of peak-based identification."""
    substance_name: str
    formula: str
    score: float
    matched_peaks: list[PeakMatch]
    unmatched_unknown: list[ReferencePeak]
    unmatched_reference: list[ReferencePeak]
    num_matched: int
    unknown_peak_count: int = 0
    reference_peak_count: int = 0
    sample_coverage: float = 0.0
    reference_coverage: float = 0.0
    mean_frequency_error: float | None = None
    max_frequency_error: float | None = None
    evidence_level: str = "insufficient"
    method: str = "peak"

    @property
    def compared_points(self) -> int:
        """Compatibility alias used by older reports and session files."""

        return self.num_matched
