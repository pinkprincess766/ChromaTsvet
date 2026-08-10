import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QMessageBox

import python_analyzer.main as main
from python_analyzer.analysis.models import AnalysisSettings
from python_analyzer.analysis.peak_review import PEAK_REVIEW_REJECTED, PeakReview
from python_analyzer.analysis.session_bundle import (
    build_analysis_session_payload,
    write_analysis_session,
)
from python_analyzer.core.identification import MatchResult
from tests.support.gui_fakes import FakeIdentifier


class MainWindowSessionActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(
            QSettings.IniFormat,
            QSettings.UserScope,
            "/tmp/chromatsvet-session-action-tests",
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
        self.window.current_data = [0.1, 0.3, 0.8, 0.2]

    def tearDown(self):
        self.window.close()
        self.process_patch.stop()
        self.identifier_patch.stop()

    def test_save_writes_snapshot_without_private_source_path(self):
        self.window.current_file_name = "/Users/scientist/private/sample.csv"
        self.window.run_analysis()

        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "session"
            expected_output = output_path.with_suffix(".chromatsvet-session.json")
            with (
                patch.object(
                    main.QFileDialog,
                    "getSaveFileName",
                    return_value=(
                        str(output_path),
                        "ChromaTsvet Session (*.chromatsvet-session.json)",
                    ),
                ),
                patch.object(QMessageBox, "information", return_value=QMessageBox.Ok),
            ):
                self.window.save_analysis_session()

            self.assertTrue(expected_output.is_file())
            payload_text = expected_output.read_text(encoding="utf-8")
            payload = json.loads(payload_text)

        self.assertEqual(payload["source"]["file_name"], "sample.csv")
        self.assertNotIn("/Users/scientist/private", payload_text)
        self.assertIn("Analysis session saved:", self.window.log_history[-1])

    def test_load_restores_snapshot_without_rerunning_analysis(self):
        peak = SimpleNamespace(
            frequency=125.0,
            position=250.0,
            intensity=0.9,
            width=3.0,
            width_hz=1.5,
            area=2.7,
            snr=14.0,
        )
        payload = build_analysis_session_payload(
            source_file_name="/Users/scientist/private/session_source.csv",
            data_points_count=512,
            settings=AnalysisSettings(
                sample_rate=2000.0,
                filter_type="none",
                filter_params={},
                baseline_enabled=True,
                baseline_method="improved",
                peak_threshold=0.02,
                peak_prominence=0.3,
                peak_distance=4,
                normalize_area=True,
                peak_min_snr=5.0,
                window_type="hann",
                spectrum_smoothing_enabled=True,
                spectrum_smoothing_method="median",
                spectrum_smoothing_window=9,
                peak_frequency_tolerance=2.5,
                data_type="raman",
            ),
            method_name="Raman QC",
            result={
                "spectrum": [0.0, 1.0, 0.25],
                "frequency_axis": [0.0, 50.0, 100.0],
                "sample_rate": 2000.0,
                "normalized": True,
            },
            frequency_axis=[0.0, 50.0, 100.0],
            spectrum=[0.0, 1.0, 0.25],
            peaks=[peak],
            peak_reviews=[
                PeakReview(
                    PEAK_REVIEW_REJECTED,
                    "rejected by user",
                    user_modified=True,
                )
            ],
            matches=[
                MatchResult(
                    substance_name="Reference",
                    formula="R",
                    score=0.91,
                    compared_points=1,
                )
            ],
            app_version="0.2.0",
            rust_core_version="0.1.0",
        )

        with TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "session.chromatsvet-session.json"
            write_analysis_session(session_path, payload)
            self.process_signal.reset_mock()

            with (
                patch.object(
                    main.QFileDialog,
                    "getOpenFileName",
                    return_value=(
                        str(session_path),
                        "ChromaTsvet Session (*.chromatsvet-session.json)",
                    ),
                ),
                patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok),
            ):
                self.window.open_analysis_session_file()

        self.process_signal.assert_not_called()
        self.assertIsNone(self.window.current_data)
        self.assertEqual(self.window.current_data_points_count, 512)
        self.assertEqual(self.window.current_file_name, "session_source.csv")
        self.assertEqual(self.window.sample_rate, 2000.0)
        self.assertEqual(self.window.data_type, "raman")
        self.assertEqual(self.window.peak_table.rowCount(), 1)
        self.assertEqual(self.window.table.rowCount(), 1)
        self.assertEqual(self.window.peak_table.item(0, 8).text(), "rejected by user")
        self.assertEqual(self.window.table.item(0, 0).text(), "Reference")
        self.assertIn("session loaded", self.window.status_details_label.text())
        self.assertNotIn("/Users/scientist/private", "\n".join(self.window.log_history))


if __name__ == "__main__":
    unittest.main()
