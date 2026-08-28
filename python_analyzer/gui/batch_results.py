"""Qt presentation for compact batch-analysis results."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from python_analyzer.analysis.batch import (
    BATCH_STATUS_SUCCESS,
    BatchAnalysisItem,
    BatchAnalysisSummary,
)
from python_analyzer.exporters import write_batch_detail_archive
from python_analyzer.gui.recent_files import (
    remember_last_directory,
    suggested_dialog_path,
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

    def __init__(self, parent, summary: BatchAnalysisSummary, *, settings=None):
        super().__init__(parent)
        self.summary = summary
        self.settings = settings
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
        self.export_details_button = buttons.addButton(
            "Export Details ZIP...",
            QDialogButtonBox.ActionRole,
        )
        self.export_details_button.clicked.connect(self.export_details_archive)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def export_details_archive(self) -> None:
        suggested_path = (
            suggested_dialog_path(self.settings, "batch-analysis-details.zip")
            if self.settings is not None
            else "batch-analysis-details.zip"
        )
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export detailed batch results",
            suggested_path,
            "ZIP Archive (*.zip)",
        )
        if not selected_path:
            return

        output_path = Path(selected_path)
        if output_path.suffix.casefold() != ".zip":
            output_path = output_path.with_suffix(".zip")

        try:
            write_batch_detail_archive(output_path, self.summary)
        except Exception as exc:
            self._log_export_event(
                f"Detailed batch export failed ({type(exc).__name__})",
                level="error",
            )
            QMessageBox.warning(
                self,
                "Export failed",
                "The detailed batch archive could not be written. Choose a "
                "writable folder and try again.",
            )
            return

        if self.settings is not None:
            remember_last_directory(self.settings, output_path)
        self._log_export_event("Detailed batch archive exported")
        QMessageBox.information(
            self,
            "Export complete",
            "Detailed batch results were exported as a ZIP archive.",
        )

    def _log_export_event(self, message: str, *, level: str = "info") -> None:
        parent = self.parent()
        log_method = getattr(parent, "log", None)
        if callable(log_method):
            log_method(message, level=level)

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
