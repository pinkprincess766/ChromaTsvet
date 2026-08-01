from __future__ import annotations

import logging
import sqlite3
import json
import math
import numpy as np
from typing import List
from dataclasses import dataclass
from pathlib import Path
from paths import DEFAULT_REFERENCE_DATA, get_library_db_path
from python_analyzer.analysis.models import ReferencePeak, PeakMatch, PeakBasedMatchResult


logger = logging.getLogger("chromatsvet.identification")

DEFAULT_DATA_TYPE = "generic"
ALLOWED_DATA_TYPE_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
DATA_TYPE_CHOICES = (
    ("Generic", "generic"),
    ("IR", "ir"),
    ("Raman", "raman"),
    ("Mass spectrometry", "ms"),
    ("UV-Vis", "uv_vis"),
    ("Fluorescence", "fluorescence"),
)
ALLOWED_DATA_TYPES = {value for _, value in DATA_TYPE_CHOICES}

FREQUENCY_SCORE_WEIGHT = 0.65
INTENSITY_SCORE_WEIGHT = 0.25
AREA_SCORE_WEIGHT = 0.10
WIDTH_SCORE_WEIGHT = 0.0
LOG_RATIO_SCALE = math.log(4.0)
LOG_RATIO_EPSILON = 1e-12

@dataclass(init=False)
class MatchResult:
    substance_name: str
    formula: str = ""
    score: float = 0.0
    compared_points: int = 0

    def __init__(
        self,
        substance_name: str,
        formula: str = "",
        score: float = 0.0,
        compared_points: int = 0,
        *,
        matched_points: int | None = None,
    ):
        if matched_points is not None:
            compared_points = matched_points
        self.substance_name = substance_name
        self.formula = formula
        self.score = score
        self.compared_points = compared_points

    @property
    def matched_points(self) -> int:
        """Backward-compatible alias for the pre-v0.1 field name."""
        return self.compared_points


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


