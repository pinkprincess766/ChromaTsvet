from __future__ import annotations

import logging
import sqlite3
import json
import numpy as np
from typing import List
from dataclasses import dataclass
from pathlib import Path
from paths import DEFAULT_REFERENCE_DATA, get_library_db_path


logger = logging.getLogger("chromatsvet.identification")

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

class SpectrumIdentifier:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = get_library_db_path()

        self.db_path = Path(db_path)
        try:
            self.conn = sqlite3.connect(self.db_path)
            self._create_table()
        except Exception:
            if hasattr(self, "conn"):
                self.conn.close()
            logger.exception("Failed to connect to database: %s", self.db_path)
            raise
        logger.info("Database connected: %s", self.db_path)

    def _create_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS compounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                formula TEXT,
                spectrum TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def add_reference(self, name: str, intensities: list, formula: str = ""):
        try:
            spectrum_json = json.dumps([float(x) for x in intensities])
            self.conn.execute("""
                INSERT OR REPLACE INTO compounds (name, formula, spectrum)
                VALUES (?, ?, ?)
            """, (name.strip(), formula.strip(), spectrum_json))
            self.conn.commit()
            logger.info("Added reference substance: %s", name)
            return True
        except Exception:
            logger.exception("Could not add reference substance %r", name)
            return False

    def clear_database(self):
        try:
            self.conn.execute("DELETE FROM compounds")
            self.conn.commit()
            logger.info("Reference database cleared")
            return True
        except Exception:
            logger.exception("Could not clear the reference database")
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
        if len(unknown_spectrum) == 0:
            return []

        unk_norm = self._normalize(unknown_spectrum)
        results = []

        cursor = self.conn.execute("SELECT name, formula, spectrum FROM compounds")
        for name, formula, spectrum_json in cursor.fetchall():
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

    def _normalize(self, arr: np.ndarray) -> np.ndarray:
        max_val = np.max(arr)
        return arr / (max_val + 1e-10) if max_val > 0 else arr

    def log(self, msg: str):
        logger.info(msg)
