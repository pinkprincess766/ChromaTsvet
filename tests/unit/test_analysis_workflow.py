from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from python_analyzer.analysis.models import AnalysisSettings
from python_analyzer.analysis.peak_review import PEAK_REVIEW_ACCEPTED
from python_analyzer.analysis.workflow import (
    AnalysisResultError,
    run_analysis_workflow,
)


def analysis_settings(**overrides) -> AnalysisSettings:
    values = {
        "sample_rate": 800.0,
        "filter_type": "none",
        "filter_params": {},
        "baseline_enabled": True,
        "baseline_method": "improved",
        "peak_threshold": 0.1,
        "peak_prominence": 0.0,
        "peak_distance": 1,
        "normalize_area": False,
    }
    values.update(overrides)
    return AnalysisSettings(**values)


def test_workflow_returns_validated_headless_outcome():
    peak = SimpleNamespace(frequency=200.0, position=1.0, intensity=3.0)
    raw_result = {
        "spectrum": [1.0, 3.0, 2.0],
        "frequency_axis": [0.0, 200.0, 400.0],
        "peaks": [peak],
    }
    processor = Mock(return_value=raw_result)

    outcome = run_analysis_workflow(
        [0.0, 1.0, 0.0, -1.0],
        analysis_settings(),
        processor=processor,
    )

    assert outcome.result is raw_result
    np.testing.assert_allclose(outcome.spectrum, [1.0, 3.0, 2.0])
    np.testing.assert_allclose(outcome.frequency_axis, [0.0, 200.0, 400.0])
    assert outcome.peaks == [peak]
    assert outcome.peak_reviews[0].status == PEAK_REVIEW_ACCEPTED
    assert processor.call_args.kwargs["filter_type"] == "none"


def test_workflow_rebuilds_missing_frequency_axis_from_analysis_settings():
    processor = Mock(return_value={"spectrum": [2.0, 1.0, 0.5], "peaks": []})

    outcome = run_analysis_workflow(
        [0.0, 1.0, 0.0, -1.0],
        analysis_settings(sample_rate=400.0),
        processor=processor,
    )

    np.testing.assert_allclose(outcome.frequency_axis, [0.0, 100.0, 200.0])


@pytest.mark.parametrize(
    "invalid_axis",
    (
        [0.0, 200.0, 100.0],
        [0.0, 0.0, 200.0],
        [[0.0, 100.0, 200.0]],
    ),
)
def test_workflow_rebuilds_non_physical_frequency_axis(invalid_axis):
    processor = Mock(
        return_value={
            "spectrum": [2.0, 1.0, 0.5],
            "frequency_axis": invalid_axis,
            "peaks": [],
        }
    )

    outcome = run_analysis_workflow(
        [0.0, 1.0, 0.0, -1.0],
        analysis_settings(sample_rate=400.0),
        processor=processor,
    )

    np.testing.assert_allclose(outcome.frequency_axis, [0.0, 100.0, 200.0])


@pytest.mark.parametrize(
    "invalid_spectrum",
    (
        [[1.0, 2.0], [3.0, 4.0]],
        [1.0, float("nan")],
        [1.0, float("inf")],
        ["not-a-number"],
    ),
)
def test_workflow_rejects_unsafe_spectrum_values(invalid_spectrum):
    processor = Mock(
        return_value={
            "spectrum": invalid_spectrum,
            "frequency_axis": [0.0, 1.0],
            "peaks": [],
        }
    )

    with pytest.raises(AnalysisResultError):
        run_analysis_workflow(
            [0.0, 1.0],
            analysis_settings(),
            processor=processor,
        )


@pytest.mark.parametrize("invalid_peaks", (None, "peak", 42))
def test_workflow_rejects_invalid_peak_collections(invalid_peaks):
    processor = Mock(
        return_value={
            "spectrum": [1.0, 0.5],
            "frequency_axis": [0.0, 400.0],
            "peaks": invalid_peaks,
        }
    )

    with pytest.raises(AnalysisResultError, match="peak list"):
        run_analysis_workflow(
            [0.0, 1.0],
            analysis_settings(),
            processor=processor,
        )


def test_workflow_rejects_invalid_result_container():
    processor = Mock(return_value=[1.0, 2.0])

    with pytest.raises(AnalysisResultError, match="result container"):
        run_analysis_workflow(
            [0.0, 1.0],
            analysis_settings(),
            processor=processor,
        )
