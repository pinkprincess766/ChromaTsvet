"""Portable ZIP export for per-file batch peak results."""

from __future__ import annotations

import csv
from io import StringIO
import math
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from python_analyzer.analysis.batch import (
    BATCH_STATUS_FAILED,
    BATCH_STATUS_SUCCESS,
    MAX_BATCH_FILES,
    MAX_BATCH_PEAK_RECORDS_PER_FILE,
    MAX_BATCH_PEAK_RECORDS_TOTAL,
    BatchAnalysisItem,
    BatchAnalysisSummary,
    BatchPeakRecord,
)

from .spreadsheet_safety import safe_spreadsheet_cell


BATCH_DETAIL_ARCHIVE_SCHEMA_VERSION = "1"
MAX_ARCHIVE_SOURCE_NAME_CHARACTERS = 255
MAX_ARCHIVE_ENTRY_STEM_CHARACTERS = 72
MAX_ARCHIVE_PUBLIC_TEXT_CHARACTERS = 255

ARCHIVE_INFO_HEADERS = ("field", "value")
MANIFEST_HEADERS = (
    "source_file",
    "status",
    "point_count",
    "peak_count",
    "warning_count",
    "skipped_row_count",
    "peak_details",
    "peak_file",
    "details",
)
ANALYSIS_METADATA_HEADERS = (
    "sample_rate_hz",
    "filter_type",
    "filter_params",
    "fft_window",
    "baseline",
    "normalization",
    "spectrum_smoothing",
    "spectrum_smoothing_method",
    "spectrum_smoothing_window",
    "peak_threshold",
    "peak_prominence",
    "peak_distance",
    "peak_min_snr",
    "data_type",
    "peak_frequency_tolerance_hz",
)
PEAK_HEADERS = (
    "source_file",
    *ANALYSIS_METADATA_HEADERS,
    "frequency_hz",
    "position_bin",
    "intensity",
    "prominence",
    "baseline_level",
    "left_base",
    "right_base",
    "width_bins",
    "width_hz",
    "area",
    "noise",
    "snr",
    "is_global_max",
    "review_status",
    "review_reason",
)


class BatchDetailArchiveError(ValueError):
    """Raised when a batch snapshot cannot be exported without ambiguity."""


