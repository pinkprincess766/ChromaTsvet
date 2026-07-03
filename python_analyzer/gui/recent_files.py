"""Recent-file helpers backed by QSettings."""

from __future__ import annotations

from pathlib import Path


RECENT_FILES_KEY = "ui/recent_files"
LAST_DIRECTORY_KEY = "ui/last_directory"
MAX_RECENT_FILES = 10


def load_recent_files(settings, *, limit: int = MAX_RECENT_FILES) -> list[str]:
    """Return normalized recent-file paths from settings."""
    paths = []
    seen = set()
    for path_string in _settings_string_list(settings.value(RECENT_FILES_KEY, [])):
        normalized = _normalized_path_string(path_string)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        paths.append(normalized)
        if len(paths) >= limit:
            break
    return paths


def remember_recent_file(
    settings,
    file_path: str | Path,
    *,
    limit: int = MAX_RECENT_FILES,
) -> list[str]:
    """Move ``file_path`` to the top of the recent-file list."""
    normalized = _normalized_path_string(file_path)
    if not normalized:
        return load_recent_files(settings, limit=limit)

    paths = [normalized]
    paths.extend(
        path
        for path in load_recent_files(settings, limit=limit)
        if path != normalized
    )
    paths = paths[:limit]
    settings.setValue(RECENT_FILES_KEY, paths)
    remember_last_directory(settings, normalized)
    return paths


def forget_recent_file(settings, file_path: str | Path) -> list[str]:
    """Remove one path from the recent-file list."""
    normalized = _normalized_path_string(file_path)
    paths = [path for path in load_recent_files(settings) if path != normalized]
    settings.setValue(RECENT_FILES_KEY, paths)
    return paths


def clear_recent_files(settings) -> None:
    settings.remove(RECENT_FILES_KEY)


def remember_last_directory(settings, file_or_directory: str | Path) -> str:
    """Store a usable directory for the next open/save dialog."""
    path = Path(file_or_directory).expanduser()
    directory = path if path.is_dir() else path.parent
    if directory and directory.is_dir():
        directory_string = str(directory)
        settings.setValue(LAST_DIRECTORY_KEY, directory_string)
        return directory_string
    return ""


def load_last_directory(settings) -> str:
    directory = settings.value(LAST_DIRECTORY_KEY, "")
    if not directory:
        return ""
    path = Path(str(directory)).expanduser()
    if path.is_dir():
        return str(path)
    return ""


def suggested_dialog_path(settings, default_name: str) -> str:
    directory = load_last_directory(settings)
    if not directory:
        return default_name
    return str(Path(directory) / default_name)


def _settings_string_list(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _normalized_path_string(file_path: str | Path) -> str:
    try:
        path = Path(file_path).expanduser()
    except (TypeError, ValueError):
        return ""
    if not path.is_absolute():
        path = path.resolve(strict=False)
    return str(path)
