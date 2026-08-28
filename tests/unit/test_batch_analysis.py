from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from python_analyzer.analysis import batch as batch_module
from python_analyzer.analysis.batch import (
    BATCH_STATUS_FAILED,
    BATCH_STATUS_SUCCESS,
    BatchSelectionError,
    analyze_spectrum_files,
)
from python_analyzer.analysis.models import AnalysisSettings


def analysis_settings() -> AnalysisSettings:
    return AnalysisSettings(
        sample_rate=100.0,
        filter_type="none",
        filter_params={},
        baseline_enabled=True,
        baseline_method="improved",
        peak_threshold=0.1,
        peak_prominence=0.0,
        peak_distance=1,
        normalize_area=False,
    )


def valid_result(*, warnings=()):
    peak = SimpleNamespace(
        frequency=25.0,
        position=1.0,
        intensity=2.0,
        prominence=1.0,
        snr=10.0,
        area=1.0,
        width=1.0,
    )
    return {
        "spectrum": [0.5, 2.0, 0.5],
        "frequency_axis": [0.0, 25.0, 50.0],
        "peaks": [peak],
        "processing_warnings": warnings,
    }


def write_spectrum(path: Path, content: str = "intensity\n0.5\n2.0\n0.5\n") -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_batch_isolates_per_file_failures_and_preserves_order(tmp_path):
    first = write_spectrum(tmp_path / "first.csv")
    unsupported = tmp_path / "private-parent" / "broken.bin"
    second = write_spectrum(tmp_path / "second.txt")
    processor = Mock(return_value=valid_result(warnings=("warning",)))

    summary = analyze_spectrum_files(
        [first, unsupported, second],
        analysis_settings(),
        processor=processor,
    )

    assert [item.source_name for item in summary.items] == [
        "first.csv",
        "broken.bin",
        "second.txt",
    ]
    assert [item.status for item in summary.items] == [
        BATCH_STATUS_SUCCESS,
        BATCH_STATUS_FAILED,
        BATCH_STATUS_SUCCESS,
    ]
    assert summary.successful_count == 2
    assert summary.failed_count == 1
    assert summary.items[0].point_count == 3
    assert summary.items[0].peak_count == 1
    assert summary.items[0].warning_count == 1
    assert summary.items[0].peak_details_available is True
    assert len(summary.items[0].peak_records) == 1
    assert summary.items[0].peak_records[0].frequency == 25.0
    assert summary.items[0].peak_records[0].review_status == "accepted"
    assert str(tmp_path) not in summary.items[1].error_message
    assert processor.call_count == 2


def test_batch_counts_skipped_rows_without_retaining_values(tmp_path):
    source = write_spectrum(
        tmp_path / "dirty.csv",
        "intensity\n0.5\nsecret-payload\n2.0\n0.5\n",
    )

    summary = analyze_spectrum_files(
        [source],
        analysis_settings(),
        processor=Mock(return_value=valid_result()),
    )

    item = summary.items[0]
    assert item.status == BATCH_STATUS_SUCCESS
    assert item.point_count == 3
    assert item.skipped_row_count == 1
    assert "secret-payload" not in repr(summary)


def test_batch_cancellation_stops_before_next_native_call(tmp_path):
    files = [
        write_spectrum(tmp_path / "first.csv"),
        write_spectrum(tmp_path / "second.csv"),
        write_spectrum(tmp_path / "third.csv"),
    ]
    completed = []
    processor = Mock(return_value=valid_result())

    summary = analyze_spectrum_files(
        files,
        analysis_settings(),
        processor=processor,
        should_cancel=lambda: bool(completed),
        on_item_finished=completed.append,
    )

    assert summary.cancelled is True
    assert summary.requested_count == 3
    assert len(summary.items) == 1
    assert processor.call_count == 1


def test_batch_masks_unexpected_exception_details_and_continues(tmp_path):
    files = [
        write_spectrum(tmp_path / "first.csv"),
        write_spectrum(tmp_path / "second.csv"),
    ]
    private_path = "/Users/example/private/secret-spectrum.csv"
    processor = Mock(
        side_effect=[RuntimeError(f"failed at {private_path}"), valid_result()]
    )

    summary = analyze_spectrum_files(
        files,
        analysis_settings(),
        processor=processor,
    )

    assert summary.items[0].status == BATCH_STATUS_FAILED
    assert summary.items[0].error_message == "Analysis failed (RuntimeError)."
    assert private_path not in repr(summary)
    assert summary.items[1].status == BATCH_STATUS_SUCCESS


