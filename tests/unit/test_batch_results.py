from __future__ import annotations

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
    dialog.close()
