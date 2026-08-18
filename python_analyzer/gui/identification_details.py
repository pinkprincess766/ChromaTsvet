"""Presentation helpers for inspectable identification candidates."""

from __future__ import annotations

import math
import re
from typing import Any, Sequence

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
MAX_DISPLAY_TEXT = 200
MAX_DETAIL_TABLE_ROWS = 1_000


def identification_overview_values(match: Any) -> list[str]:
    """Return a stable row for the candidate ranking table."""

    method = _safe_text(getattr(match, "method", "legacy_cosine"), 40)
    is_peak_match = method == "peak"
    compared_points = getattr(
        match,
        "compared_points",
        getattr(match, "matched_points", 0),
    )
    return [
        _safe_text(getattr(match, "substance_name", "")),
        _safe_text(getattr(match, "formula", "")),
        _format_number(getattr(match, "score", None), 3),
        str(_non_negative_int(compared_points)),
        _format_percent(getattr(match, "sample_coverage", None))
        if is_peak_match
        else "n/a",
        _format_percent(getattr(match, "reference_coverage", None))
        if is_peak_match
        else "n/a",
        _format_number(getattr(match, "mean_frequency_error", None), 4)
        if is_peak_match
        else "n/a",
        _safe_text(
            getattr(
                match,
                "evidence_level",
                "legacy" if not is_peak_match else "insufficient",
            ),
            32,
        ),
    ]


def has_peak_diagnostics(match: Any) -> bool:
    return getattr(match, "method", "legacy_cosine") == "peak"


class IdentificationDetailsDialog(QDialog):
    """Show matched and unmatched peaks for one ranked candidate."""

    def __init__(self, parent: QWidget, match: Any):
        super().__init__(parent)
        self.setWindowTitle("Identification Candidate Details")
        self.resize(820, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(10)

        title = QLabel(
            _safe_text(getattr(match, "substance_name", "Unnamed candidate"))
        )
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        summary = QFormLayout()
        summary.addRow("Formula", QLabel(_safe_text(getattr(match, "formula", ""))))
        summary.addRow("Method", QLabel(_method_label(match)))
        summary.addRow(
            "Score",
            QLabel(_format_number(getattr(match, "score", None), 3)),
        )
        summary.addRow(
            "Evidence",
            QLabel(_safe_text(getattr(match, "evidence_level", "legacy"))),
        )
        matched_count = _non_negative_int(getattr(match, "compared_points", 0))
        summary.addRow("Matched peaks", QLabel(str(matched_count)))

        if has_peak_diagnostics(match):
            summary.addRow(
                "Sample coverage",
                QLabel(_format_percent(getattr(match, "sample_coverage", None))),
            )
            summary.addRow(
                "Reference coverage",
                QLabel(_format_percent(getattr(match, "reference_coverage", None))),
            )
            summary.addRow(
                "Mean frequency error",
                QLabel(_format_number(getattr(match, "mean_frequency_error", None), 6)),
            )
            summary.addRow(
                "Maximum frequency error",
                QLabel(_format_number(getattr(match, "max_frequency_error", None), 6)),
            )
        layout.addLayout(summary)

        notice = QLabel(
            "Evidence levels rank computational candidates; they do not constitute "
            "a validated chemical identification."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        if has_peak_diagnostics(match):
            layout.addWidget(self._diagnostic_tabs(match), 1)
        else:
            legacy_notice = QLabel(
                "This result uses legacy cosine similarity. Per-peak diagnostics "
                "are not available for this reference record."
            )
            legacy_notice.setWordWrap(True)
            legacy_notice.setAlignment(Qt.AlignCenter)
            layout.addWidget(legacy_notice, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _diagnostic_tabs(self, match: Any) -> QTabWidget:
        matched, matched_total = _bounded_rows(
            getattr(match, "matched_peaks", [])
        )
        unmatched_sample, unmatched_sample_total = _bounded_rows(
            getattr(match, "unmatched_unknown", [])
        )
        unmatched_reference, unmatched_reference_total = _bounded_rows(
            getattr(match, "unmatched_reference", [])
        )
        tabs = QTabWidget()
        tabs.addTab(
            _matched_peak_table(matched),
            _tab_label("Matched", len(matched), matched_total),
        )
        tabs.addTab(
            _reference_peak_table(unmatched_sample),
            _tab_label(
                "Unmatched Sample",
                len(unmatched_sample),
                unmatched_sample_total,
            ),
        )
        tabs.addTab(
            _reference_peak_table(unmatched_reference),
            _tab_label(
                "Unmatched Reference",
                len(unmatched_reference),
                unmatched_reference_total,
            ),
        )
        return tabs


def _matched_peak_table(matches: Sequence[Any]) -> QTableWidget:
    table = _readonly_table(
        [
            "Sample frequency",
            "Reference frequency",
            "|Error|",
            "Intensity ratio",
            "Pair score",
        ],
        len(matches),
    )
    for row, match in enumerate(matches):
        values = [
            _format_number(getattr(match, "unknown_frequency", None), 6),
            _format_number(getattr(match, "reference_frequency", None), 6),
            _format_number(getattr(match, "frequency_diff", None), 6),
            _format_number(getattr(match, "intensity_ratio", None), 6),
            _format_number(getattr(match, "score", None), 3),
        ]
        _set_row(table, row, values)
    return table


def _reference_peak_table(peaks: Sequence[Any]) -> QTableWidget:
    table = _readonly_table(
        ["Frequency", "Intensity", "Width", "Width Hz", "Area", "SNR"],
        len(peaks),
    )
    for row, peak in enumerate(peaks):
        _set_row(
            table,
            row,
            [
                _format_number(getattr(peak, "frequency", None), 6),
                _format_number(getattr(peak, "intensity", None), 6),
                _format_number(getattr(peak, "width", None), 6),
                _format_number(getattr(peak, "width_hz", None), 6),
                _format_number(getattr(peak, "area", None), 6),
                _format_number(getattr(peak, "snr", None), 6),
            ],
        )
    return table


def _readonly_table(headers: list[str], rows: int) -> QTableWidget:
    table = QTableWidget(rows, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    return table


def _set_row(table: QTableWidget, row: int, values: Sequence[str]) -> None:
    for column, value in enumerate(values):
        table.setItem(row, column, QTableWidgetItem(value))


def _method_label(match: Any) -> str:
    return "Peak-based" if has_peak_diagnostics(match) else "Legacy cosine"


def _bounded_rows(values: Any) -> tuple[Sequence[Any], int]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return (), 0
    total = len(values)
    return values[:MAX_DETAIL_TABLE_ROWS], total


def _tab_label(label: str, displayed: int, total: int) -> str:
    count = str(total) if displayed == total else f"{displayed}/{total}"
    return f"{label} ({count})"


def _format_percent(value: Any) -> str:
    numeric_value = _finite_number(value)
    if numeric_value is None:
        return "n/a"
    return f"{max(0.0, min(1.0, numeric_value)) * 100:.1f}%"


def _format_number(value: Any, precision: int) -> str:
    numeric_value = _finite_number(value)
    return "n/a" if numeric_value is None else f"{numeric_value:.{precision}f}"


def _finite_number(value: Any) -> float | None:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    return numeric_value if math.isfinite(numeric_value) else None


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _safe_text(value: Any, maximum: int = MAX_DISPLAY_TEXT) -> str:
    text = _CONTROL_CHARACTERS.sub(" ", str("" if value is None else value))
    return " ".join(text.split())[:maximum]
