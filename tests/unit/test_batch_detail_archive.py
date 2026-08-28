from __future__ import annotations

import csv
from io import StringIO
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from python_analyzer.analysis.batch import (
    BATCH_STATUS_FAILED,
    BATCH_STATUS_SUCCESS,
    BatchAnalysisItem,
    BatchAnalysisSummary,
    BatchPeakRecord,
)
from python_analyzer.exporters.batch_detail_archive import (
    BatchDetailArchiveError,
    write_batch_detail_archive,
)


def _csv_rows(archive: ZipFile, entry_name: str) -> list[list[str]]:
    text = archive.read(entry_name).decode("utf-8-sig")
    return list(csv.reader(StringIO(text)))


def _peak_record() -> BatchPeakRecord:
    return BatchPeakRecord(
        frequency=25.0,
        position=2.0,
        intensity=4.5,
        prominence=3.0,
        baseline_level=1.5,
        left_base=1.0,
        right_base=1.5,
        width=2.0,
        width_hz=0.5,
        area=9.58,
        noise=0.1,
        snr=30.0,
        review_status="accepted",
        review_reason="accepted",
    )


def test_detail_archive_is_path_free_collision_safe_and_formula_safe(tmp_path):
    private_path = "/Users/example/private/=SUM(A1).csv"
    metadata = (
        ("sample_rate_hz", "100"),
        ("filter_type", "=UNSAFE()"),
    )
    summary = BatchAnalysisSummary(
        items=(
            BatchAnalysisItem(
                source_name=private_path,
                status=BATCH_STATUS_SUCCESS,
                point_count=3,
                peak_count=1,
                peak_records=(_peak_record(),),
                peak_details_available=True,
                analysis_metadata=metadata,
            ),
            BatchAnalysisItem(
                source_name="=SUM(A1).csv",
                status=BATCH_STATUS_SUCCESS,
                point_count=3,
                peak_count=1,
                peak_records=(_peak_record(),),
                peak_details_available=True,
                analysis_metadata=metadata,
            ),
            BatchAnalysisItem(
                source_name="failed.csv",
                status=BATCH_STATUS_FAILED,
                error_message="Unsupported or malformed spectrum data.",
            ),
        ),
        requested_count=3,
    )
    output_path = tmp_path / "details.zip"

    write_batch_detail_archive(output_path, summary)

    with ZipFile(output_path) as archive:
        names = archive.namelist()
        peak_names = [name for name in names if name.startswith("peaks/")]
        assert names[:2] == ["archive-info.csv", "manifest.csv"]
        assert len(peak_names) == 2
        assert len(set(peak_names)) == 2
        manifest_rows = _csv_rows(archive, "manifest.csv")
        first_peak_rows = _csv_rows(archive, peak_names[0])
        all_text = "\n".join(
            archive.read(name).decode("utf-8-sig") for name in names
        )

    assert manifest_rows[1][0] == "'=SUM(A1).csv"
    assert manifest_rows[1][6] == "available"
    assert manifest_rows[3][1] == BATCH_STATUS_FAILED
    assert first_peak_rows[1][0] == "'=SUM(A1).csv"
    filter_column = first_peak_rows[0].index("filter_type")
    assert first_peak_rows[1][filter_column] == "'=UNSAFE()"
    assert private_path not in all_text
    assert "/Users/example" not in all_text


def test_detail_archive_marks_omitted_peak_snapshot_without_partial_csv(tmp_path):
    summary = BatchAnalysisSummary(
        items=(
            BatchAnalysisItem(
                source_name="large.csv",
                status=BATCH_STATUS_SUCCESS,
                point_count=100,
                peak_count=50,
                peak_details_available=False,
                peak_details_message="Peak details were omitted by the safety limit.",
            ),
        ),
        requested_count=1,
    )
    output_path = tmp_path / "details.zip"

    write_batch_detail_archive(output_path, summary)

    with ZipFile(output_path) as archive:
        manifest_rows = _csv_rows(archive, "manifest.csv")
        assert not any(name.startswith("peaks/") for name in archive.namelist())
    assert manifest_rows[1][6] == "omitted"
    assert manifest_rows[1][7] == ""


def test_detail_archive_rejects_incomplete_snapshot(tmp_path):
    summary = BatchAnalysisSummary(
        items=(
            BatchAnalysisItem(
                source_name="incomplete.csv",
                status=BATCH_STATUS_SUCCESS,
                peak_count=2,
                peak_records=(_peak_record(),),
                peak_details_available=True,
            ),
        ),
        requested_count=1,
    )

    with pytest.raises(BatchDetailArchiveError, match="incomplete"):
        write_batch_detail_archive(tmp_path / "details.zip", summary)


@pytest.mark.parametrize(
    "item",
    (
        BatchAnalysisItem(
            source_name="negative.csv",
            status=BATCH_STATUS_SUCCESS,
            point_count=-1,
        ),
        BatchAnalysisItem(
            source_name="unknown.csv",
            status="unknown",
        ),
    ),
)
def test_detail_archive_rejects_malformed_summary_items(tmp_path, item):
    summary = BatchAnalysisSummary(items=(item,), requested_count=1)

    with pytest.raises(BatchDetailArchiveError):
        write_batch_detail_archive(tmp_path / "details.zip", summary)


def test_detail_archive_failure_preserves_existing_destination(tmp_path):
    output_path = tmp_path / "details.zip"
    output_path.write_bytes(b"existing archive")
    summary = BatchAnalysisSummary(items=(), requested_count=0)

    with (
        patch(
            "python_analyzer.exporters.batch_detail_archive._write_archive",
            side_effect=OSError("simulated write failure"),
        ),
        pytest.raises(OSError, match="simulated"),
    ):
        write_batch_detail_archive(output_path, summary)

    assert output_path.read_bytes() == b"existing archive"
    assert list(tmp_path.iterdir()) == [output_path]


def test_detail_archive_removes_non_finite_values_from_manual_snapshot(tmp_path):
    record = _peak_record()
    unsafe_record = BatchPeakRecord(
        **{
            **record.__dict__,
            "frequency": float("nan"),
            "area": float("inf"),
        }
    )
    summary = BatchAnalysisSummary(
        items=(
            BatchAnalysisItem(
                source_name="finite.csv",
                status=BATCH_STATUS_SUCCESS,
                peak_count=1,
                peak_records=(unsafe_record,),
                peak_details_available=True,
            ),
        ),
        requested_count=1,
    )
    output_path = tmp_path / "details.zip"

    write_batch_detail_archive(output_path, summary)

    with ZipFile(output_path) as archive:
        peak_name = next(
            name for name in archive.namelist() if name.startswith("peaks/")
        )
        rows = _csv_rows(archive, peak_name)
    assert rows[1][rows[0].index("frequency_hz")] == ""
    assert rows[1][rows[0].index("area")] == ""
