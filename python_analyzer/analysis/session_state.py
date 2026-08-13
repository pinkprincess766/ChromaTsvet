"""Explicit in-memory state for one analyzed spectrum."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from python_analyzer.analysis.models import AnalysisSettings
from python_analyzer.analysis.peak_review import PeakReview


@dataclass(frozen=True)
class AnalysisSessionState:
    """Snapshot of the current analysis independent from Qt widgets."""

    source_file_name: str
    data_points_count: int
    settings: AnalysisSettings
    method_name: str
    result: Mapping[str, Any]
    frequency_axis: Sequence[Any]
    spectrum: Sequence[Any]
    peaks: Sequence[Any]
    peak_reviews: Sequence[PeakReview]
    matches: Sequence[Any]
