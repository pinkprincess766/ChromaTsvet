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
from python_analyzer.exporters import (
    write_batch_detail_archive,
    write_batch_summary_csv,
    write_batch_summary_excel,
)
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
        self.export_csv_button = buttons.addButton(
            "Export CSV...",
            QDialogButtonBox.ActionRole,
        )
        self.export_excel_button = buttons.addButton(
            "Export Excel...",
            QDialogButtonBox.ActionRole,
        )
        self.export_csv_button.clicked.connect(self.export_csv)
        self.export_excel_button.clicked.connect(self.export_excel)
        self.export_details_button.clicked.connect(self.export_details_archive)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def export_details_archive(self) -> None:
        self._export_result(
            title="Export detailed batch results",
            default_name="batch-analysis-details.zip",
            file_filter="ZIP Archive (*.zip)",
            suffix=".zip",
            writer=write_batch_detail_archive,
            log_label="Detailed batch archive",
            success_message="Detailed batch results were exported as a ZIP archive.",
            failure_subject="detailed batch archive",
        )

    def export_csv(self) -> None:
        self._export_result(
            title="Export batch summary as CSV",
            default_name="batch-analysis-summary.csv",
            file_filter="CSV (*.csv)",
            suffix=".csv",
            writer=write_batch_summary_csv,
            log_label="Batch summary CSV",
            success_message="Batch summary exported as CSV.",
            failure_subject="batch summary",
        )

    def export_excel(self) -> None:
        self._export_result(
            title="Export batch summary as Excel",
            default_name="batch-analysis-summary.xlsx",
            file_filter="Excel Workbook (*.xlsx)",
            suffix=".xlsx",
            writer=write_batch_summary_excel,
            log_label="Batch summary XLSX",
            success_message="Batch summary exported as XLSX.",
            failure_subject="batch summary",
        )

    def _export_result(
        self,
        *,
        title: str,
        default_name: str,
        file_filter: str,
        suffix: str,
        writer,
        log_label: str,
        success_message: str,
        failure_subject: str,
    ) -> None:
        suggested_path = (
            suggested_dialog_path(self.settings, default_name)
            if self.settings is not None
            else default_name
        )
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            title,
            suggested_path,
            file_filter,
        )
        if not selected_path:
            return

        output_path = Path(selected_path)
        if output_path.suffix.casefold() != suffix:
            output_path = output_path.with_suffix(suffix)

        try:
            writer(output_path, self.summary)
        except Exception as exc:
            self._log_export_event(
                f"{log_label} export failed ({type(exc).__name__})",
                level="error",
            )
            QMessageBox.warning(
                self,
                "Export failed",
                f"The {failure_subject} could not be written. Choose a "
                "writable folder and try again.",
            )
            return

        if self.settings is not None:
            remember_last_directory(self.settings, output_path)
        self._log_export_event(f"{log_label} exported")
        QMessageBox.information(
            self,
            "Export complete",
            success_message,
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
