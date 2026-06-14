from pathlib import Path
import sys


def get_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


PROJECT_ROOT = get_project_root()
LIBRARY_DB = PROJECT_ROOT / "library.db"
RUST_MODULE_DIR = PROJECT_ROOT


def ensure_rust_in_path():
    if str(RUST_MODULE_DIR) not in sys.path:
        sys.path.insert(0, str(RUST_MODULE_DIR))


def get_library_db_path() -> Path:
    LIBRARY_DB.parent.mkdir(parents=True, exist_ok=True)
    return LIBRARY_DB