class SpectrumIdentifier:
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

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _create_table(self):
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
        self._add_column_if_missing("peaks_json", "TEXT")
        self._add_column_if_missing("schema_version", "INTEGER DEFAULT 1")
        self._add_column_if_missing("data_type", "TEXT DEFAULT 'generic'")
        self.conn.commit()

    def _add_column_if_missing(self, column_name: str, column_definition: str) -> None:
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
    ):
        """Add or update a reference.

        Can store either raw intensities (legacy) or peak features.
        """
        try:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("reference name cannot be empty")

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
                            "frequency": p.frequency,
                            "intensity": p.intensity,
                            "width": p.width,
                            "width_hz": p.width_hz,
                            "area": p.area,
                            "snr": p.snr,
                        }
                        for p in reference_peaks
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
                    str(formula or "").strip(),
                    spectrum_json,
                    peaks_json,
                    schema_ver,
                    normalized_data_type,
                ),
            )
            self.conn.commit()
            logger.info("Added reference substance: %s", name)
            return True
        except Exception as exc:
            logger.error(
                "Could not add reference substance %r (%s)",
                name,
                type(exc).__name__,
            )
            return False

    def clear_database(self):
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
        """Update editable reference metadata without touching stored spectra or peaks."""
        try:
            normalized_id = int(reference_id)
            if normalized_id <= 0:
                raise ValueError("reference id must be positive")

            clean_name = str(name or "").strip()
            if not clean_name:
                raise ValueError("reference name cannot be empty")

            cursor = self.conn.execute(
                """
                UPDATE compounds
                SET name = ?, formula = ?, data_type = ?
                WHERE id = ?
                """,
                (
                    clean_name,
                    str(formula or "").strip(),
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

    def restore_default(self):
        """Restore the default reference database."""
        if not self.clear_database():
            return False

        for name, formula, spectrum in DEFAULT_REFERENCE_DATA:
            if not self.add_reference(name, spectrum, formula):
                return False

        self.log("♻ Default database restored")
        return True

    def find_matches(self, unknown_spectrum: np.ndarray) -> List[MatchResult]:
        """Legacy cosine similarity on raw spectrum (for backward compatibility)."""
        if len(unknown_spectrum) == 0:
            return []

        unk_norm = self._normalize(unknown_spectrum)
        results = []

        cursor = self.conn.execute("SELECT name, formula, spectrum FROM compounds")
        for name, formula, spectrum_json in cursor.fetchall():
            if not spectrum_json:
                continue  # peak-only reference
            ref_int = np.array(json.loads(spectrum_json))
            ref_norm = self._normalize(ref_int[:len(unk_norm)])

            min_len = min(len(unk_norm), len(ref_norm))
            if min_len == 0:
                continue

            score = np.dot(unk_norm[:min_len], ref_norm[:min_len]) / (
                np.linalg.norm(unk_norm[:min_len]) * np.linalg.norm(ref_norm[:min_len]) + 1e-10
            )

            results.append(MatchResult(
                substance_name=name,
                formula=formula or "",
                score=round(float(score), 3),
                # This is the overlap used by cosine similarity, not matched peaks.
                compared_points=min_len
            ))

        return sorted(results, key=lambda x: x.score, reverse=True)

    def find_peak_matches(
        self,
        unknown_peaks: list[dict],
        frequency_tolerance: float = 5.0,
        data_type: str | None = None,
    ) -> List[PeakBasedMatchResult]:
        """Peak-based matching against stored references (schema v2+)."""
        normalized_unknown_peaks = normalize_reference_peaks(unknown_peaks)
        if not normalized_unknown_peaks:
            return []

        results: List[PeakBasedMatchResult] = []

        requested_data_type = normalize_data_type(data_type) if data_type else None
        query = (
            "SELECT name, formula, peaks_json, data_type "
            "FROM compounds WHERE peaks_json IS NOT NULL"
        )

        cursor = self.conn.execute(query)
        for name, formula, peaks_json, ref_data_type in cursor.fetchall():
            normalized_ref_type = normalize_data_type(ref_data_type)
            if (
                requested_data_type
                and normalized_ref_type not in (requested_data_type, DEFAULT_DATA_TYPE)
            ):
                continue
            try:
                ref_peak_dicts = json.loads(peaks_json)
                if not isinstance(ref_peak_dicts, list):
                    raise ValueError("peaks_json must contain a list")
                ref_peaks = normalize_reference_peaks(ref_peak_dicts)
            except (TypeError, ValueError, json.JSONDecodeError):
                logger.warning("Skipping malformed peak reference for %s", name)
                continue
            if not ref_peaks:
                continue

            matches = find_peak_matches(
                normalized_unknown_peaks,
                ref_peaks,
                frequency_tolerance=frequency_tolerance,
            )
            matched_unknown = {
                match.unknown_index for match in matches if match.unknown_index >= 0
            }
            matched_reference = {
                match.reference_index for match in matches if match.reference_index >= 0
            }

            score = compute_peak_based_score(
                matches, len(normalized_unknown_peaks), len(ref_peaks)
            )

            results.append(
                PeakBasedMatchResult(
                    substance_name=name,
                    formula=formula or "",
                    score=score,
                    matched_peaks=matches,
                    unmatched_unknown=[
                        peak
                        for index, peak in enumerate(normalized_unknown_peaks)
                        if index not in matched_unknown
                    ],
                    unmatched_reference=[
                        peak
                        for index, peak in enumerate(ref_peaks)
                        if index not in matched_reference
                    ],
                    num_matched=len(matches),
                )
            )

        return sorted(results, key=lambda x: x.score, reverse=True)

    def _normalize(self, arr: np.ndarray) -> np.ndarray:
        max_val = np.max(arr)
        return arr / (max_val + 1e-10) if max_val > 0 else arr

    def log(self, msg: str):
        logger.info(msg)


def normalize_data_type(data_type: object) -> str:
    value = str(data_type or DEFAULT_DATA_TYPE).strip().lower()
    if not value:
        return DEFAULT_DATA_TYPE

    normalized = "".join(char for char in value if char in ALLOWED_DATA_TYPE_CHARS)
    normalized = normalized[:32] or DEFAULT_DATA_TYPE
    return normalized if normalized in ALLOWED_DATA_TYPES else DEFAULT_DATA_TYPE


def normalize_reference_peaks(peaks: list[object]) -> list[ReferencePeak]:
    normalized_peaks = []
    for peak in peaks:
        reference_peak = peak_to_reference_peak(peak)
        if reference_peak is not None:
            normalized_peaks.append(reference_peak)
    return normalized_peaks


def peak_to_reference_peak(peak: object) -> ReferencePeak | None:
    frequency = _peak_value(peak, "frequency", None)
    if frequency is None:
        frequency = _peak_value(peak, "position", None)
    intensity = _peak_value(peak, "intensity", None)

    if frequency is None or intensity is None:
        return None

    frequency = _finite_float(frequency)
    intensity = _finite_float(intensity)
    if frequency is None or intensity is None:
        return None

    width = _finite_float(_peak_value(peak, "width", 0.0), default=0.0)
    width_hz = _finite_float(_peak_value(peak, "width_hz", 0.0), default=0.0)
    area = _finite_float(_peak_value(peak, "area", 0.0), default=0.0)
    snr = _finite_float(_peak_value(peak, "snr", 0.0), default=0.0)

    return ReferencePeak(
        frequency=frequency,
        intensity=max(0.0, intensity),
        width=max(0.0, width),
        width_hz=max(0.0, width_hz),
        area=max(0.0, area),
        snr=max(0.0, snr),
    )


def _peak_value(peak: object, field_name: str, default: object = None) -> object:
    if isinstance(peak, dict):
        return peak.get(field_name, default)
    return getattr(peak, field_name, default)


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


def find_peak_matches(
    unknown_peaks: list[dict | ReferencePeak],
    reference_peaks: list[ReferencePeak],
    frequency_tolerance: float = 5.0,  # Hz or units
    frequency_weight: float = FREQUENCY_SCORE_WEIGHT,
    intensity_weight: float = INTENSITY_SCORE_WEIGHT,
    area_weight: float = AREA_SCORE_WEIGHT,
    width_weight: float = WIDTH_SCORE_WEIGHT,
) -> list[PeakMatch]:
    """Basic peak-to-peak matcher with frequency tolerance.

    Matches each unknown peak to the closest reference peak within tolerance.
    Returns list of PeakMatch with simple scoring.
    """
    frequency_tolerance = _finite_float(frequency_tolerance, default=0.0) or 0.0
    if frequency_tolerance <= 0.0:
        return []

    weights = _score_weights(
        frequency_weight,
        intensity_weight,
        area_weight,
        width_weight,
    )

    unk_peaks = normalize_reference_peaks(unknown_peaks)
    ref_peaks = normalize_reference_peaks(reference_peaks)
    candidates = build_peak_match_candidates(
        unk_peaks,
        ref_peaks,
        frequency_tolerance,
        weights,
    )
    return select_one_to_one_peak_matches(unk_peaks, ref_peaks, candidates)


def build_peak_match_candidates(
    unknown_peaks: list[ReferencePeak],
    reference_peaks: list[ReferencePeak],
    frequency_tolerance: float,
    weights: dict[str, float] | None = None,
) -> list[tuple[float, float, int, int, float, float]]:
    """Build possible peak matches inside a frequency tolerance window.

    Sorting both peak lists keeps candidate generation proportional to the
    number of in-window pairs: O(U log U + R log R + K), where K is the number
    of candidate matches admitted by the tolerance.
    """
    weights = weights or _score_weights()
    unknown_sorted = sorted(
        enumerate(unknown_peaks),
        key=lambda item: item[1].frequency,
    )
    reference_sorted = sorted(
        enumerate(reference_peaks),
        key=lambda item: item[1].frequency,
    )

    candidates = []
    window_left = 0
    window_right = 0
    for unknown_index, unknown_peak in unknown_sorted:
        min_frequency = unknown_peak.frequency - frequency_tolerance
        max_frequency = unknown_peak.frequency + frequency_tolerance

        while (
            window_left < len(reference_sorted)
            and reference_sorted[window_left][1].frequency < min_frequency
        ):
            window_left += 1
        while (
            window_right < len(reference_sorted)
            and reference_sorted[window_right][1].frequency <= max_frequency
        ):
            window_right += 1

        for reference_index, reference_peak in reference_sorted[window_left:window_right]:
            candidate = _score_peak_pair(
                unknown_index,
                unknown_peak,
                reference_index,
                reference_peak,
                frequency_tolerance,
                weights,
            )
            if candidate is not None:
                candidates.append(candidate)

    return candidates


def select_one_to_one_peak_matches(
    unknown_peaks: list[ReferencePeak],
    reference_peaks: list[ReferencePeak],
    candidates: list[tuple[float, float, int, int, float, float]],
) -> list[PeakMatch]:
    matches: list[PeakMatch] = []
    used_unknown: set[int] = set()
    used_reference: set[int] = set()
    for (
        negative_score,
        frequency_diff,
        unknown_index,
        reference_index,
        intensity_ratio,
        score,
    ) in sorted(candidates):
        if unknown_index in used_unknown or reference_index in used_reference:
            continue

        used_unknown.add(unknown_index)
        used_reference.add(reference_index)
        unknown_peak = unknown_peaks[unknown_index]
        reference_peak = reference_peaks[reference_index]
        matches.append(
            PeakMatch(
                unknown_frequency=unknown_peak.frequency,
                reference_frequency=reference_peak.frequency,
                frequency_diff=frequency_diff,
                intensity_ratio=intensity_ratio,
                score=round(score, 3),
                unknown_index=unknown_index,
                reference_index=reference_index,
            )
        )

    return matches


def _score_peak_pair(
    unknown_index: int,
    unknown_peak: ReferencePeak,
    reference_index: int,
    reference_peak: ReferencePeak,
    frequency_tolerance: float,
    weights: dict[str, float],
) -> tuple[float, float, int, int, float, float] | None:
    frequency_diff = abs(unknown_peak.frequency - reference_peak.frequency)
    if frequency_diff > frequency_tolerance:
        return None

    frequency_score = max(0.0, 1.0 - (frequency_diff / frequency_tolerance))
    intensity_ratio = _safe_ratio(unknown_peak.intensity, reference_peak.intensity)
    score_parts = [("frequency", frequency_score)]
    score_parts.append(
        (
            "intensity",
            _log_ratio_score(unknown_peak.intensity, reference_peak.intensity),
        )
    )

    if unknown_peak.area > 0.0 and reference_peak.area > 0.0:
        score_parts.append(("area", _log_ratio_score(unknown_peak.area, reference_peak.area)))
    if unknown_peak.width_hz > 0.0 and reference_peak.width_hz > 0.0:
        score_parts.append(
            ("width", _log_ratio_score(unknown_peak.width_hz, reference_peak.width_hz))
        )

    score = _weighted_score(score_parts, weights)
    return (-score, frequency_diff, unknown_index, reference_index, intensity_ratio, score)


def _score_weights(
    frequency_weight: float = FREQUENCY_SCORE_WEIGHT,
    intensity_weight: float = INTENSITY_SCORE_WEIGHT,
    area_weight: float = AREA_SCORE_WEIGHT,
    width_weight: float = WIDTH_SCORE_WEIGHT,
) -> dict[str, float]:
    return {
        "frequency": max(0.0, _finite_float(frequency_weight, 0.0) or 0.0),
        "intensity": max(0.0, _finite_float(intensity_weight, 0.0) or 0.0),
        "area": max(0.0, _finite_float(area_weight, 0.0) or 0.0),
        "width": max(0.0, _finite_float(width_weight, 0.0) or 0.0),
    }


def _weighted_score(score_parts: list[tuple[str, float]], weights: dict[str, float]) -> float:
    numerator = 0.0
    denominator = 0.0
    for name, score in score_parts:
        weight = weights.get(name, 0.0)
        if weight <= 0.0:
            continue
        numerator += weight * max(0.0, min(1.0, score))
        denominator += weight

    return numerator / denominator if denominator > 0.0 else 0.0


def _log_ratio_score(left: float, right: float) -> float:
    ratio_error = abs(
        math.log(
            (max(0.0, left) + LOG_RATIO_EPSILON)
            / (max(0.0, right) + LOG_RATIO_EPSILON)
        )
    )
    return max(0.0, 1.0 - (ratio_error / LOG_RATIO_SCALE))


def _safe_ratio(left: float, right: float) -> float:
    return (left + LOG_RATIO_EPSILON) / (right + LOG_RATIO_EPSILON)


def compute_peak_based_score(
    matches: list[PeakMatch],
    num_unknown_peaks: int,
    num_reference_peaks: int,
    unmatched_penalty: float = 0.3,
) -> float:
    """Compute overall score from matches, penalizing unmatched peaks."""
    if not matches:
        return 0.0

    avg_match_score = sum(m.score for m in matches) / len(matches)
    match_ratio = len(matches) / max(num_unknown_peaks, 1)
    coverage = len(matches) / max(num_reference_peaks, 1)

    penalty = unmatched_penalty * (1 - min(match_ratio, coverage))
    final_score = avg_match_score * (1 - penalty)

    return max(0.0, min(1.0, round(final_score, 3)))
