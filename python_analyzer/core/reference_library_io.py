"""Portable import/export helpers for the reference library.

The exported document intentionally stores only scientific reference data.
Runtime state such as database paths, source file paths, UI filters, and recent
files must stay outside this boundary.
"""

from __future__ import annotations

import csv
from datetime import date
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence

from python_analyzer.analysis.models import ReferencePeak


EXPORT_FORMAT = "chromatsvet.reference_library"
EXPORT_SCHEMA_VERSION = 3
SUPPORTED_EXPORT_SCHEMA_VERSIONS = frozenset(range(1, EXPORT_SCHEMA_VERSION + 1))
REFERENCE_RECORD_SCHEMA_VERSION = 2
REFERENCE_METADATA_SCHEMA_VERSION = 3
REFERENCE_ACQUISITION_SCHEMA_VERSION = 4

MAX_REFERENCE_RECORDS = 2_000
MAX_REFERENCE_NAME_LENGTH = 200
MAX_REFERENCE_FORMULA_LENGTH = 200
MAX_REFERENCE_DESCRIPTION_LENGTH = 4_000
MAX_REFERENCE_CAS_LENGTH = 12
MAX_REFERENCE_MANUFACTURER_LENGTH = 200
MAX_REFERENCE_SAMPLE_ID_LENGTH = 160
MAX_REFERENCE_INSTRUMENT_LENGTH = 200
MAX_REFERENCE_OPERATOR_LENGTH = 200
MAX_REFERENCE_CATEGORIES = 32
MAX_REFERENCE_CATEGORY_LENGTH = 80
MAX_SPECTRUM_POINTS = 200_000
MAX_REFERENCE_PEAKS = 20_000
MAX_TOTAL_SPECTRUM_POINTS = 2_000_000
MAX_TOTAL_REFERENCE_PEAKS = 200_000
MAX_JSON_CELL_LENGTH = 10_000_000
MAX_REFERENCE_FILE_BYTES = 64 * 1024 * 1024

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

BASE_CSV_HEADERS = [
    "format",
    "export_schema_version",
    "name",
    "formula",
    "data_type",
    "record_schema_version",
    "spectrum_json",
    "peaks_json",
]
METADATA_CSV_HEADERS = [
    "description",
    "cas_number",
    "manufacturer",
    "categories_json",
]
ACQUISITION_CSV_HEADERS = [
    "sample_id",
    "instrument",
    "operator_name",
    "measurement_date",
]
CSV_HEADERS = [*BASE_CSV_HEADERS, *METADATA_CSV_HEADERS, *ACQUISITION_CSV_HEADERS]