def write_batch_detail_archive(
    output_path: str | Path,
    summary: BatchAnalysisSummary,
) -> None:
    """Atomically write a path-free ZIP containing manifest and peak CSV files."""

    destination = Path(output_path).expanduser()
    if destination.exists() and destination.is_dir():
        raise IsADirectoryError("The batch archive destination is a directory.")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        _write_archive(temporary_path, summary)
        os.replace(temporary_path, destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _write_archive(output_path: Path, summary: BatchAnalysisSummary) -> None:
    _validate_summary(summary)
    manifest_rows: list[tuple[Any, ...]] = []
    peak_entries: list[tuple[str, str]] = []

    for index, item in enumerate(summary.items, start=1):
        source_name = _public_source_name(item.source_name)
        peak_entry_name = ""
        details_status = "not_applicable"
        details = item.error_message if item.status == BATCH_STATUS_FAILED else ""

        if item.status == BATCH_STATUS_SUCCESS:
            if item.peak_details_available:
                _validate_complete_peak_snapshot(item)
                details_status = "available"
                peak_entry_name = _peak_entry_name(index, source_name)
                peak_entries.append(
                    (peak_entry_name, _peak_csv_text(item, source_name))
                )
            else:
                details_status = "omitted"
                details = item.peak_details_message or "Peak details are unavailable."
        elif item.status != BATCH_STATUS_FAILED:
            raise BatchDetailArchiveError("Batch item has an unknown status.")

        manifest_rows.append(
            (
                source_name,
                item.status,
                item.point_count,
                item.peak_count,
                item.warning_count,
                item.skipped_row_count,
                details_status,
                peak_entry_name,
                _safe_public_text(details),
            )
        )

    archive_info_rows = (
        ("schema_version", BATCH_DETAIL_ARCHIVE_SCHEMA_VERSION),
        ("requested_files", summary.requested_count),
        ("processed_files", len(summary.items)),
        ("successful_files", summary.successful_count),
        ("failed_files", summary.failed_count),
        ("cancelled", "yes" if summary.cancelled else "no"),
    )

    with ZipFile(output_path, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        _write_csv_entry(
            archive,
            "archive-info.csv",
            ARCHIVE_INFO_HEADERS,
            archive_info_rows,
        )
        _write_csv_entry(archive, "manifest.csv", MANIFEST_HEADERS, manifest_rows)
        for entry_name, csv_text in peak_entries:
            _write_text_entry(archive, entry_name, csv_text)


def _validate_complete_peak_snapshot(item: BatchAnalysisItem) -> None:
    if item.peak_count < 0:
        raise BatchDetailArchiveError("Batch item has a negative peak count.")
    if len(item.peak_records) != item.peak_count:
        raise BatchDetailArchiveError(
            "Batch peak snapshot is incomplete and cannot be exported as complete."
        )


def _validate_summary(summary: BatchAnalysisSummary) -> None:
    if not _is_non_negative_integer(summary.requested_count):
        raise BatchDetailArchiveError("Batch requested count is invalid.")
    if len(summary.items) > summary.requested_count:
        raise BatchDetailArchiveError("Batch contains more items than requested files.")
    if len(summary.items) > MAX_BATCH_FILES:
        raise BatchDetailArchiveError("Batch exceeds the supported file limit.")

    total_peak_records = 0
    for item in summary.items:
        for value in (
            item.point_count,
            item.peak_count,
            item.warning_count,
            item.skipped_row_count,
        ):
            if not _is_non_negative_integer(value):
                raise BatchDetailArchiveError("Batch item contains an invalid count.")
        if len(item.peak_records) > MAX_BATCH_PEAK_RECORDS_PER_FILE:
            raise BatchDetailArchiveError("Batch item exceeds the peak detail limit.")
        total_peak_records += len(item.peak_records)
    if total_peak_records > MAX_BATCH_PEAK_RECORDS_TOTAL:
        raise BatchDetailArchiveError("Batch exceeds the total peak detail limit.")


def _is_non_negative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _peak_csv_text(item: BatchAnalysisItem, source_name: str) -> str:
    metadata = _metadata_mapping(item.analysis_metadata)
    rows = (
        (
            source_name,
            *(metadata.get(header, "") for header in ANALYSIS_METADATA_HEADERS),
            _finite_cell(record.frequency),
            _finite_cell(record.position),
            _finite_cell(record.intensity),
            _finite_cell(record.prominence),
            _finite_cell(record.baseline_level),
            _finite_cell(record.left_base),
            _finite_cell(record.right_base),
            _finite_cell(record.width),
            _finite_cell(record.width_hz),
            _finite_cell(record.area),
            _finite_cell(record.noise),
            _finite_cell(record.snr),
            "yes" if record.is_global_max else "no",
            _safe_public_text(record.review_status),
            _safe_public_text(record.review_reason),
        )
        for record in item.peak_records
    )
    return _csv_text(PEAK_HEADERS, rows)


def _metadata_mapping(rows: Iterable[tuple[str, str]]) -> dict[str, str]:
    allowed_headers = set(ANALYSIS_METADATA_HEADERS)
    metadata: dict[str, str] = {}
    for key, value in rows:
        normalized_key = str(key)
        if normalized_key not in allowed_headers or normalized_key in metadata:
            continue
        metadata[normalized_key] = _safe_public_text(value)
    return metadata


def _write_csv_entry(
    archive: ZipFile,
    entry_name: str,
    headers: tuple[str, ...],
    rows: Iterable[tuple[Any, ...]],
) -> None:
    _write_text_entry(archive, entry_name, _csv_text(headers, rows))


def _csv_text(
    headers: tuple[str, ...],
    rows: Iterable[tuple[Any, ...]],
) -> str:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(tuple(safe_spreadsheet_cell(value) for value in row))
    return output.getvalue()


def _write_text_entry(archive: ZipFile, entry_name: str, text: str) -> None:
    # Fixed metadata makes identical scientific snapshots byte-for-byte stable.
    entry = ZipInfo(entry_name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.compress_type = ZIP_DEFLATED
    entry.external_attr = 0o600 << 16
    archive.writestr(entry, text.encode("utf-8-sig"))


def _peak_entry_name(index: int, source_name: str) -> str:
    normalized_stem = unicodedata.normalize("NFKC", Path(source_name).stem)
    portable_stem = re.sub(r"[^\w.-]+", "-", normalized_stem, flags=re.UNICODE)
    portable_stem = portable_stem.strip(" .-_")[:MAX_ARCHIVE_ENTRY_STEM_CHARACTERS]
    if not portable_stem:
        portable_stem = "spectrum"
    return f"peaks/{index:03d}-{portable_stem}-peaks.csv"


def _public_source_name(value: Any) -> str:
    text = str(value or "").replace("\\", "/").rsplit("/", 1)[-1]
    text = "".join(character if character.isprintable() else "?" for character in text)
    return text[:MAX_ARCHIVE_SOURCE_NAME_CHARACTERS] or "<unnamed>"


def _safe_public_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if "/" in text or "\\" in text:
        return "[redacted]"
    return text[:MAX_ARCHIVE_PUBLIC_TEXT_CHARACTERS]


def _finite_cell(value: Any) -> float | str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return ""
    return numeric_value if math.isfinite(numeric_value) else ""
