import sqlite3
import json
import numpy as np
from typing import List
from dataclasses import dataclass
from pathlib import Path

@dataclass
class MatchResult:
    substance_name: str
    formula: str = ""
    score: float = 0.0
    matched_peaks: int = 0

class SpectrumIdentifier:
    def __init__(self, db_path=None):
        if db_path is None:
            project_root = Path(__file__).resolve().parents[2]
            db_path = project_root / "library.db"

        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self._create_table()
        self.log("✅ База подключена")

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
            self.log(f"✅ Добавлено: {name}")
            return True
        except Exception as e:
            self.log(f"❌ Ошибка: {e}")
            return False

    def clear_database(self):
        try:
            self.conn.execute("DELETE FROM compounds")
            self.conn.commit()
            self.log("🗑 База очищена")
            return True
        except Exception as e:
            self.log(f"❌ Ошибка очистки: {e}")
            return False

    def restore_default(self):
        """Восстанавливает стандартную базу"""
        self.clear_database()
        default_data = [
            ("Acetone", "C3H6O", [1,3,10,4,1]),
            ("Ethanol", "C2H5OH", [2,8,5,1]),
            ("Isopropanol", "C3H8O", [1,9,3]),
            ("Methanol", "CH4O", [3,7,2]),
            ("Benzene", "C6H6", [5,12,8,3]),
            ("Toluene", "C7H8", [4,11,7,2])
        ]
        for name, formula, spectrum in default_data:
            self.add_reference(name, spectrum, formula)
        self.log("♻ База восстановлена до стандартной")
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
                # Current model compares spectrum points, not detected peak identities.
                matched_peaks=min_len
            ))

        return sorted(results, key=lambda x: x.score, reverse=True)

    def _normalize(self, arr: np.ndarray) -> np.ndarray:
        max_val = np.max(arr)
        return arr / (max_val + 1e-10) if max_val > 0 else arr

    def log(self, msg: str):
        print(f"[DB] {msg}")
