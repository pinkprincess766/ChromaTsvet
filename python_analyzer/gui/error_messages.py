"""Safe, user-facing GUI error message helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UserErrorText:
    """Text prepared for a QMessageBox and the status bar."""

    title: str
    message: str
    status_message: str


def display_file_label(path) -> str:
    """Return a display-safe filename without leaking local directories."""
    try:
        return Path(path).name or "selected file"
    except (TypeError, ValueError):
        return "selected file"


def safe_exception_details(exception: BaseException) -> str:
    """Return useful exception details without absolute local paths."""
    if isinstance(exception, UnicodeDecodeError):
        encoding = exception.encoding or "unknown encoding"
        return f"{encoding} decode error near byte {exception.start}"

    if isinstance(exception, UnicodeError):
        return type(exception).__name__

    if isinstance(exception, OSError):
        if getattr(exception, "strerror", None):
            return str(exception.strerror)
        details = str(exception).strip()
        if details and not getattr(exception, "filename", None):
            return details
        return type(exception).__name__

    return str(exception).strip() or repr(exception)


def spectrum_read_error_text(exception: BaseException) -> UserErrorText:
    """Translate low-level file read failures into actionable UI text."""
    if isinstance(exception, FileNotFoundError):
        return UserErrorText(
            title="File not found",
            message=(
                "The selected spectrum file no longer exists. "
                "Check whether it was moved, renamed, or deleted."
            ),
            status_message="Spectrum file not found",
        )

    if isinstance(exception, PermissionError):
        return UserErrorText(
            title="File permission error",
            message=(
                "ChromaTsvet does not have permission to read this file. "
                "Check the file permissions or copy it to a readable folder."
            ),
            status_message="Spectrum file permission error",
        )

    if isinstance(exception, UnicodeError):
        return UserErrorText(
            title="Unsupported text encoding",
            message=(
                "The selected spectrum file could not be decoded as text. "
                "Export it as UTF-8 CSV/TXT and try again."
            ),
            status_message="Unsupported spectrum file encoding",
        )

    if isinstance(exception, csv.Error):
        return UserErrorText(
            title="Malformed CSV/TXT file",
            message=(
                "The selected table has malformed quoting or separators. "
                "Check the delimiter, quotes, and column layout."
            ),
            status_message="Malformed spectrum table",
        )

    return UserErrorText(
        title="Could not open file",
        message=(
            "The selected spectrum file could not be read. "
            "Check its format, encoding, and permissions."
        ),
        status_message="Could not read spectrum file",
    )
