"""Shared log-view formatting helpers."""

from __future__ import annotations

from PyQt5.QtGui import QColor, QPalette, QTextCharFormat, QTextCursor


LOG_LEVEL_LABELS = {"info": "INFO", "warning": "WARN", "error": "ERROR"}
LOG_LEVEL_COLORS = {"warning": "#F5A623", "error": "#FF5C5C"}


def log_level_from_entry(entry: str) -> str:
    for level, label in LOG_LEVEL_LABELS.items():
        if f"[{label}]" in entry:
            return level
    return "info"


def append_log_entry(
    log_view,
    entry: str,
    level: str = "info",
    auto_scroll: bool = True,
) -> None:
    """Append one colored entry to any ChromaTsvet log view."""
    scroll_bar = log_view.verticalScrollBar()
    previous_scroll = scroll_bar.value()
    cursor = log_view.textCursor()
    cursor.movePosition(QTextCursor.End)
    if not log_view.document().isEmpty():
        cursor.insertText("\n")

    text_format = QTextCharFormat()
    color = LOG_LEVEL_COLORS.get(level)
    text_format.setForeground(
        QColor(color) if color else log_view.palette().color(QPalette.Text)
    )
    cursor.insertText(entry, text_format)
    log_view.setTextCursor(cursor)
    if auto_scroll:
        log_view.ensureCursorVisible()
    else:
        scroll_bar.setValue(previous_scroll)
