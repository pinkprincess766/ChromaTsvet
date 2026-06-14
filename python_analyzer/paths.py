"""Compatibility proxy for running ``python_analyzer/main.py`` directly."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
    LIBRARY_DB = PROJECT_ROOT / "library.db"
    RUST_MODULE_DIR = PROJECT_ROOT

    def get_project_root() -> Path:
        return PROJECT_ROOT

    def ensure_rust_in_path():
        if str(RUST_MODULE_DIR) not in sys.path:
            sys.path.insert(0, str(RUST_MODULE_DIR))

    def get_library_db_path() -> Path:
        LIBRARY_DB.parent.mkdir(parents=True, exist_ok=True)
        return LIBRARY_DB
else:
    root_paths_file = Path(__file__).resolve().parents[1] / "paths.py"
    spec = spec_from_file_location("_chromatsvet_project_paths", root_paths_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load project paths from {root_paths_file}")

    project_paths = module_from_spec(spec)
    spec.loader.exec_module(project_paths)

    get_project_root = project_paths.get_project_root
    PROJECT_ROOT = project_paths.PROJECT_ROOT
    LIBRARY_DB = project_paths.LIBRARY_DB
    RUST_MODULE_DIR = project_paths.RUST_MODULE_DIR
    ensure_rust_in_path = project_paths.ensure_rust_in_path
    get_library_db_path = project_paths.get_library_db_path
