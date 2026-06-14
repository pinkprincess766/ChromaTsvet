import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QMessageBox

import python_analyzer.main as main
from python_analyzer.core.identification import SpectrumIdentifier


class FakeIdentifier:
    def find_matches(self, spectrum):
        return []

    def add_reference(self, name, intensities, formula):
        return True

    def clear_database(self):
        return True

    def restore_default(self):
        return True


class MainWindowErrorHandlingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(
            QSettings.IniFormat,
            QSettings.UserScope,
            "/tmp/chromatsvet-error-handling-tests",
        )

    def setUp(self):
        main.app_settings().clear()
        self.identifier_patch = patch.object(main, "SpectrumIdentifier", FakeIdentifier)
        self.process_patch = patch.object(
            main.spectrometer_rust,
            "process_signal",
            return_value={"spectrum": [1.0, 2.0], "peaks": []},
        )
        self.identifier_patch.start()
        self.process_signal = self.process_patch.start()
        self.window = main.MainWindow()

    def tearDown(self):
        self.window.close()
        self.process_patch.stop()
        self.identifier_patch.stop()

    def test_log_levels_are_prefixed_and_colored(self):
        self.window.log("Warning entry", level="warning")
        self.window.log("Error entry", level="error")

        self.assertIn("[WARN] Warning entry", self.window.log_history[-2])
        self.assertIn("[ERROR] Error entry", self.window.log_history[-1])
        self.assertIn("Application started", self.window.embedded_log_view.toPlainText())

        embedded_html = self.window.embedded_log_view.toHtml().lower()
        self.assertIn("#f5a623", embedded_html)
        self.assertIn("#ff5c5c", embedded_html)

        log_window = main.LogWindow(self.window)
        html = log_window.log_view.toHtml().lower()
        self.assertIn("#f5a623", html)
        self.assertIn("#ff5c5c", html)
        log_window.close()

    def test_embedded_log_copy_and_clear_controls(self):
        self.window.log("Copy this entry")

        self.window.log_copy_button.click()
        self.assertEqual(
            QApplication.clipboard().text(),
            self.window.embedded_log_view.toPlainText(),
        )

        self.window.log_clear_button.click()
        self.assertEqual(self.window.log_history, [])
        self.assertEqual(self.window.embedded_log_view.toPlainText(), "")

    def test_analysis_failure_is_reported_without_raising(self):
        self.process_signal.side_effect = RuntimeError("Rust failure")

        with patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok) as critical:
            self.window.run_analysis()

        critical.assert_called_once()
        self.assertIn("[ERROR]", self.window.log_history[-1])
        self.assertIn("RuntimeError: Rust failure", self.window.log_history[-1])
        self.assertEqual(self.window.status_bar.currentMessage(), "Spectrum analysis failed")

    def test_file_read_failure_is_reported_without_raising(self):
        missing_file = "/tmp/chromatsvet-file-that-does-not-exist.csv"

        with (
            patch.object(main.QFileDialog, "getOpenFileName", return_value=(missing_file, "")),
            patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok) as warning,
        ):
            self.window.load_file()

        warning.assert_called_once()
        self.assertIn("[ERROR]", self.window.log_history[-1])
        self.assertIn("FileNotFoundError", self.window.log_history[-1])

    def test_invalid_substance_input_is_reported(self):
        answers = [("Test", True), ("T", True), ("1,,2", True)]

        with (
            patch.object(main.QInputDialog, "getText", side_effect=answers),
            patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok) as warning,
        ):
            self.window.add_substance()

        warning.assert_called_once()
        self.assertIn("[ERROR]", self.window.log_history[-1])
        self.assertIn("intensity values cannot be empty", self.window.log_history[-1])

    def test_non_finite_file_values_are_rejected_by_parser(self):
        self.assertIsNone(self.window._parse_number("nan"))
        self.assertIsNone(self.window._parse_number("inf"))
        self.assertEqual(self.window._parse_number("1,25"), 1.25)

    def test_database_failure_is_reported(self):
        self.window.identifier.clear_database = lambda: False

        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.Yes),
            patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok) as critical,
        ):
            self.window.clear_database()

        critical.assert_called_once()
        self.assertIn("[ERROR]", self.window.log_history[-1])
        self.assertIn("RuntimeError", self.window.log_history[-1])

    def test_pdf_permission_failure_is_reported(self):
        with (
            patch.object(
                main.QFileDialog,
                "getSaveFileName",
                return_value=("/restricted/report.pdf", ""),
            ),
            patch.object(
                main.tempfile,
                "NamedTemporaryFile",
                side_effect=PermissionError("access denied"),
            ),
            patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok) as warning,
        ):
            self.window.export_pdf()

        warning.assert_called_once()
        self.assertIn("[ERROR]", self.window.log_history[-1])
        self.assertIn("PermissionError: access denied", self.window.log_history[-1])

    def test_peak_export_is_disabled_without_detected_peaks(self):
        self.assertFalse(self.window.btn_export_peaks.isEnabled())

        with (
            patch.object(main.QFileDialog, "getSaveFileName") as save_dialog,
            patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok) as warning,
        ):
            self.window.export_peaks_csv()

        warning.assert_called_once()
        save_dialog.assert_not_called()
        self.assertIn("[WARN]", self.window.log_history[-1])

    def test_peak_export_writes_csv_and_updates_log(self):
        peak = SimpleNamespace(
            position=124.0,
            intensity=0.854,
            width=12.3,
            area=4.21,
            snr=18.7,
        )
        self.process_signal.return_value = {"spectrum": [0.0, 1.0], "peaks": [peak]}
        self.window.run_analysis()
        self.assertTrue(self.window.btn_export_peaks.isEnabled())

        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "peaks.csv"
            with (
                patch.object(
                    main.QFileDialog,
                    "getSaveFileName",
                    return_value=(str(output_path), "CSV (*.csv)"),
                ),
                patch.object(QMessageBox, "information", return_value=QMessageBox.Ok),
            ):
                self.window.export_peaks_csv()

            with output_path.open(newline="", encoding="utf-8") as csv_file:
                rows = list(csv.reader(csv_file))

        self.assertEqual(rows[0], ["position", "intensity", "width", "area", "snr"])
        self.assertEqual(rows[1], ["124.0", "0.854", "12.3", "4.21", "18.7"])
        self.assertIn("Peak list exported:", self.window.log_history[-1])

    def test_identification_table_uses_matched_points(self):
        self.window.identifier.find_matches = lambda spectrum: [
            SimpleNamespace(
                substance_name="Test",
                formula="T",
                score=0.75,
                matched_points=2,
            )
        ]

        self.window.run_analysis()

        self.assertEqual(self.window.table.horizontalHeaderItem(3).text(), "Matched points")
        self.assertEqual(self.window.table.item(0, 3).text(), "2")


class IdentifierErrorPropagationTest(unittest.TestCase):
    def test_find_matches_reports_compared_points(self):
        identifier = SpectrumIdentifier(":memory:")
        try:
            identifier.add_reference("Reference", [1.0, 2.0, 3.0], "R")
            matches = identifier.find_matches(np.array([1.0, 2.0, 3.0, 4.0]))
        finally:
            identifier.conn.close()

        self.assertEqual(matches[0].matched_points, 3)
        self.assertFalse(hasattr(matches[0], "matched_peaks"))

    def test_restore_default_propagates_clear_failure(self):
        identifier = SpectrumIdentifier.__new__(SpectrumIdentifier)
        identifier.clear_database = lambda: False
        identifier.add_reference = lambda *args: self.fail("add_reference must not run")

        self.assertFalse(identifier.restore_default())

    def test_restore_default_propagates_add_failure(self):
        identifier = SpectrumIdentifier.__new__(SpectrumIdentifier)
        identifier.clear_database = lambda: True
        identifier.add_reference = lambda *args: False
        identifier.log = lambda message: None

        self.assertFalse(identifier.restore_default())


if __name__ == "__main__":
    unittest.main()
