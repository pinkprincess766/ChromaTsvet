from __future__ import annotations

from unittest.mock import patch

from PyQt5.QtWidgets import QMessageBox

from python_analyzer.analysis.batch import (
    BATCH_STATUS_FAILED,
    BATCH_STATUS_SUCCESS,
    BatchAnalysisItem,
    BatchAnalysisSummary,
)
from python_analyzer.gui.batch_results import BatchResultsDialog


def test_batch_results_dialog_renders_compact_safe_summary(qapp):
    summary = BatchAnalysisSummary(
        items=(
            BatchAnalysisItem(
                source_name="good.csv",
                status=BATCH_STATUS_SUCCESS,
                point_count=12,
                peak_count=3,
                warning_count=1,
                skipped_row_count=2,
            ),
            BatchAnalysisItem(
                source_name="bad.csv",
                status=BATCH_STATUS_FAILED,
                error_message="Unsupported or malformed spectrum data.",
            ),
        ),
        requested_count=3,
        cancelled=True,
    )

    dialog = BatchResultsDialog(None, summary)

    assert "cancelled" in dialog.summary_label.text()
    assert "1 successful" in dialog.summary_label.text()
    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 0).text() == "good.csv"
    assert dialog.table.item(0, 3).text() == "3"
    assert dialog.table.item(1, 1).text() == "Failed"
    assert dialog.table.item(1, 6).text() == "Unsupported or malformed spectrum data."
    assert dialog.export_csv_button.text() == "Export CSV..."
    assert dialog.export_excel_button.text() == "Export Excel..."
    dialog.close()


def test_batch_results_dialog_exports_csv_with_safe_confirmation(qapp, tmp_path):
    summary = BatchAnalysisSummary(items=(), requested_count=0)
    dialog = BatchResultsDialog(None, summary)
    selected_path = tmp_path / "summary-without-suffix"

    with (
        patch(
            "python_analyzer.gui.batch_results.QFileDialog.getSaveFileName",
            return_value=(str(selected_path), "CSV (*.csv)"),
        ),
        patch(
            "python_analyzer.gui.batch_results.write_batch_summary_csv"
        ) as writer,
        patch.object(
            QMessageBox,
            "information",
            return_value=QMessageBox.Ok,
        ) as information,
    ):
        dialog.export_csv()

    writer.assert_called_once_with(selected_path.with_suffix(".csv"), summary)
    assert "CSV" in information.call_args.args[2]
    assert str(tmp_path) not in information.call_args.args[2]
    dialog.close()


def test_batch_results_dialog_masks_export_exception_details(qapp, tmp_path):
    summary = BatchAnalysisSummary(items=(), requested_count=0)
    dialog = BatchResultsDialog(None, summary)
    private_path = "/Users/example/private/export.csv"

    with (
        patch(
            "python_analyzer.gui.batch_results.QFileDialog.getSaveFileName",
            return_value=(str(tmp_path / "summary.csv"), "CSV (*.csv)"),
        ),
        patch(
            "python_analyzer.gui.batch_results.write_batch_summary_csv",
            side_effect=OSError(f"failed at {private_path}"),
        ),
        patch.object(
            QMessageBox,
            "warning",
            return_value=QMessageBox.Ok,
        ) as warning,
    ):
        dialog.export_csv()

    assert private_path not in warning.call_args.args[2]
    assert "writable folder" in warning.call_args.args[2]
    dialog.close()
