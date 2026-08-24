"""Qt presentation for compact batch-analysis results."""

from __future__ import annotations

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from python_analyzer.analysis.batch import (
    BATCH_STATUS_SUCCESS,
    BatchAnalysisItem,
    BatchAnalysisSummary,
)


class BatchResultsDialog(QDialog):
    """Display one immutable summary row per selected spectrum file."""

    COLUMN_LABELS = (
        "File",
        "Status",
        "Points",
        "Peaks",
        "Warnings",
        "Skipped rows",
        "Details",
    )

    def __init__(self, parent, summary: BatchAnalysisSummary):
        super().__init__(parent)
        self.setWindowTitle("Batch Analysis Results")
        self.resize(920, 460)

        layout = QVBoxLayout(self)
        state = "cancelled" if summary.cancelled else "complete"
        self.summary_label = QLabel(
            f"Batch {state}: {summary.successful_count} successful, "
            f"{summary.failed_count} failed, "
            f"{len(summary.items)} of {summary.requested_count} processed."
        )
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(len(summary.items), len(self.COLUMN_LABELS), self)
        self.table.setHorizontalHeaderLabels(self.COLUMN_LABELS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAccessibleName("Batch analysis results")

        for row, item in enumerate(summary.items):
            self._set_result_row(row, item)
        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_result_row(self, row: int, item: BatchAnalysisItem) -> None:
        successful = item.status == BATCH_STATUS_SUCCESS
        status_text = "Success" if successful else "Failed"
        values = (
            item.source_name,
            status_text,
            str(item.point_count) if successful else "",
            str(item.peak_count) if successful else "",
            str(item.warning_count) if successful else "",
            str(item.skipped_row_count) if successful else "",
            item.error_message,
        )
        status_color = QColor("#2e7d32" if successful else "#b3261e")
        for column, value in enumerate(values):
            table_item = QTableWidgetItem(value)
            if column == 1:
                table_item.setForeground(status_color)
            self.table.setItem(row, column, table_item)
