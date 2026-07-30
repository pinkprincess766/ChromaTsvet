from types import SimpleNamespace
from unittest.mock import patch

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

import python_analyzer.main as main
from python_analyzer.analysis.manual_peaks import editable_peak_from_values
from python_analyzer.analysis.peak_review import PEAK_REVIEW_MANUAL


class RecordingIdentifier:
    def __init__(self):
        self.peak_match_calls = []

    def find_matches(self, spectrum):
        return []

    def find_peak_matches(self, unknown_peaks, frequency_tolerance=5.0, data_type=None):
        self.peak_match_calls.append(list(unknown_peaks))
        return []

    def add_reference(self, name, intensities, formula, peaks=None, data_type="generic"):
        return True

    def clear_database(self):
        return True

    def restore_default(self):
        return True

    def list_references(self):
        return []

    def delete_reference(self, reference_id):
        return True


class FakePeakDialog:
    next_values = {
        "frequency": 12.5,
        "position": 3.0,
        "intensity": 0.75,
        "width": 2.0,
        "width_hz": 1.0,
        "area": 1.5,
        "snr": 9.0,
    }
    last_peak = None

    def __init__(self, parent=None, *, peak=None, title="Peak"):
        self.parent = parent
        self.title = title
        FakePeakDialog.last_peak = peak

    def exec(self):
        return QDialog.Accepted

    def values(self):
        return dict(FakePeakDialog.next_values)


def make_window_with_analysis():
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat,
        QSettings.UserScope,
        "/tmp/chromatsvet-manual-peak-tests",
    )
    main.app_settings().clear()
    identifier = RecordingIdentifier()
    process_result = {
        "spectrum": [1.0, 2.0, 0.5],
        "peaks": [
            SimpleNamespace(
                frequency=10.0,
                position=1.0,
                intensity=2.0,
                width=1.5,
                width_hz=0.5,
                area=2.2,
                snr=12.0,
            )
        ],
        "sample_rate": 1000.0,
    }
    identifier_patch = patch.object(main, "SpectrumIdentifier", lambda: identifier)
    process_patch = patch.object(
        main.spectrometer_rust,
        "process_signal",
        return_value=process_result,
    )
    identifier_patch.start()
    process_patch.start()
    window = main.MainWindow()
    window.current_data = [0.1, 0.3, 0.8, 0.2]
    window.run_analysis()
    return window, identifier, identifier_patch, process_patch


def test_manual_peak_model_rejects_non_finite_required_values():
    try:
        editable_peak_from_values(
            frequency=float("nan"),
            position=1.0,
            intensity=1.0,
        )
    except ValueError as exc:
        assert "frequency" in str(exc)
    else:
        raise AssertionError("manual peak accepted NaN frequency")


def test_add_manual_peak_updates_result_table_review_and_matching():
    app = QApplication.instance() or QApplication([])
    _ = app
    window, identifier, identifier_patch, process_patch = make_window_with_analysis()
    try:
        with patch("python_analyzer.gui.main_window.PeakEditDialog", FakePeakDialog):
            window.add_manual_peak()

        assert len(window.current_peaks) == 2
        assert window.current_result["peaks"] == window.current_peaks
        assert window.current_peak_reviews[-1].status == PEAK_REVIEW_MANUAL
        assert window.current_peak_reviews[-1].user_modified is True
        assert window.peak_table.item(1, 0).text() == "12.5"
        assert identifier.peak_match_calls[-1][-1].source == "manual"
    finally:
        window.close()
        process_patch.stop()
        identifier_patch.stop()


def test_edit_selected_peak_marks_row_as_manual_edit():
    app = QApplication.instance() or QApplication([])
    _ = app
    window, _identifier, identifier_patch, process_patch = make_window_with_analysis()
    try:
        FakePeakDialog.next_values = {
            "frequency": 22.0,
            "position": 5.0,
            "intensity": 1.25,
            "width": 3.0,
            "width_hz": 1.5,
            "area": 4.0,
            "snr": 11.0,
        }
        window.peak_table.setCurrentCell(0, 0)

        with patch("python_analyzer.gui.main_window.PeakEditDialog", FakePeakDialog):
            window.edit_selected_peak()

        assert FakePeakDialog.last_peak is not None
        assert window.current_peaks[0].frequency == 22.0
        assert window.current_peaks[0].source == "edited"
        assert window.current_peak_reviews[0].status == PEAK_REVIEW_MANUAL
        assert window.current_peak_reviews[0].reason == "edited by user"
        assert window.peak_table.item(0, 0).text() == "22"
    finally:
        window.close()
        process_patch.stop()
        identifier_patch.stop()


def test_remove_selected_peak_updates_result_and_reviews():
    app = QApplication.instance() or QApplication([])
    _ = app
    window, _identifier, identifier_patch, process_patch = make_window_with_analysis()
    try:
        window.peak_table.setCurrentCell(0, 0)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            window.remove_selected_peak()

        assert window.current_peaks == []
        assert window.current_result["peaks"] == []
        assert window.current_peak_reviews == []
        assert window.peak_table.rowCount() == 0
    finally:
        window.close()
        process_patch.stop()
        identifier_patch.stop()
