"""Portable import/export helpers for the reference library.

The exported document intentionally stores only scientific reference data.
Runtime state such as database paths, source file paths, UI filters, and recent
files must stay outside this boundary.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence

from python_analyzer.analysis.models import ReferencePeak


EXPORT_FORMAT = "chromatsvet.reference_library"
EXPORT_SCHEMA_VERSION = 1
REFERENCE_RECORD_SCHEMA_VERSION = 2

MAX_REFERENCE_RECORDS = 2_000
MAX_REFERENCE_NAME_LENGTH = 200
MAX_REFERENCE_FORMULA_LENGTH = 200
MAX_SPECTRUM_POINTS = 200_000
MAX_REFERENCE_PEAKS = 20_000
MAX_JSON_CELL_LENGTH = 10_000_000

DEFAULT_DATA_TYPE = "generic"
ALLOWED_DATA_TYPE_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
ALLOWED_DATA_TYPES = {
    "generic",
    "ir",
    "raman",
    "ms",
    "uv_vis",
    "fluorescence",
}

DuplicatePolicy = Literal["skip", "merge", "replace"]
DUPLICATE_POLICIES: tuple[DuplicatePolicy, ...] = ("skip", "merge", "replace")

CSV_HEADERS = [
    "format",
    "export_schema_version",
    "name",
    "formula",
    "data_type",
    "record_schema_version",
    "spectrum_json",
    "peaks_json",
]

_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")


class ReferenceLibraryFormatError(ValueError):
    """Raised when an imported reference-library document is malformed."""


@dataclass(frozen=True)
class ReferenceLibraryRecord:
    """One portable reference-library record."""

    name: str
    formula: str = ""
    data_type: str = DEFAULT_DATA_TYPE
    schema_version: int = REFERENCE_RECORD_SCHEMA_VERSION
    spectrum: tuple[float, ...] = field(default_factory=tuple)
    peaks: tuple[ReferencePeak, ...] = field(default_factory=tuple)

    @property
    def peak_count(self) -> int:
        return len(self.peaks)

    @property
    def spectrum_points(self) -> int:
        return len(self.spectrum)


@dataclass(frozen=True)
class ReferenceImportPreviewRow:
    """One row in an import preview."""

    name: str
    data_type: str
    spectrum_points: int
    peak_count: int
    status: Literal["new", "duplicate"]


@dataclass(frozen=True)
class ReferenceImportPreview:
    """Import preview computed before mutating the local database."""

    rows: tuple[ReferenceImportPreviewRow, ...]
    new_count: int
    duplicate_count: int

    @property
    def total_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class ReferenceImportResult:
    """Mutation summary after importing reference records."""

    added: int = 0
    merged: int = 0
    replaced: int = 0
    skipped: int = 0
    failed: int = 0

    @property
    def changed(self) -> int:
        return self.added + self.merged + self.replaced


def normalize_duplicate_policy(policy: object) -> DuplicatePolicy:
    value = str(policy or "skip").strip().lower()
    if value not in DUPLICATE_POLICIES:
        raise ValueError("duplicate policy must be one of: skip, merge, replace")
    return value  # type: ignore[return-value]


def canonical_reference_name(name: object) -> str:
    """Return the comparison key used for duplicate reference names."""
    return " ".join(str(name or "").strip().casefold().split())


def build_import_preview(
    records: Sequence[ReferenceLibraryRecord],
    existing_names: Iterable[object],
) -> ReferenceImportPreview:
    existing_keys = {canonical_reference_name(name) for name in existing_names}
    rows: list[ReferenceImportPreviewRow] = []
    new_count = 0
    duplicate_count = 0

    seen_import_keys: set[str] = set()
    for record in records:
        key = canonical_reference_name(record.name)
        is_duplicate = key in existing_keys or key in seen_import_keys
        status: Literal["new", "duplicate"] = "duplicate" if is_duplicate else "new"
        if is_duplicate:
            duplicate_count += 1
        else:
            new_count += 1
        seen_import_keys.add(key)
        rows.append(
            ReferenceImportPreviewRow(
                name=record.name,
                data_type=record.data_type,
                spectrum_points=record.spectrum_points,
                peak_count=record.peak_count,
                status=status,
            )
        )

    return ReferenceImportPreview(
        rows=tuple(rows),
        new_count=new_count,
        duplicate_count=duplicate_count,
    )


def merge_reference_records(
    existing: ReferenceLibraryRecord,
    incoming: ReferenceLibraryRecord,
) -> ReferenceLibraryRecord:
    """Merge duplicate references without inventing new scientific values."""
    merged_peaks = incoming.peaks or existing.peaks
    merged_spectrum = incoming.spectrum or existing.spectrum
    merged_schema_version = (
        REFERENCE_RECORD_SCHEMA_VERSION if merged_peaks else max(existing.schema_version, 1)
    )
    return ReferenceLibraryRecord(
        name=existing.name,
        formula=incoming.formula or existing.formula,
        data_type=(
            incoming.data_type
            if incoming.data_type != DEFAULT_DATA_TYPE
            else existing.data_type
        ),
        schema_version=merged_schema_version,
        spectrum=merged_spectrum,
        peaks=merged_peaks,
    )


def write_reference_json(
    output_path: str | Path,
    records: Sequence[ReferenceLibraryRecord],
) -> None:
    payload = {
        "format": EXPORT_FORMAT,
        "schema_version": EXPORT_SCHEMA_VERSION,
        "records": [record_to_payload(record) for record in _bounded_records(records)],
    }
    Path(output_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def read_reference_json(input_path: str | Path) -> list[ReferenceLibraryRecord]:
    try:
        payload = json.loads(Path(input_path).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ReferenceLibraryFormatError("reference JSON is malformed") from exc

    if not isinstance(payload, dict):
        raise ReferenceLibraryFormatError("reference JSON must contain an object")
    if payload.get("format") != EXPORT_FORMAT:
        raise ReferenceLibraryFormatError("unsupported reference-library format")
    if _safe_int(payload.get("schema_version")) != EXPORT_SCHEMA_VERSION:
        raise ReferenceLibraryFormatError("unsupported reference-library schema version")

    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise ReferenceLibraryFormatError("reference JSON must contain a records list")
    _validate_record_count(len(raw_records))
    return [
        record_from_payload(raw_record, row_label=f"records[{index}]")
        for index, raw_record in enumerate(raw_records)
    ]


def write_reference_csv(
    output_path: str | Path,
    records: Sequence[ReferenceLibraryRecord],
) -> None:
    with Path(output_path).open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for record in _bounded_records(records):
            payload = record_to_payload(record)
            writer.writerow(
                {
                    "format": EXPORT_FORMAT,
                    "export_schema_version": EXPORT_SCHEMA_VERSION,
                    "name": escape_csv_text(payload["name"]),
                    "formula": escape_csv_text(payload["formula"]),
                    "data_type": payload["data_type"],
                    "record_schema_version": payload["schema_version"],
                    "spectrum_json": json.dumps(
                        payload["spectrum"],
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                    "peaks_json": json.dumps(
                        payload["peaks"],
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                }
            )


def read_reference_csv(input_path: str | Path) -> list[ReferenceLibraryRecord]:
    with Path(input_path).open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ReferenceLibraryFormatError("reference CSV is empty")
        missing = [header for header in CSV_HEADERS if header not in reader.fieldnames]
        if missing:
            raise ReferenceLibraryFormatError("reference CSV is missing required columns")

        records = []
        for row_index, row in enumerate(reader, start=2):
            if row.get("format") != EXPORT_FORMAT:
                raise ReferenceLibraryFormatError(
                    f"unsupported reference-library format at CSV row {row_index}"
                )
            if _safe_int(row.get("export_schema_version")) != EXPORT_SCHEMA_VERSION:
                raise ReferenceLibraryFormatError(
                    f"unsupported reference-library schema version at CSV row {row_index}"
                )
            records.append(_record_from_csv_row(row, row_index))

    _validate_record_count(len(records))
    return records


def record_to_payload(record: ReferenceLibraryRecord) -> dict[str, Any]:
    clean_record = coerce_reference_record(record)
    return {
        "name": clean_record.name,
        "formula": clean_record.formula,
        "data_type": clean_record.data_type,
        "schema_version": clean_record.schema_version,
        "spectrum": list(clean_record.spectrum),
        "peaks": [peak_to_payload(peak) for peak in clean_record.peaks],
    }


def record_from_payload(
    payload: object,
    *,
    row_label: str = "record",
) -> ReferenceLibraryRecord:
    if not isinstance(payload, dict):
        raise ReferenceLibraryFormatError(f"{row_label} must be an object")

    return coerce_reference_record(
        ReferenceLibraryRecord(
            name=_clean_text(
                payload.get("name"),
                max_length=MAX_REFERENCE_NAME_LENGTH,
                field_name=f"{row_label}.name",
            ),
            formula=_clean_text(
                payload.get("formula", ""),
                max_length=MAX_REFERENCE_FORMULA_LENGTH,
                field_name=f"{row_label}.formula",
                required=False,
            ),
            data_type=normalize_data_type(payload.get("data_type")),
            schema_version=max(1, _safe_int(payload.get("schema_version"), default=1)),
            spectrum=_coerce_float_sequence(
                payload.get("spectrum", []),
                max_items=MAX_SPECTRUM_POINTS,
                field_name=f"{row_label}.spectrum",
                non_negative=False,
            ),
            peaks=_coerce_peaks(payload.get("peaks", []), row_label=row_label),
        )
    )


def coerce_reference_record(record: ReferenceLibraryRecord) -> ReferenceLibraryRecord:
    name = _clean_text(
        record.name,
        max_length=MAX_REFERENCE_NAME_LENGTH,
        field_name="record.name",
    )
    formula = _clean_text(
        record.formula,
        max_length=MAX_REFERENCE_FORMULA_LENGTH,
        field_name="record.formula",
        required=False,
    )
    spectrum = _coerce_float_sequence(
        record.spectrum,
        max_items=MAX_SPECTRUM_POINTS,
        field_name="record.spectrum",
        non_negative=False,
    )
    peaks = _coerce_peaks(record.peaks, row_label="record")
    schema_version = max(1, int(record.schema_version or 1))
    if peaks:
        schema_version = max(schema_version, REFERENCE_RECORD_SCHEMA_VERSION)
    return ReferenceLibraryRecord(
        name=name,
        formula=formula,
        data_type=normalize_data_type(record.data_type),
        schema_version=schema_version,
        spectrum=spectrum,
        peaks=peaks,
    )


def peak_to_payload(peak: ReferencePeak) -> dict[str, float]:
    normalized = _coerce_peak(peak, field_name="peak")
    return {
        "frequency": normalized.frequency,
        "intensity": normalized.intensity,
        "width": normalized.width,
        "width_hz": normalized.width_hz,
        "area": normalized.area,
        "snr": normalized.snr,
    }


def escape_csv_text(value: object) -> str:
    text = str(value or "")
    if text.startswith("'") and len(text) > 1 and text[1] in _CSV_FORMULA_PREFIXES:
        return text
    if text.startswith(_CSV_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def unescape_csv_text(value: object) -> str:
    text = str(value or "")
    if len(text) > 1 and text[0] == "'" and text[1] in _CSV_FORMULA_PREFIXES:
        return text[1:]
    return text


def normalize_data_type(data_type: object) -> str:
    value = str(data_type or DEFAULT_DATA_TYPE).strip().lower()
    normalized = "".join(char for char in value if char in ALLOWED_DATA_TYPE_CHARS)
    normalized = normalized[:32] or DEFAULT_DATA_TYPE
    return normalized if normalized in ALLOWED_DATA_TYPES else DEFAULT_DATA_TYPE


def _record_from_csv_row(row: dict[str, str], row_index: int) -> ReferenceLibraryRecord:
    spectrum_json = row.get("spectrum_json") or "[]"
    peaks_json = row.get("peaks_json") or "[]"
    if len(spectrum_json) > MAX_JSON_CELL_LENGTH or len(peaks_json) > MAX_JSON_CELL_LENGTH:
        raise ReferenceLibraryFormatError(f"CSV row {row_index} contains an oversized JSON cell")

    try:
        spectrum = json.loads(spectrum_json or "[]")
        peaks = json.loads(peaks_json or "[]")
    except json.JSONDecodeError as exc:
        raise ReferenceLibraryFormatError(f"CSV row {row_index} contains malformed JSON") from exc

    return record_from_payload(
        {
            "name": unescape_csv_text(row.get("name", "")),
            "formula": unescape_csv_text(row.get("formula", "")),
            "data_type": row.get("data_type", DEFAULT_DATA_TYPE),
            "schema_version": row.get("record_schema_version", 1),
            "spectrum": spectrum,
            "peaks": peaks,
        },
        row_label=f"CSV row {row_index}",
    )


def _bounded_records(records: Sequence[ReferenceLibraryRecord]) -> list[ReferenceLibraryRecord]:
    _validate_record_count(len(records))
    return [coerce_reference_record(record) for record in records]


def _validate_record_count(count: int) -> None:
    if count > MAX_REFERENCE_RECORDS:
        raise ReferenceLibraryFormatError("reference library import is too large")


def _clean_text(
    value: object,
    *,
    max_length: int,
    field_name: str,
    required: bool = True,
) -> str:
    text = str(value or "").strip()
    text = "".join(char for char in text if char == "\t" or ord(char) >= 32)
    if required and not text:
        raise ReferenceLibraryFormatError(f"{field_name} cannot be empty")
    if len(text) > max_length:
        raise ReferenceLibraryFormatError(f"{field_name} is too long")
    return text


def _coerce_float_sequence(
    values: object,
    *,
    max_items: int,
    field_name: str,
    non_negative: bool,
) -> tuple[float, ...]:
    if values in (None, ""):
        return tuple()
    if not isinstance(values, (list, tuple)):
        raise ReferenceLibraryFormatError(f"{field_name} must be a list")
    if len(values) > max_items:
        raise ReferenceLibraryFormatError(f"{field_name} is too large")

    result = []
    for index, value in enumerate(values):
        number = _finite_float(value)
        if number is None:
            raise ReferenceLibraryFormatError(f"{field_name}[{index}] must be finite")
        if non_negative:
            number = max(0.0, number)
        result.append(number)
    return tuple(result)


def _coerce_peaks(values: object, *, row_label: str) -> tuple[ReferencePeak, ...]:
    if values in (None, ""):
        return tuple()
    if not isinstance(values, (list, tuple)):
        raise ReferenceLibraryFormatError(f"{row_label}.peaks must be a list")
    if len(values) > MAX_REFERENCE_PEAKS:
        raise ReferenceLibraryFormatError(f"{row_label}.peaks is too large")
    return tuple(
        _coerce_peak(value, field_name=f"{row_label}.peaks[{index}]")
        for index, value in enumerate(values)
    )


def _coerce_peak(value: object, *, field_name: str) -> ReferencePeak:
    if isinstance(value, ReferencePeak):
        raw = {
            "frequency": value.frequency,
            "intensity": value.intensity,
            "width": value.width,
            "width_hz": value.width_hz,
            "area": value.area,
            "snr": value.snr,
        }
    elif isinstance(value, dict):
        raw = value
    else:
        raise ReferenceLibraryFormatError(f"{field_name} must be an object")

    frequency = _finite_float(raw.get("frequency"))
    intensity = _finite_float(raw.get("intensity"))
    if frequency is None or intensity is None:
        raise ReferenceLibraryFormatError(f"{field_name} requires finite frequency and intensity")

    return ReferencePeak(
        frequency=frequency,
        intensity=max(0.0, intensity),
        width=max(0.0, _finite_float(raw.get("width"), default=0.0) or 0.0),
        width_hz=max(0.0, _finite_float(raw.get("width_hz"), default=0.0) or 0.0),
        area=max(0.0, _finite_float(raw.get("area"), default=0.0) or 0.0),
        snr=max(0.0, _finite_float(raw.get("snr"), default=0.0) or 0.0),
    )


def _finite_float(value: object, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