_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")
_CAS_NUMBER_PATTERN = re.compile(r"^(\d{2,7})-(\d{2})-(\d)$")
_CATEGORY_SEPARATOR_PATTERN = re.compile(r"[,;\n]+")


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
    description: str = ""
    cas_number: str = ""
    manufacturer: str = ""
    categories: tuple[str, ...] = field(default_factory=tuple)
    sample_id: str = ""
    instrument: str = ""
    operator_name: str = ""
    measurement_date: str = ""

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
    cas_number: str = ""
    categories: tuple[str, ...] = field(default_factory=tuple)


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
        clean_record = coerce_reference_record(record)
        key = canonical_reference_name(clean_record.name)
        is_duplicate = key in existing_keys or key in seen_import_keys
        status: Literal["new", "duplicate"] = "duplicate" if is_duplicate else "new"
        if is_duplicate:
            duplicate_count += 1
        else:
            new_count += 1
        seen_import_keys.add(key)
        rows.append(
            ReferenceImportPreviewRow(
                name=clean_record.name,
                cas_number=clean_record.cas_number,
                categories=clean_record.categories,
                data_type=clean_record.data_type,
                spectrum_points=clean_record.spectrum_points,
                peak_count=clean_record.peak_count,
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
    merged_categories = normalize_reference_categories(
        (*existing.categories, *incoming.categories),
        field_name="merged.categories",
    )
    merged_schema_version = max(existing.schema_version, incoming.schema_version, 1)
    if merged_peaks:
        merged_schema_version = max(
            merged_schema_version,
            REFERENCE_RECORD_SCHEMA_VERSION,
        )
    if (
        incoming.description
        or existing.description
        or incoming.cas_number
        or existing.cas_number
        or incoming.manufacturer
        or existing.manufacturer
        or merged_categories
    ):
        merged_schema_version = max(
            merged_schema_version,
            REFERENCE_METADATA_SCHEMA_VERSION,
        )
    if any(
        (
            incoming.sample_id,
            existing.sample_id,
            incoming.instrument,
            existing.instrument,
            incoming.operator_name,
            existing.operator_name,
            incoming.measurement_date,
            existing.measurement_date,
        )
    ):
        merged_schema_version = max(
            merged_schema_version,
            REFERENCE_ACQUISITION_SCHEMA_VERSION,
        )
    return ReferenceLibraryRecord(
        name=existing.name,
        formula=incoming.formula or existing.formula,
        description=incoming.description or existing.description,
        cas_number=incoming.cas_number or existing.cas_number,
        manufacturer=incoming.manufacturer or existing.manufacturer,
        categories=merged_categories,
        sample_id=incoming.sample_id or existing.sample_id,
        instrument=incoming.instrument or existing.instrument,
        operator_name=incoming.operator_name or existing.operator_name,
        measurement_date=incoming.measurement_date or existing.measurement_date,
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
        _validate_reference_file_size(input_path)
        payload = json.loads(Path(input_path).read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReferenceLibraryFormatError("reference JSON is malformed") from exc

    if not isinstance(payload, dict):
        raise ReferenceLibraryFormatError("reference JSON must contain an object")
    if payload.get("format") != EXPORT_FORMAT:
        raise ReferenceLibraryFormatError("unsupported reference-library format")
    export_schema_version = _parse_schema_version(
        payload.get("schema_version"),
        field_name="reference-library schema_version",
        max_supported=EXPORT_SCHEMA_VERSION,
    )
    if export_schema_version not in SUPPORTED_EXPORT_SCHEMA_VERSIONS:
        raise ReferenceLibraryFormatError("unsupported reference-library schema version")

    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise ReferenceLibraryFormatError("reference JSON must contain a records list")
    _validate_record_count(len(raw_records))
    records = [
        record_from_payload(raw_record, row_label=f"records[{index}]")
        for index, raw_record in enumerate(raw_records)
    ]
    _validate_aggregate_payload(records)
    return records


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
                    "description": escape_csv_text(payload["description"]),
                    "cas_number": escape_csv_text(payload["cas_number"]),
                    "manufacturer": escape_csv_text(payload["manufacturer"]),
                    "sample_id": escape_csv_text(payload["sample_id"]),
                    "instrument": escape_csv_text(payload["instrument"]),
                    "operator_name": escape_csv_text(payload["operator_name"]),
                    "measurement_date": payload["measurement_date"],
                    "categories_json": json.dumps(
                        payload["categories"],
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
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
    try:
        return _read_reference_csv_utf8(input_path)
    except UnicodeDecodeError as exc:
        raise ReferenceLibraryFormatError(
            "reference CSV must use UTF-8 encoding"
        ) from exc


def _read_reference_csv_utf8(input_path: str | Path) -> list[ReferenceLibraryRecord]:
    _validate_reference_file_size(input_path)
    with Path(input_path).open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ReferenceLibraryFormatError("reference CSV is empty")
        missing = [header for header in BASE_CSV_HEADERS if header not in reader.fieldnames]
        if missing:
            raise ReferenceLibraryFormatError("reference CSV is missing required columns")

        records = []
        for row_index, row in enumerate(reader, start=2):
            if None in row:
                raise ReferenceLibraryFormatError(
                    f"CSV row {row_index} contains unexpected columns"
                )
            if row.get("format") != EXPORT_FORMAT:
                raise ReferenceLibraryFormatError(
                    f"unsupported reference-library format at CSV row {row_index}"
                )
            export_schema_version = _parse_schema_version(
                row.get("export_schema_version"),
                field_name=f"CSV row {row_index}.export_schema_version",
                max_supported=EXPORT_SCHEMA_VERSION,
            )
            if export_schema_version not in SUPPORTED_EXPORT_SCHEMA_VERSIONS:
                raise ReferenceLibraryFormatError(
                    f"unsupported reference-library schema version at CSV row {row_index}"
                )
            if export_schema_version >= 2:
                missing_metadata = [
                    header for header in METADATA_CSV_HEADERS if header not in reader.fieldnames
                ]
                if missing_metadata:
                    raise ReferenceLibraryFormatError(
                        f"reference CSV row {row_index} is missing v2 metadata columns"
                    )
            if export_schema_version >= 3:
                missing_acquisition = [
                    header
                    for header in ACQUISITION_CSV_HEADERS
                    if header not in reader.fieldnames
                ]
                if missing_acquisition:
                    raise ReferenceLibraryFormatError(
                        f"reference CSV row {row_index} is missing v3 acquisition columns"
                    )
            records.append(_record_from_csv_row(row, row_index))

    _validate_record_count(len(records))
    _validate_aggregate_payload(records)
    return records


def record_to_payload(record: ReferenceLibraryRecord) -> dict[str, Any]:
    clean_record = coerce_reference_record(record)
    return {
        "name": clean_record.name,
        "formula": clean_record.formula,
        "description": clean_record.description,
        "cas_number": clean_record.cas_number,
        "manufacturer": clean_record.manufacturer,
        "categories": list(clean_record.categories),
        "sample_id": clean_record.sample_id,
        "instrument": clean_record.instrument,
        "operator_name": clean_record.operator_name,
        "measurement_date": clean_record.measurement_date,
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
            description=_clean_text(
                payload.get("description", ""),
                max_length=MAX_REFERENCE_DESCRIPTION_LENGTH,
                field_name=f"{row_label}.description",
                required=False,
            ),
            cas_number=normalize_cas_number(
                payload.get("cas_number", ""),
                field_name=f"{row_label}.cas_number",
            ),
            manufacturer=_clean_text(
                payload.get("manufacturer", ""),
                max_length=MAX_REFERENCE_MANUFACTURER_LENGTH,
                field_name=f"{row_label}.manufacturer",
                required=False,
            ),
            sample_id=_clean_text(
                payload.get("sample_id", ""),
                max_length=MAX_REFERENCE_SAMPLE_ID_LENGTH,
                field_name=f"{row_label}.sample_id",
                required=False,
            ),
            instrument=_clean_text(
                payload.get("instrument", ""),
                max_length=MAX_REFERENCE_INSTRUMENT_LENGTH,
                field_name=f"{row_label}.instrument",
                required=False,
            ),
            operator_name=_clean_text(
                payload.get("operator_name", ""),
                max_length=MAX_REFERENCE_OPERATOR_LENGTH,
                field_name=f"{row_label}.operator_name",
                required=False,
            ),
            measurement_date=normalize_measurement_date(
                payload.get("measurement_date", ""),
                field_name=f"{row_label}.measurement_date",
            ),
            categories=normalize_reference_categories(
                payload.get("categories", []),
                field_name=f"{row_label}.categories",
            ),
            data_type=normalize_data_type(payload.get("data_type")),
            schema_version=_parse_schema_version(
                payload.get("schema_version", 1),
                field_name=f"{row_label}.schema_version",
                max_supported=REFERENCE_ACQUISITION_SCHEMA_VERSION,
            ),
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
    description = _clean_text(
        record.description,
        max_length=MAX_REFERENCE_DESCRIPTION_LENGTH,
        field_name="record.description",
        required=False,
    )
    cas_number = normalize_cas_number(record.cas_number, field_name="record.cas_number")
    manufacturer = _clean_text(
        record.manufacturer,
        max_length=MAX_REFERENCE_MANUFACTURER_LENGTH,
        field_name="record.manufacturer",
        required=False,
    )
    sample_id = _clean_text(
        record.sample_id,
        max_length=MAX_REFERENCE_SAMPLE_ID_LENGTH,
        field_name="record.sample_id",
        required=False,
    )
    instrument = _clean_text(
        record.instrument,
        max_length=MAX_REFERENCE_INSTRUMENT_LENGTH,
        field_name="record.instrument",
        required=False,
    )
    operator_name = _clean_text(
        record.operator_name,
        max_length=MAX_REFERENCE_OPERATOR_LENGTH,
        field_name="record.operator_name",
        required=False,
    )
    measurement_date = normalize_measurement_date(
        record.measurement_date,
        field_name="record.measurement_date",
    )
    categories = normalize_reference_categories(
        record.categories,
        field_name="record.categories",
    )
    spectrum = _coerce_float_sequence(
        record.spectrum,
        max_items=MAX_SPECTRUM_POINTS,
        field_name="record.spectrum",
        non_negative=False,
    )
    peaks = _coerce_peaks(record.peaks, row_label="record")
    schema_version = _parse_schema_version(
        record.schema_version,
        field_name="record.schema_version",
        max_supported=REFERENCE_ACQUISITION_SCHEMA_VERSION,
    )
    if peaks:
        schema_version = max(schema_version, REFERENCE_RECORD_SCHEMA_VERSION)
    if description or cas_number or manufacturer or categories:
        schema_version = max(schema_version, REFERENCE_METADATA_SCHEMA_VERSION)
    if sample_id or instrument or operator_name or measurement_date:
        schema_version = max(schema_version, REFERENCE_ACQUISITION_SCHEMA_VERSION)
    return ReferenceLibraryRecord(
        name=name,
        formula=formula,
        description=description,
        cas_number=cas_number,
        manufacturer=manufacturer,
        categories=categories,
        sample_id=sample_id,
        instrument=instrument,
        operator_name=operator_name,
        measurement_date=measurement_date,
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


def normalize_cas_number(value: object, *, field_name: str = "cas_number") -> str:
    """Validate a CAS Registry Number, including its check digit."""

    text = _clean_text(
        value,
        max_length=MAX_REFERENCE_CAS_LENGTH,
        field_name=field_name,
        required=False,
    )
    if not text:
        return ""

    match = _CAS_NUMBER_PATTERN.fullmatch(text)
    if match is None:
        raise ReferenceLibraryFormatError(f"{field_name} is not a valid CAS number")

    body = "".join(match.groups()[:2])
    expected_check_digit = sum(
        int(digit) * multiplier
        for multiplier, digit in enumerate(reversed(body), start=1)
    ) % 10
    if expected_check_digit != int(match.group(3)):
        raise ReferenceLibraryFormatError(f"{field_name} has an invalid check digit")
    return text


def normalize_measurement_date(
    value: object,
    *,
    field_name: str = "measurement_date",
) -> str:
    """Return an ISO calendar date without inventing time-zone precision."""

    text = _clean_text(
        value,
        max_length=10,
        field_name=field_name,
        required=False,
    )
    if not text:
        return ""
    try:
        normalized = date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ReferenceLibraryFormatError(
            f"{field_name} must use YYYY-MM-DD"
        ) from exc
    if normalized != text:
        raise ReferenceLibraryFormatError(f"{field_name} must use YYYY-MM-DD")
    return normalized


def normalize_reference_categories(
    values: object,
    *,
    field_name: str = "categories",
) -> tuple[str, ...]:
    """Return bounded, deterministic category labels without duplicates."""

    if values in (None, ""):
        return tuple()
    if isinstance(values, str):
        raw_values = _CATEGORY_SEPARATOR_PATTERN.split(values)
    elif isinstance(values, (list, tuple)):
        raw_values = values
    else:
        raise ReferenceLibraryFormatError(f"{field_name} must be a list of strings")
    if len(raw_values) > MAX_REFERENCE_CATEGORIES:
        raise ReferenceLibraryFormatError(f"{field_name} contains too many categories")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, raw_value in enumerate(raw_values):
        if not isinstance(raw_value, str):
            raise ReferenceLibraryFormatError(
                f"{field_name}[{index}] must be a string"
            )
        category = _clean_text(
            raw_value,
            max_length=MAX_REFERENCE_CATEGORY_LENGTH,
            field_name=f"{field_name}[{index}]",
            required=False,
        )
        if not category:
            continue
        key = category.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(category)
    return tuple(normalized)


def normalize_data_type(data_type: object) -> str:
    value = str(data_type or DEFAULT_DATA_TYPE).strip().lower()
    normalized = "".join(char for char in value if char in ALLOWED_DATA_TYPE_CHARS)
    normalized = normalized[:32] or DEFAULT_DATA_TYPE
    return normalized if normalized in ALLOWED_DATA_TYPES else DEFAULT_DATA_TYPE


def _record_from_csv_row(row: dict[str, str], row_index: int) -> ReferenceLibraryRecord:
    spectrum_json = row.get("spectrum_json") or "[]"
    peaks_json = row.get("peaks_json") or "[]"
    categories_json = row.get("categories_json") or "[]"
    if any(
        len(cell) > MAX_JSON_CELL_LENGTH
        for cell in (spectrum_json, peaks_json, categories_json)
    ):
        raise ReferenceLibraryFormatError(f"CSV row {row_index} contains an oversized JSON cell")

    try:
        spectrum = json.loads(spectrum_json or "[]")
        peaks = json.loads(peaks_json or "[]")
        categories = json.loads(categories_json or "[]")
    except json.JSONDecodeError as exc:
        raise ReferenceLibraryFormatError(f"CSV row {row_index} contains malformed JSON") from exc

    return record_from_payload(
        {
            "name": unescape_csv_text(row.get("name", "")),
            "formula": unescape_csv_text(row.get("formula", "")),
            "description": unescape_csv_text(row.get("description", "")),
            "cas_number": unescape_csv_text(row.get("cas_number", "")),
            "manufacturer": unescape_csv_text(row.get("manufacturer", "")),
            "sample_id": unescape_csv_text(row.get("sample_id", "")),
            "instrument": unescape_csv_text(row.get("instrument", "")),
            "operator_name": unescape_csv_text(row.get("operator_name", "")),
            "measurement_date": row.get("measurement_date", ""),
            "categories": categories,
            "data_type": row.get("data_type", DEFAULT_DATA_TYPE),
            "schema_version": row.get("record_schema_version", 1),
            "spectrum": spectrum,
            "peaks": peaks,
        },
        row_label=f"CSV row {row_index}",
    )


def _bounded_records(records: Sequence[ReferenceLibraryRecord]) -> list[ReferenceLibraryRecord]:
    validate_reference_collection_limits(records)
    clean_records = [coerce_reference_record(record) for record in records]
    _validate_aggregate_payload(clean_records)
    return clean_records


def validate_reference_collection_limits(
    records: Sequence[ReferenceLibraryRecord],
) -> None:
    """Reject oversized in-memory imports before any persistence mutation."""

    _validate_record_count(len(records))
    total_spectrum_points = sum(
        len(getattr(record, "spectrum", ()) or ()) for record in records
    )
    if total_spectrum_points > MAX_TOTAL_SPECTRUM_POINTS:
        raise ReferenceLibraryFormatError(
            "reference library contains too many spectrum points"
        )
    total_peaks = sum(len(getattr(record, "peaks", ()) or ()) for record in records)
    if total_peaks > MAX_TOTAL_REFERENCE_PEAKS:
        raise ReferenceLibraryFormatError("reference library contains too many peaks")


def _validate_record_count(count: int) -> None:
    if count > MAX_REFERENCE_RECORDS:
        raise ReferenceLibraryFormatError("reference library import is too large")


def _validate_aggregate_payload(records: Sequence[ReferenceLibraryRecord]) -> None:
    total_spectrum_points = sum(record.spectrum_points for record in records)
    if total_spectrum_points > MAX_TOTAL_SPECTRUM_POINTS:
        raise ReferenceLibraryFormatError(
            "reference library contains too many spectrum points"
        )
    total_peaks = sum(record.peak_count for record in records)
    if total_peaks > MAX_TOTAL_REFERENCE_PEAKS:
        raise ReferenceLibraryFormatError("reference library contains too many peaks")


def _validate_reference_file_size(input_path: str | Path) -> None:
    try:
        file_size = Path(input_path).stat().st_size
    except OSError:
        raise
    if file_size > MAX_REFERENCE_FILE_BYTES:
        raise ReferenceLibraryFormatError("reference library file is too large")


def _clean_text(
    value: object,
    *,
    max_length: int,
    field_name: str,
    required: bool = True,
) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = " ".join(
        "".join(
            char if not unicodedata.category(char).startswith("C") else " "
            for char in text
        ).split()
    )
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


def _parse_schema_version(
    value: object,
    *,
    field_name: str,
    max_supported: int,
) -> int:
    if isinstance(value, bool):
        raise ReferenceLibraryFormatError(f"{field_name} must be an integer")
    if isinstance(value, int):
        version = value
    elif isinstance(value, str) and value.strip().isdigit():
        version = int(value.strip())
    else:
        raise ReferenceLibraryFormatError(f"{field_name} must be an integer")

    if version < 1 or version > max_supported:
        raise ReferenceLibraryFormatError(f"unsupported {field_name}")
    return version