def test_batch_sanitizes_control_characters_in_displayed_file_name(tmp_path):
    source = write_spectrum(tmp_path / "line\nbreak.csv")
    progress_names = []

    summary = analyze_spectrum_files(
        [source],
        analysis_settings(),
        processor=Mock(return_value=valid_result()),
        on_progress=lambda _index, _total, name: progress_names.append(name),
    )

    assert summary.items[0].source_name == "line?break.csv"
    assert progress_names == ["line?break.csv"]


@pytest.mark.parametrize("selection", ([], "one.csv", Path("one.csv")))
def test_batch_rejects_invalid_selection_shape(selection):
    with pytest.raises(BatchSelectionError):
        analyze_spectrum_files(selection, analysis_settings())


def test_batch_rejects_selection_above_named_limit():
    with pytest.raises(BatchSelectionError, match="no more than 2"):
        analyze_spectrum_files(
            ["one.csv", "two.csv", "three.csv"],
            analysis_settings(),
            max_files=2,
        )


def test_batch_stops_consuming_selection_after_named_limit():
    consumed = []

    def generated_paths():
        for index in range(10_000):
            consumed.append(index)
            yield f"{index}.csv"

    with pytest.raises(BatchSelectionError, match="no more than 2"):
        analyze_spectrum_files(
            generated_paths(),
            analysis_settings(),
            max_files=2,
        )

    assert consumed == [0, 1, 2]


@pytest.mark.parametrize("limit", (0, -1, True, 1.5))
def test_batch_rejects_invalid_file_size_limit(limit):
    with pytest.raises(BatchSelectionError, match="file-size limit"):
        analyze_spectrum_files(
            ["one.csv"],
            analysis_settings(),
            max_file_size_bytes=limit,
        )


def test_batch_rejects_oversized_file_without_calling_processor(tmp_path):
    source = write_spectrum(tmp_path / "large.csv", "intensity\n0.5\n2.0\n")
    processor = Mock(return_value=valid_result())

    summary = analyze_spectrum_files(
        [source],
        analysis_settings(),
        processor=processor,
        max_file_size_bytes=4,
    )

    assert summary.items[0].status == BATCH_STATUS_FAILED
    assert summary.items[0].error_message == "Unsupported or malformed spectrum data."
    processor.assert_not_called()


def test_batch_peak_snapshot_removes_non_finite_values(tmp_path):
    source = write_spectrum(tmp_path / "finite-export.csv")
    result = valid_result()
    result["peaks"][0].frequency = float("nan")
    result["peaks"][0].area = float("inf")

    summary = analyze_spectrum_files(
        [source],
        analysis_settings(),
        processor=Mock(return_value=result),
    )

    record = summary.items[0].peak_records[0]
    assert record.frequency is None
    assert record.area is None
    assert record.position == 1.0


def test_batch_omits_peak_details_instead_of_truncating_them(
    tmp_path,
    monkeypatch,
):
    source = write_spectrum(tmp_path / "many-peaks.csv")
    result = valid_result()
    result["peaks"] = result["peaks"] * 2
    monkeypatch.setattr(batch_module, "MAX_BATCH_PEAK_RECORDS_PER_FILE", 1)

    summary = analyze_spectrum_files(
        [source],
        analysis_settings(),
        processor=Mock(return_value=result),
    )

    item = summary.items[0]
    assert item.status == BATCH_STATUS_SUCCESS
    assert item.peak_count == 2
    assert item.peak_records == ()
    assert item.peak_details_available is False
    assert "omitted" in item.peak_details_message


def test_batch_metadata_whitelists_filter_parameters_and_redacts_paths(tmp_path):
    source = write_spectrum(tmp_path / "metadata.csv")
    settings = analysis_settings()
    result = valid_result()
    result["baseline_method"] = "/Users/example/private/baseline"

    summary = analyze_spectrum_files(
        [source],
        settings,
        processor=Mock(return_value=result),
    )

    metadata = dict(summary.items[0].analysis_metadata)
    assert batch_module._safe_filter_parameters(
        {
            "window_size": 5,
            "secret_path": "/Users/example/private",
        }
    ) == '{"window_size":5}'
    assert batch_module._safe_filter_parameters(
        {"window_size": "/Users/example/private"}
    ) == "{}"
    assert metadata["baseline"] == "[redacted]"
    assert "/Users/example" not in repr(summary)
