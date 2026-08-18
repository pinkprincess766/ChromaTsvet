from __future__ import annotations

import logging
import json
import math
import numpy as np
from typing import List
from dataclasses import dataclass
from python_analyzer.analysis.models import ReferencePeak, PeakBasedMatchResult
from python_analyzer.analysis.identification_evidence import (
    EVIDENCE_LEGACY,
    summarize_match_evidence,
)
from python_analyzer.core.peak_matching import (
    DATA_TYPE_CHOICES,
    DEFAULT_DATA_TYPE,
    build_peak_match_candidates,
    compute_peak_based_score,
    find_peak_matches,
    normalize_data_type,
    normalize_reference_peaks,
    peak_to_reference_peak,
    select_one_to_one_peak_matches,
)
from python_analyzer.core.reference_library_io import (
    ReferenceImportPreview,
    ReferenceImportResult,
    ReferenceLibraryRecord,
)
from python_analyzer.core.reference_repository import (
    ReferenceLibraryEntry,
    ReferenceRepository,
)


logger = logging.getLogger("chromatsvet.identification")
MAX_LEGACY_SPECTRUM_POINTS = 2_000_000

@dataclass(init=False)
class MatchResult:
    substance_name: str
    formula: str = ""
    score: float = 0.0
    compared_points: int = 0
    method: str = "legacy_cosine"
    evidence_level: str = EVIDENCE_LEGACY

    def __init__(
        self,
        substance_name: str,
        formula: str = "",
        score: float = 0.0,
        compared_points: int = 0,
        *,
        matched_points: int | None = None,
        method: str = "legacy_cosine",
        evidence_level: str = EVIDENCE_LEGACY,
    ):
        if matched_points is not None:
            compared_points = matched_points
        self.substance_name = substance_name
        self.formula = formula
        self.score = score
        self.compared_points = compared_points
        self.method = method
        self.evidence_level = evidence_level

    @property
    def matched_points(self) -> int:
        """Backward-compatible alias for the pre-v0.1 field name."""
        return self.compared_points


