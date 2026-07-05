import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_PATHS_FILE = REPO_ROOT / "paths.py"
PROXY_PATHS_FILE = REPO_ROOT / "python_analyzer" / "paths.py"


def load_paths_module(module_name, paths_file=ROOT_PATHS_FILE):
    spec = importlib.util.spec_from_file_location(module_name, paths_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PathsTest(unittest.TestCase):
    def test_normal_run_uses_persistent_user_database(self):
        with TemporaryDirectory() as temp_dir:
            user_dir = Path(temp_dir) / "user-data"
            with (
                patch.object(sys, "frozen", False, create=True),
                patch.dict(
                    os.environ,
                    {"CHROMATSVET_DATA_DIR": str(user_dir)},
                    clear=False,
                ),
            ):
                normal_paths = load_paths_module("_test_normal_paths")
                database_path = normal_paths.get_library_db_path()

            self.assertEqual(database_path, user_dir / "library.db")
            self.assertTrue(database_path.is_file())
            connection = sqlite3.connect(database_path)
            try:
                compound_count = connection.execute(
                    "SELECT COUNT(*) FROM compounds"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertGreater(compound_count, 0)

    def test_frozen_database_is_seeded_once_in_user_data_directory(self):
        for index, paths_file in enumerate((ROOT_PATHS_FILE, PROXY_PATHS_FILE)):
            with self.subTest(paths_file=paths_file):
                self._assert_frozen_database_is_persistent(paths_file, index)

    def _assert_frozen_database_is_persistent(self, paths_file, index):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle_dir = root / "bundle"
            user_dir = root / "user-data"
            bundle_dir.mkdir()
            seed_database = bundle_dir / "library.db"
            self._create_database(seed_database, "seed")

            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "_MEIPASS", str(bundle_dir), create=True),
                patch.dict(
                    os.environ,
                    {"CHROMATSVET_DATA_DIR": str(user_dir)},
                    clear=False,
                ),
            ):
                frozen_paths = load_paths_module(
                    f"_test_frozen_paths_{index}", paths_file
                )
                database_path = frozen_paths.get_library_db_path()
                self.assertEqual(database_path, user_dir / "library.db")
                self.assertEqual(self._read_value(database_path), "seed")

                self._write_value(database_path, "user change")
                self._write_value(seed_database, "new seed")

                self.assertEqual(
                    frozen_paths.get_library_db_path(), user_dir / "library.db"
                )
                self.assertEqual(self._read_value(database_path), "user change")

    @staticmethod
    def _create_database(path, value):
        connection = sqlite3.connect(path)
        try:
            connection.execute("CREATE TABLE state (value TEXT NOT NULL)")
            connection.execute("INSERT INTO state VALUES (?)", (value,))
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _write_value(path, value):
        connection = sqlite3.connect(path)
        try:
            connection.execute("UPDATE state SET value = ?", (value,))
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _read_value(path):
        connection = sqlite3.connect(path)
        try:
            return connection.execute("SELECT value FROM state").fetchone()[0]
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
