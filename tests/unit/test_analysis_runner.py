from __future__ import annotations

from unittest.mock import Mock, patch

import numpy as np
import pytest

from python_analyzer.analysis.models import AnalysisSettings
from python_analyzer.analysis.runner import (
    build_process_signal_kwargs,
    run_analysis,
)


def analysis_settings(**overrides) -> AnalysisSettings:
    values = {
        "sample_rate": 800.0,
        "filter_type": "median",
        "filter_params": {"window_size": 3},
        "baseline_enabled": True,
        "baseline_method": "linear",
        "peak_threshold": 0.15,
        "peak_prominence": 0.25,
        "peak_distance": 4,
        "normalize_area": False,
        "peak_min_snr": 2.5,
        "window_type": "hamming",
        "spectrum_smoothing_enabled": True,
        "spectrum_smoothing_method": "median",
        "spectrum_smoothing_window": 5,
    }
    values.update(overrides)
    return AnalysisSettings(**values)


def test_build_process_signal_kwargs_preserves_pipeline_contract():
    settings = analysis_settings()

    kwargs = build_process_signal_kwargs(np.array([1.0, 2.0]), settings)

    assert kwargs == {
        "data": [1.0, 2.0],
        "sample_rate": 800.0,
        "filter_type": "none",
        "window_type": "hamming",
        "threshold": 0.15,
        "baseline": True,
        "baseline_method": "linear",
        "prominence": 0.25,
        "distance": 4,
        "min_snr": 2.5,
        "spectrum_smoothing": True,
        "spectrum_smoothing_method": "median",
        "spectrum_smoothing_window": 5,
    }


def test_build_process_signal_kwargs_only_enables_normalization_explicitly():
    disabled = build_process_signal_kwargs([1.0], analysis_settings())
    enabled = build_process_signal_kwargs(
        [1.0],
        analysis_settings(normalize_area=True),
    )

    assert "normalize" not in disabled
    assert enabled["normalize"] is True


def test_run_analysis_filters_before_calling_injected_processor():
    processor = Mock(return_value={"spectrum": [3.0], "peaks": []})
    filtered = np.array([0.25, 0.5, 0.75])
    settings = analysis_settings()

    with patch(
        "python_analyzer.analysis.runner.filters.apply_filter",
        return_value=filtered,
    ) as apply_filter:
        result = run_analysis([0.0, 1.0, 0.0], settings, processor=processor)

    apply_filter.assert_called_once_with(
        [0.0, 1.0, 0.0],
        "median",
        {"window_size": 3},
    )
    processor.assert_called_once()
    assert processor.call_args.kwargs["data"] == [0.25, 0.5, 0.75]
    assert processor.call_args.kwargs["filter_type"] == "none"
    assert result == {"spectrum": [3.0], "peaks": []}


def test_run_analysis_does_not_invoke_processor_for_empty_signal():
    processor = Mock()

    assert run_analysis([], analysis_settings(), processor=processor) == {}
    processor.assert_not_called()


def test_run_analysis_propagates_processor_failure():
    processor = Mock(side_effect=RuntimeError("native pipeline failed"))

    with pytest.raises(RuntimeError, match="native pipeline failed"):
        run_analysis([0.0, 1.0, 0.0], analysis_settings(), processor=processor)
