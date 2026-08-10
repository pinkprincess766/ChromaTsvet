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
    peak_to_reference_peak,
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


def _safe_path_label(path: Path) -> str:
    path_string = str(path)
    if path_string == ":memory:":
        return path_string
    return path.name or "library.db"
