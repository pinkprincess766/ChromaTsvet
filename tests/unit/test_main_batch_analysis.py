from __future__ import annotations

from unittest.mock import Mock, patch

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QProgressDialog

import python_analyzer.main as main
from python_analyzer.analysis.batch import BatchAnalysisSummary
from python_analyzer.gui import main_window as main_window_module
from python_analyzer.gui.recent_files import load_last_directory
from tests.support.gui_fakes import FakeIdentifier


def test_main_window_batch_action_wires_selection_to_headless_runner(qapp, tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat,
        QSettings.UserScope,
        str(tmp_path / "settings"),
    )
    main.app_settings().clear()
    source = tmp_path / "sample.csv"
    source.write_text("intensity\n0.1\n0.5\n0.2\n", encoding="utf-8")
    summary = BatchAnalysisSummary(items=(), requested_count=1)
    progress = QProgressDialog()
    results_dialog = Mock()

    with (
        patch.object(main, "SpectrumIdentifier", FakeIdentifier),
        patch.object(
            main.spectrometer_rust,
            "process_signal",
            return_value={"spectrum": [1.0], "peaks": []},
        ),
        patch.object(
            main_window_module.QFileDialog,
            "getOpenFileNames",
            return_value=([str(source)], "Spectrum files (*.csv *.txt)"),
        ),
        patch.object(
            main_window_module,
            "analyze_spectrum_files",
            return_value=summary,
        ) as analyze_batch,
        patch.object(main_window_module, "QProgressDialog", return_value=progress),
        patch.object(
            main_window_module,
            "BatchResultsDialog",
            return_value=results_dialog,
        ) as dialog_class,
    ):
        window = main.MainWindow()
        try:
            window.run_batch_analysis()
        finally:
            window.close()

    assert window.batch_analysis_action.text() == "Batch Analyze Spectra..."
    assert analyze_batch.call_args.args[0] == [str(source)]
    assert callable(analyze_batch.call_args.kwargs["should_cancel"])
    assert load_last_directory(window.settings) == str(tmp_path)
    assert progress.isVisible() is False
    dialog_class.assert_called_once_with(window, summary)
    results_dialog.exec.assert_called_once()
