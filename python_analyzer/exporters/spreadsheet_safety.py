"""Safety helpers for spreadsheet-like exports."""

from __future__ import annotations

from typing import Any


DANGEROUS_SPREADSHEET_PREFIXES = ("=", "+", "-", "@")


def safe_spreadsheet_cell(value: Any) -> Any:
    """Return ``value`` with formula-like text forced to remain plain text."""

    if not isinstance(value, str):
        return value

    if value.lstrip().startswith(DANGEROUS_SPREADSHEET_PREFIXES):
        return f"'{value}"
    return value
