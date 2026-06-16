import os
from pathlib import Path
import shutil
import sys


APP_NAME = "ChromaTsvet"


def get_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


PROJECT_ROOT = get_project_root()
SEED_LIBRARY_DB = PROJECT_ROOT / "library.db"
LIBRARY_DB = SEED_LIBRARY_DB
RUST_MODULE_DIR = PROJECT_ROOT


def ensure_rust_in_path():
    if str(RUST_MODULE_DIR) not in sys.path:
        sys.path.insert(0, str(RUST_MODULE_DIR))


def get_library_db_path() -> Path:
    user_database = get_user_data_dir() / "library.db"
    if not user_database.exists() and SEED_LIBRARY_DB.is_file():
        _copy_seed_database(SEED_LIBRARY_DB, user_database)
    return user_database


def get_user_data_dir(app_name: str = APP_NAME) -> Path:
    """Return a persistent writable directory for application state."""
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
    """Copy the bundled seed database without replacing existing user data."""
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
