"""Application logging configuration for ChromaTsvet."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys


_HANDLER_MARKER = "_chromatsvet_handler"
_LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"


def setup_logging(
    app_name: str = "ChromaTsvet",
    log_filename: str = "app.log",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
) -> logging.Logger:
    """Configure and return the shared ChromaTsvet logger.

    Only handlers created by this function are managed. Root logger handlers are
    intentionally left untouched so embedding applications and test runners keep
    control of their own logging configuration.
    """
    app_logger = logging.getLogger("chromatsvet")
    app_logger.setLevel(logging.DEBUG)
    app_logger.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT)
    stream_handler = _get_handler(app_logger, "stderr")
    if stream_handler is None:
        stream_handler = logging.StreamHandler(sys.stderr)
        setattr(stream_handler, _HANDLER_MARKER, "stderr")
        app_logger.addHandler(stream_handler)
    stream_handler.setLevel(console_level)
    stream_handler.setFormatter(formatter)

    file_handler = _get_handler(app_logger, "file")
    if file_handler is None:
        try:
            log_path = _prepare_log_path(app_name, log_filename)
        except (OSError, RuntimeError):
            app_logger.warning(
                "Could not determine a writable log directory; stderr logging remains active",
                exc_info=True,
            )
            return app_logger
        if log_path is None:
            app_logger.warning(
                "No writable log directory was found; stderr logging remains active"
            )
            return app_logger
        try:
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
        except OSError:
            app_logger.warning(
                "Could not create rotating log file at %s; stderr logging remains active",
                log_path,
                exc_info=True,
            )
        else:
            file_handler.setLevel(file_level)
            file_handler.setFormatter(formatter)
            setattr(file_handler, _HANDLER_MARKER, "file")
            app_logger.addHandler(file_handler)
            app_logger.debug("File logging enabled: %s", log_path)

    if file_handler is not None:
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)

    return app_logger


def _get_handler(logger: logging.Logger, handler_type: str) -> logging.Handler | None:
    for handler in logger.handlers:
        if getattr(handler, _HANDLER_MARKER, None) == handler_type:
            return handler
    return None


def _prepare_log_path(app_name: str, log_filename: str) -> Path | None:
    for directory in _log_directory_candidates(app_name):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        return directory / log_filename
    return None


def _log_directory_candidates(app_name: str) -> list[Path]:
    candidates: list[Path] = []
    configured_directory = os.environ.get("CHROMATSVET_LOG_DIR")
    if configured_directory:
        candidates.append(Path(configured_directory).expanduser())

    try:
        from PyQt5.QtCore import QStandardPaths

        qt_location = QStandardPaths.writableLocation(
            QStandardPaths.AppLocalDataLocation
        )
        if qt_location:
            candidates.append(Path(qt_location) / app_name / "logs")
    except (ImportError, RuntimeError):
        pass

    safe_name = re.sub(r"[^a-z0-9._-]+", "-", app_name.lower()).strip("-")
    safe_name = safe_name or "chromatsvet"
    try:
        candidates.append(Path.home() / f".{safe_name}" / "logs")
    except RuntimeError:
        pass

    try:
        from paths import get_project_root

        candidates.append(get_project_root() / "logs")
    except (ImportError, OSError, RuntimeError):
        pass

    try:
        candidates.append(Path.cwd() / "logs")
    except OSError:
        pass

    unique_candidates = []
    for candidate in candidates:
        if candidate not in unique_candidates:
            unique_candidates.append(candidate)
    return unique_candidates