class SpectrumIdentifier:
    def __init__(self, db_path=None):
        self.repository = ReferenceRepository(db_path)
        self.db_path = self.repository.db_path
        # Compatibility for tests and old UI code that still inspects the DB.
        self.conn = self.repository.conn

    def close(self) -> None:
        repository = getattr(self, "repository", None)
        if repository is not None:
            repository.close()
        self.conn = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def add_reference(
        self,
        name: str,
        intensities: list | None = None,
        formula: str = "",
        peaks: list[ReferencePeak] | None = None,
        data_type: str = "generic",
        description: str = "",
        cas_number: str = "",
        manufacturer: str = "",
        categories: list[str] | tuple[str, ...] | str = (),
    ) -> bool:
        return self.repository.add_reference(
            name,
            intensities,
            formula,
            peaks=peaks,
            data_type=data_type,
            description=description,
            cas_number=cas_number,
            manufacturer=manufacturer,
            categories=categories,
        )

    def clear_database(self) -> bool:
        return self.repository.clear_database()

    def list_references(self) -> list[ReferenceLibraryEntry]:
        return self.repository.list_references()

    def export_reference_records(
        self,
        reference_ids: list[int] | None = None,
    ) -> list[ReferenceLibraryRecord]:
        return self.repository.export_reference_records(reference_ids)

    def preview_reference_import(
        self,
        records: list[ReferenceLibraryRecord],
    ) -> ReferenceImportPreview:
        return self.repository.preview_reference_import(records)

    def import_reference_records(
        self,
        records: list[ReferenceLibraryRecord],
        duplicate_policy: str = "skip",
    ) -> ReferenceImportResult:
        return self.repository.import_reference_records(records, duplicate_policy)

    def delete_reference(self, reference_id: int) -> bool:
        return self.repository.delete_reference(reference_id)

    def update_reference_metadata(
        self,
        reference_id: int,
        name: str,
        formula: str = "",
        data_type: str = "generic",
        description: str = "",
        cas_number: str = "",
        manufacturer: str = "",
        categories: list[str] | tuple[str, ...] | str = (),
    ) -> bool:
        return self.repository.update_reference_metadata(
            reference_id,
            name,
            formula=formula,
            data_type=data_type,
            description=description,
            cas_number=cas_number,
            manufacturer=manufacturer,
            categories=categories,
        )

    def restore_default(self) -> bool:
        return self.repository.restore_default()

    def find_matches(self, unknown_spectrum: np.ndarray) -> List[MatchResult]:
        """Legacy cosine similarity on raw spectrum (for backward compatibility)."""
        unknown_values = _finite_spectrum(unknown_spectrum)
        if unknown_values.size == 0:
            return []

        unk_norm = self._normalize(unknown_values)
        results = []

        for name, formula, spectrum_json in self.repository.legacy_reference_rows():
            if not spectrum_json:
                continue  # peak-only reference
            try:
                decoded_spectrum = json.loads(spectrum_json)
                if not isinstance(decoded_spectrum, list):
                    raise ValueError("legacy spectrum must be a list")
                if len(decoded_spectrum) > MAX_LEGACY_SPECTRUM_POINTS:
                    raise ValueError("legacy spectrum is too large")
                if not decoded_spectrum:
                    continue
                ref_int = _finite_spectrum(decoded_spectrum)
            except (TypeError, ValueError, json.JSONDecodeError):
                logger.warning("Skipping malformed legacy reference record")
                continue
            if ref_int.size == 0:
                logger.warning("Skipping malformed legacy reference record")
                continue
            ref_norm = self._normalize(ref_int[:len(unk_norm)])

            min_len = min(len(unk_norm), len(ref_norm))
            if min_len == 0:
                continue

            score = np.dot(unk_norm[:min_len], ref_norm[:min_len]) / (
                np.linalg.norm(unk_norm[:min_len]) * np.linalg.norm(ref_norm[:min_len]) + 1e-10
            )
            if not math.isfinite(float(score)):
                continue

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
        for name, formula, peaks_json, ref_data_type in self.repository.peak_reference_rows():
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
                # Stored labels may come from an old or externally modified DB.
                # Keep diagnostic logs useful without echoing untrusted text.
                logger.warning("Skipping malformed peak reference record")
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
            evidence = summarize_match_evidence(
                score=score,
                matches=matches,
                unknown_peak_count=len(normalized_unknown_peaks),
                reference_peak_count=len(ref_peaks),
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
                    unknown_peak_count=len(normalized_unknown_peaks),
                    reference_peak_count=len(ref_peaks),
                    sample_coverage=evidence.sample_coverage,
                    reference_coverage=evidence.reference_coverage,
                    mean_frequency_error=evidence.mean_frequency_error,
                    max_frequency_error=evidence.max_frequency_error,
                    evidence_level=evidence.evidence_level,
                )
            )

        return sorted(
            results,
            key=lambda result: (
                -result.score,
                -result.reference_coverage,
                _finite_sort_value(result.mean_frequency_error),
                result.substance_name.casefold(),
            ),
        )

    def _normalize(self, arr: np.ndarray) -> np.ndarray:
        max_val = np.max(arr)
        return arr / (max_val + 1e-10) if max_val > 0 else arr

    def log(self, msg: str):
        logger.info(msg)


def _finite_sort_value(value: object) -> float:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return math.inf
    return numeric_value if math.isfinite(numeric_value) else math.inf


def _finite_spectrum(values: object) -> np.ndarray:
    try:
        spectrum = np.asarray(values, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return np.asarray([], dtype=float)
    if spectrum.size > MAX_LEGACY_SPECTRUM_POINTS:
        return np.asarray([], dtype=float)
    return spectrum if np.all(np.isfinite(spectrum)) else np.asarray([], dtype=float)
