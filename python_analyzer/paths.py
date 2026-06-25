"""Compatibility proxy for running ``python_analyzer/main.py`` directly."""

from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys


if getattr(sys, "frozen", False):
    APP_NAME = "ChromaTsvet"
    DEFAULT_REFERENCE_DATA = [
        ("Acetone", "C3H6O", [1, 3, 10, 4, 1]),
        ("Ethanol", "C2H5OH", [2, 8, 5, 1]),
        ("Isopropanol", "C3H8O", [1, 9, 3]),
        ("Methanol", "CH4O", [3, 7, 2]),
        ("Benzene", "C6H6", [5, 12, 8, 3]),
        ("Toluene", "C7H8", [4, 11, 7, 2]),
    ]
    PROJECT_ROOT = Path(sys._MEIPASS)
    SEED_LIBRARY_DB = PROJECT_ROOT / "library.db"
    LIBRARY_DB = SEED_LIBRARY_DB
    RUST_MODULE_DIR = PROJECT_ROOT

    def get_project_root() -> Path:
        return PROJECT_ROOT

    def ensure_rust_in_path():
        if str(RUST_MODULE_DIR) not in sys.path:
            sys.path.insert(0, str(RUST_MODULE_DIR))

    def get_library_db_path() -> Path:
        user_database = get_user_data_dir() / "library.db"
        if not user_database.exists():
            if SEED_LIBRARY_DB.is_file():
                _copy_seed_database(SEED_LIBRARY_DB, user_database)
            else:
                _create_default_database(user_database)
        return user_database

    def get_user_data_dir(app_name: str = APP_NAME) -> Path:
        candidates = []
        configured_directory = os.environ.get("CHROMATSVET_DATA_DIR")
        if configured_directory:
            candidates.append(Path(configured_directory).expanduser())

        try:
            from PyQt5.QtCore import QStandardPaths

            qt_location = QStandardPaths.writableLocation(
                QStandardPaths.AppLocalDataLocation
            )
            if qt_location:
                candidates.append(Path(qt_location) / app_name)
        except (ImportError, RuntimeError):
            pass

        try:
            candidates.append(Path.home() / f".{app_name.lower()}")
        except RuntimeError:
            pass

        for directory in candidates:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError:
                continue
            return directory

        raise OSError("Could not create a persistent ChromaTsvet data directory")

    def _copy_seed_database(seed_database: Path, user_database: Path) -> None:
        user_database.parent.mkdir(parents=True, exist_ok=True)
        temporary_database = user_database.with_name(
            f".{user_database.name}.{os.getpid()}.tmp"
        )
        try:
            shutil.copy2(seed_database, temporary_database)
            if not user_database.exists():
                temporary_database.replace(user_database)
        finally:
            temporary_database.unlink(missing_ok=True)

    def _create_default_database(user_database: Path) -> None:
        user_database.parent.mkdir(parents=True, exist_ok=True)
        temporary_database = user_database.with_name(
            f".{user_database.name}.{os.getpid()}.tmp"
        )
        try:
            connection = sqlite3.connect(temporary_database)
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS compounds (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        formula TEXT,
                        spectrum TEXT NOT NULL
                    )
                    """
                )
                connection.executemany(
                    """
                    INSERT INTO compounds (name, formula, spectrum)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (
                            name,
                            formula,
                            json.dumps([float(value) for value in spectrum]),
                        )
                        for name, formula, spectrum in DEFAULT_REFERENCE_DATA
                    ],
                )
                connection.commit()
            finally:
                connection.close()

            if not user_database.exists():
                temporary_database.replace(user_database)
        finally:
            temporary_database.unlink(missing_ok=True)
else:
    root_paths_file = Path(__file__).resolve().parents[1] / "paths.py"
    spec = spec_from_file_location("_chromatsvet_project_paths", root_paths_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load project paths from {root_paths_file}")

    project_paths = module_from_spec(spec)
    spec.loader.exec_module(project_paths)

    get_project_root = project_paths.get_project_root
    get_user_data_dir = project_paths.get_user_data_dir
    APP_NAME = project_paths.APP_NAME
    PROJECT_ROOT = project_paths.PROJECT_ROOT
    SEED_LIBRARY_DB = project_paths.SEED_LIBRARY_DB
    LIBRARY_DB = project_paths.LIBRARY_DB
    RUST_MODULE_DIR = project_paths.RUST_MODULE_DIR
    ensure_rust_in_path = project_paths.ensure_rust_in_path
    get_library_db_path = project_paths.get_library_db_path
