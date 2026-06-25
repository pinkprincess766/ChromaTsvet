"""Spectrum file reader.

Handles loading of single-column or two-column numeric spectral/chromatogram
data from CSV and TXT files. Supports various delimiters, decimal commas,
and both English and Russian intensity column headers.

This module is intentionally free of Qt and business logic.
"""

from __future__ import annotations

import csv
import io as stdio
import re
from pathlib import Path
from typing import Tuple, List, Optional

import numpy as np


INTENSITY_COLUMN_NAMES = {
    "intensity",
    "intensityau",
    "amplitude",
    "signal",
    "value",
    "response",
    "count",
    "counts",
    "absorbance",
    "y",
    "интенсивность",
    "амплитуда",
    "сигнал",
    "значение",
}


class SpectrumFileFormatError(ValueError):
    """Raised when a spectrum table has an unsupported or ambiguous layout."""


def _normalize_column_name(value: str) -> str:
    return re.sub(r"[^\w]+", "", value.casefold(), flags=re.UNICODE)


def _parse_number(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        try:
            parsed = float(value.replace(",", "."))
        except ValueError:
            return None
    return parsed if np.isfinite(parsed) else None


def _detect_spectrum_delimiter(text: str) -> Optional[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    sample = "\n".join(lines[:50])
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        delimiter = max(
            ("\t", ";", ","),
            key=lambda candidate: sample.count(candidate),
        )
        if delimiter not in sample:
            return None

    decimal_comma_pattern = (
        r"\s*[+-]?(?:\d+,\d*|,\d+)(?:[eE][+-]?\d+)?\s*"
    )
    decimal_lines = lines
    if _normalize_column_name(lines[0]) in INTENSITY_COLUMN_NAMES:
        decimal_lines = lines[1:]
    if delimiter == "," and decimal_lines and all(
        re.fullmatch(decimal_comma_pattern, line) for line in decimal_lines
    ):
        # A decimal-comma series is ambiguous with a headerless 2-column
        # CSV. Prefer the locale-aware legacy single-column format.
        return None
    return delimiter


def _select_intensity_column(
    records: List[Tuple[int, List[str]]], column_count: int
) -> Tuple[int, int]:
    first_row = records[0][1]
    has_header = any(
        value.strip() and _parse_number(value.strip()) is None
        for value in first_row
    )

    if column_count == 1:
        return 0, 1 if has_header else 0

    if not has_header:
        if column_count == 2:
            return 1, 0
        raise SpectrumFileFormatError(
            "A table without a header must contain exactly two columns "
            "(position and intensity)."
        )

    intensity_columns = [
        index
        for index, value in enumerate(first_row)
        if _normalize_column_name(value) in INTENSITY_COLUMN_NAMES
    ]
    if len(intensity_columns) != 1:
        available_columns = ", ".join(
            value.strip() or "<empty>" for value in first_row
        )
        raise SpectrumFileFormatError(
            "Could not identify one intensity column. Use a header such as "
            f"'intensity', 'amplitude', 'signal', or 'value'. Found: {available_columns}."
        )
    return intensity_columns[0], 1


def read_spectrum_file(file_path: str | Path) -> Tuple[List[float], List[Tuple[int, str]]]:
    """Read a spectrum file and return (data, skipped_rows).

    Returns:
        data: list of numeric intensity values
        skipped_rows: list of (line_no, original_value) for rows that could not be parsed
    """
    data: List[float] = []
    skipped_rows: List[Tuple[int, str]] = []

    path = Path(file_path)
    with open(path, "r", encoding="utf-8-sig", newline="") as spectrum_file:
        text = spectrum_file.read()

    delimiter = _detect_spectrum_delimiter(text)
    if delimiter is None:
        records = [
            (line_no, [line.strip()])
            for line_no, line in enumerate(text.splitlines(), start=1)
            if line.strip()
        ]
    else:
        reader = csv.reader(stdio.StringIO(text), delimiter=delimiter, strict=True)
        records = [
            (reader.line_num, row)
            for row in reader
            if any(cell.strip() for cell in row)
        ]

    if not records:
        return data, skipped_rows

    column_count = len(records[0][1])
    for line_no, row in records[1:]:
        if len(row) != column_count:
            raise SpectrumFileFormatError(
                f"Line {line_no} has {len(row)} columns; expected {column_count}. "
                "Use one consistent delimiter throughout the file."
            )

    intensity_column, first_data_row = _select_intensity_column(records, column_count)
    for line_no, row in records[first_data_row:]:
        value = row[intensity_column].strip()
        parsed = _parse_number(value) if value else None
        if parsed is None:
            skipped_rows.append((line_no, value or "<empty>"))
            continue
        data.append(parsed)

    return data, skipped_rows
