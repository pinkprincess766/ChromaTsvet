"""SQLite-backed storage for the local reference library."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import math
from pathlib import Path

import sqlite3

from paths import DEFAULT_REFERENCE_DATA, get_library_db_path
from python_analyzer.analysis.models import ReferencePeak
from python_analyzer.core.peak_matching import (
    normalize_data_type,
    normalize_reference_peaks,
    peak_to_reference_peak,
)
from python_analyzer.core.reference_library_io import (
    ReferenceImportPreview,
    ReferenceImportResult,
    ReferenceLibraryRecord,
    build_import_preview,
    canonical_reference_name,
    coerce_reference_record,
    merge_reference_records,
    normalize_duplicate_policy,
)


logger = logging.getLogger("chromatsvet.reference_repository")

MAX_REFERENCE_NAME_LENGTH = 200
MAX_FORMULA_LENGTH = 120
KNOWN_COLUMN_DEFINITIONS = {
    "peaks_json": "TEXT",
    "schema_version": "INTEGER DEFAULT 1",
    "data_type": "TEXT DEFAULT 'generic'",
}


@dataclass(frozen=True)
class ReferenceLibraryEntry:
    """Small UI-safe summary of one reference library row."""

    reference_id: int
    name: str
    formula: str
    data_type: str
    schema_version: int
    spectrum_points: int
    peak_count: int


class ReferenceRepository:
    """Own SQLite persistence for reference spectra and peak features."""

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = get_library_db_path()

        self.db_path = Path(db_path)
        db_label = _safe_path_label(self.db_path)
        try:
            self.conn = sqlite3.connect(self.db_path)
            self._create_table()
        except Exception as exc:
            if hasattr(self, "conn"):
                self.conn.close()
            logger.error(
                "Failed to connect to database %s (%s)",
                db_label,
                type(exc).__name__,
            )
            raise
        logger.info("Database connected: %s", db_label)

    def close(self) -> None:
        conn = getattr(self, "conn", None)
        if conn is None:
            return
        try:
            conn.close()
        except sqlite3.Error:
            logger.warning("Could not close reference database connection")
        finally:
            self.conn = None

    def _create_table(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS compounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                formula TEXT,
                spectrum TEXT,
                peaks_json TEXT,
                schema_version INTEGER DEFAULT 1,
                data_type TEXT DEFAULT 'generic'
            )
        """)
        self._add_known_column_if_missing("peaks_json")
        self._add_known_column_if_missing("schema_version")
        self._add_known_column_if_missing("data_type")
        self.conn.commit()

    def _add_known_column_if_missing(self, column_name: str) -> None:
        if column_name not in KNOWN_COLUMN_DEFINITIONS:
            raise ValueError("unknown reference-library migration column")

        column_definition = KNOWN_COLUMN_DEFINITIONS[column_name]
        try:
            self.conn.execute(
                f"ALTER TABLE compounds ADD COLUMN {column_name} {column_definition}"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                return
            logger.error(
                "Could not migrate compounds.%s (%s)",
                column_name,
                type(exc).__name__,
            )
            raise

    def add_reference(
        self,
        name: str,
        intensities: list | None = None,
        formula: str = "",
        peaks: list[ReferencePeak] | None = None,
        data_type: str = "generic",
    ) -> bool:
        """Add or update a reference row after sanitizing numeric payloads."""

        try:
            clean_name = _safe_user_text(
                name,
                label="reference name",
                max_length=MAX_REFERENCE_NAME_LENGTH,
                allow_empty=False,
            )
            clean_formula = _safe_user_text(
                formula,
                label="formula",
                max_length=MAX_FORMULA_LENGTH,
                allow_empty=True,
            )

            spectrum_json = None
            peaks_json = None
            normalized_data_type = normalize_data_type(data_type)
            schema_ver = 2 if peaks else 1

            if intensities is not None:
                clean_intensities = []
                for intensity in intensities:
                    clean_intensity = _finite_float(intensity)
                    if clean_intensity is None:
                        raise ValueError("reference intensities must be finite numbers")
                    clean_intensities.append(clean_intensity)
                spectrum_json = json.dumps(clean_intensities, allow_nan=False)

            if peaks:
                reference_peaks = []
                for peak in peaks:
                    reference_peak = peak_to_reference_peak(peak)
                    if reference_peak is not None:
                        reference_peaks.append(reference_peak)

                if not reference_peaks:
                    raise ValueError("reference peaks must contain finite frequency and intensity")

                peaks_json = json.dumps(
                    [
                        {
                            "frequency": peak.frequency,
                            "intensity": peak.intensity,
                            "width": peak.width,
                            "width_hz": peak.width_hz,
                            "area": peak.area,
                            "snr": peak.snr,
                        }
                        for peak in reference_peaks
                    ],
                    allow_nan=False,
                )
                if spectrum_json is None:
                    # Older databases may still have `spectrum TEXT NOT NULL`.
                    spectrum_json = "[]"

            self.conn.execute(
                """
                INSERT OR REPLACE INTO compounds
                (name, formula, spectrum, peaks_json, schema_version, data_type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_name,
                    clean_formula,
                    spectrum_json,
                    peaks_json,
                    schema_ver,
                    normalized_data_type,
                ),
            )
            self.conn.commit()
            logger.info("Added reference substance: %s", _safe_log_text(clean_name))
            return True
        except Exception as exc:
            logger.error(
                "Could not add reference substance %r (%s)",
                name,
                type(exc).__name__,
            )
            return False

    def clear_database(self) -> bool:
        try:
            self.conn.execute("DELETE FROM compounds")
            self.conn.commit()
            logger.info("Reference database cleared")
            return True
        except Exception as exc:
            logger.error("Could not clear the reference database (%s)", type(exc).__name__)
            return False

    def list_references(self) -> list[ReferenceLibraryEntry]:
        """Return reference-library rows without exposing database paths."""

        cursor = self.conn.execute(
            """
            SELECT id, name, formula, spectrum, peaks_json, schema_version, data_type
            FROM compounds
            ORDER BY lower(name), id
            """
        )
        entries: list[ReferenceLibraryEntry] = []
        for row in cursor.fetchall():
            (
                reference_id,
                name,
                formula,
                spectrum_json,
                peaks_json,
                schema_version,
                data_type,
            ) = row
            entries.append(
                ReferenceLibraryEntry(
                    reference_id=int(reference_id),
                    name=str(name or ""),
                    formula=str(formula or ""),
                    data_type=normalize_data_type(data_type),
                    schema_version=_safe_int(schema_version, default=1),
                    spectrum_points=_json_list_length(spectrum_json),
                    peak_count=_json_list_length(peaks_json),
                )
            )
        return entries

    def export_reference_records(
        self,
        reference_ids: list[int] | None = None,
    ) -> list[ReferenceLibraryRecord]:
        """Return portable reference records without local database metadata."""

        rows = self._fetch_reference_rows(reference_ids)
        records: list[ReferenceLibraryRecord] = []
        for row in rows:
            record = self._row_to_reference_record(row)
            if record is not None:
                records.append(record)
        return records

    def preview_reference_import(
        self,
        records: list[ReferenceLibraryRecord],
    ) -> ReferenceImportPreview:
        """Build a no-mutation import preview for UI and tests."""

        existing_names = [entry.name for entry in self.list_references()]
        return build_import_preview(records, existing_names)

    def import_reference_records(
        self,
        records: list[ReferenceLibraryRecord],
        duplicate_policy: str = "skip",
    ) -> ReferenceImportResult:
        """Import portable references with an explicit duplicate-name policy."""

        policy = normalize_duplicate_policy(duplicate_policy)
        added = merged = replaced = skipped = failed = 0

        for raw_record in records:
            try:
                record = coerce_reference_record(raw_record)
                key = canonical_reference_name(record.name)
                existing = self._record_for_name_key(key)
                if existing is None:
                    if self._insert_reference_record(record):
                        added += 1
                    else:
                        failed += 1
                    continue

                if policy == "skip":
                    skipped += 1
                    continue

                if policy == "merge":
                    record = merge_reference_records(existing, record)
                    if self._replace_reference_by_name_key(key, record):
                        merged += 1
                    else:
                        failed += 1
                    continue

                if self._replace_reference_by_name_key(key, record):
                    replaced += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                logger.warning(
                    "Skipped malformed imported reference (%s)",
                    type(exc).__name__,
                )

        return ReferenceImportResult(
            added=added,
            merged=merged,
            replaced=replaced,
            skipped=skipped,
            failed=failed,
        )

    def _fetch_reference_rows(
        self,
        reference_ids: list[int] | None = None,
    ) -> list[tuple]:
        query = (
            "SELECT id, name, formula, spectrum, peaks_json, schema_version, data_type "
            "FROM compounds"
        )
        params: list[int] = []
        if reference_ids is not None:
            for reference_id in reference_ids:
                try:
                    normalized_id = int(reference_id)
                except (TypeError, ValueError):
                    continue
                if normalized_id > 0:
                    params.append(normalized_id)
            if not params:
                return []
            placeholders = ", ".join("?" for _ in params)
            query = f"{query} WHERE id IN ({placeholders})"
        query = f"{query} ORDER BY lower(name), id"
        return list(self.conn.execute(query, params).fetchall())

    def _row_to_reference_record(self, row: tuple) -> ReferenceLibraryRecord | None:
        (
            _reference_id,
            name,
            formula,
            spectrum_json,
            peaks_json,
            schema_version,
            data_type,
        ) = row
        try:
            spectrum_values = _json_payload_list(spectrum_json)
            peak_values = _json_payload_list(peaks_json)
            return coerce_reference_record(
                ReferenceLibraryRecord(
                    name=str(name or ""),
                    formula=str(formula or ""),
                    data_type=normalize_data_type(data_type),
                    schema_version=_safe_int(schema_version, default=1),
                    spectrum=tuple(spectrum_values),
                    peaks=tuple(normalize_reference_peaks(peak_values)),
                )
            )
        except Exception as exc:
            logger.warning(
                "Skipped malformed stored reference during export (%s)",
                type(exc).__name__,
            )
            return None

    def _record_for_name_key(self, name_key: str) -> ReferenceLibraryRecord | None:
        for record in self.export_reference_records():
            if canonical_reference_name(record.name) == name_key:
                return record
        return None

    def _reference_ids_for_name_key(self, name_key: str) -> list[int]:
        return [
            entry.reference_id
            for entry in self.list_references()
            if canonical_reference_name(entry.name) == name_key
        ]

    def _insert_reference_record(self, record: ReferenceLibraryRecord) -> bool:
        try:
            with self.conn:
                self._insert_reference_record_without_commit(record)
            return True
        except Exception as exc:
            logger.warning(
                "Could not insert imported reference %r (%s)",
                _safe_log_text(record.name),
                type(exc).__name__,
            )
            return False

    def _replace_reference_by_name_key(
        self,
        name_key: str,
        record: ReferenceLibraryRecord,
    ) -> bool:
        reference_ids = self._reference_ids_for_name_key(name_key)
        placeholders = ", ".join("?" for _ in reference_ids)
        try:
            with self.conn:
                if reference_ids:
                    self.conn.execute(
                        f"DELETE FROM compounds WHERE id IN ({placeholders})",
                        reference_ids,
                    )
                self._insert_reference_record_without_commit(record)
            return True
        except Exception as exc:
            logger.warning(
                "Could not replace imported reference %r (%s)",
                _safe_log_text(record.name),
                type(exc).__name__,
            )
            return False

    def _insert_reference_record_without_commit(
        self,
        record: ReferenceLibraryRecord,
    ) -> None:
        clean_record = coerce_reference_record(record)
        spectrum_json = None
        if clean_record.spectrum:
            spectrum_json = json.dumps(list(clean_record.spectrum), allow_nan=False)

        peaks_json = None
        if clean_record.peaks:
            peaks_json = json.dumps(
                [
                    {
                        "frequency": peak.frequency,
                        "intensity": peak.intensity,
                        "width": peak.width,
                        "width_hz": peak.width_hz,
                        "area": peak.area,
                        "snr": peak.snr,
                    }
                    for peak in clean_record.peaks
                ],
                allow_nan=False,
            )
            if spectrum_json is None:
                spectrum_json = "[]"

        self.conn.execute(
            """
            INSERT INTO compounds
            (name, formula, spectrum, peaks_json, schema_version, data_type)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                clean_record.name,
                clean_record.formula,
                spectrum_json,
                peaks_json,
                clean_record.schema_version,
                normalize_data_type(clean_record.data_type),
            ),
        )

    def delete_reference(self, reference_id: int) -> bool:
        """Delete one reference row by database id."""

        try:
            normalized_id = int(reference_id)
            if normalized_id <= 0:
                raise ValueError("reference id must be positive")
            cursor = self.conn.execute(
                "DELETE FROM compounds WHERE id = ?",
                (normalized_id,),
            )
            self.conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info("Deleted reference substance id=%s", normalized_id)
            return deleted
        except Exception as exc:
            logger.error(
                "Could not delete reference substance id=%r (%s)",
                reference_id,
                type(exc).__name__,
            )
            return False

    def update_reference_metadata(
        self,
        reference_id: int,
        name: str,
        formula: str = "",
        data_type: str = "generic",
    ) -> bool:
        """Update editable reference metadata without touching stored signal data."""

        try:
            normalized_id = int(reference_id)
            if normalized_id <= 0:
                raise ValueError("reference id must be positive")

            clean_name = _safe_user_text(
                name,
                label="reference name",
                max_length=MAX_REFERENCE_NAME_LENGTH,
                allow_empty=False,
            )
            clean_formula = _safe_user_text(
                formula,
                label="formula",
                max_length=MAX_FORMULA_LENGTH,
                allow_empty=True,
            )

            cursor = self.conn.execute(
                """
                UPDATE compounds
                SET name = ?, formula = ?, data_type = ?
                WHERE id = ?
                """,
                (
                    clean_name,
                    clean_formula,
                    normalize_data_type(data_type),
                    normalized_id,
                ),
            )
            self.conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info("Updated reference substance metadata id=%s", normalized_id)
            return updated
        except Exception as exc:
            logger.error(
                "Could not update reference substance metadata id=%r (%s)",
                reference_id,
                type(exc).__name__,
            )
            return False

    def restore_default(self) -> bool:
        """Restore the default reference database."""

        if not self.clear_database():
            return False

        for name, formula, spectrum in DEFAULT_REFERENCE_DATA:
            if not self.add_reference(name, spectrum, formula):
                return False

        logger.info("Default reference database restored")
        return True

    def legacy_reference_rows(self) -> list[tuple[str, str, str]]:
        cursor = self.conn.execute("SELECT name, formula, spectrum FROM compounds")
        return cursor.fetchall()

    def peak_reference_rows(self) -> list[tuple[str, str, str, str]]:
        cursor = self.conn.execute(
            """
            SELECT name, formula, peaks_json, data_type
            FROM compounds
            WHERE peaks_json IS NOT NULL
            """
        )
        return cursor.fetchall()


def _finite_float(value: object, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _safe_user_text(
    value: object,
    *,
    label: str,
    max_length: int,
    allow_empty: bool,
) -> str:
    text = _safe_log_text(str(value or "").strip(), max_length=max_length)
    if not text and not allow_empty:
        raise ValueError(f"{label} cannot be empty")
    return text


def _safe_log_text(value: object, *, max_length: int = 200) -> str:
    safe_limit = max(0, int(max_length))
    text = str(value or "")
    text = "".join(
        char if char.isprintable() and char not in "\r\n\t" else " "
        for char in text
    ).strip()
    if len(text) > safe_limit:
        if safe_limit <= 3:
            return text[:safe_limit]
        return f"{text[:safe_limit - 3]}..."
    return text


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_list_length(payload: object) -> int:
    if not payload:
        return 0
    try:
        value = json.loads(str(payload))
    except (TypeError, json.JSONDecodeError):
        return 0
    return len(value) if isinstance(value, list) else 0


def _json_payload_list(payload: object) -> list[object]:
    if not payload:
        return []
    try:
        value = json.loads(str(payload))
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _safe_path_label(path: Path) -> str:
    path_string = str(path)
    if path_string == ":memory:":
        return path_string
    return path.name or "library.db"
