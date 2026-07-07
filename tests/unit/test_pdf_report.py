from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from PIL import Image

from python_analyzer.exporters.pdf_report import (
    PDFMatchRow,
    PDFReportData,
    PDFReportExporter,
)


class PDFReportExporterTest(unittest.TestCase):
    def test_exporter_writes_pdf_from_prepared_report_data(self):
        peak = SimpleNamespace(
            frequency=120.5,
            position=42.0,
            intensity=0.84,
            width=3.2,
            width_hz=1.6,
            area=2.4,
            snr=18.0,
        )
        report_data = PDFReportData(
            title="ChromaTsvet Analysis Report",
            subtitle="Spectral data and chromatogram analysis",
            summary_rows=[
                ("Date", "2026-07-01 21:59"),
                ("App version", "0.2.0"),
                ("Source file", "sample.csv"),
                ("Data points", "128"),
                ("Peaks found", "1"),
            ],
            parameter_rows=[
                ("Sample rate", "1000 Hz"),
                ("Baseline", "improved"),
                ("Normalization", "disabled"),
            ],
            peaks=[peak],
            matches=[
                PDFMatchRow(
                    substance_name="Reference",
                    formula="R",
                    score="0.900",
                    compared_points="1",
                )
            ],
            source_file_name="sample.csv",
            data_points_count=128,
            peaks_count=1,
        )

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "report.pdf"
            plot_path = temp_path / "plot.png"
            Image.new("RGB", (320, 180), "white").save(plot_path)

            PDFReportExporter().export(
                output_path,
                report_data,
                plot_image_path=plot_path,
            )

            self.assertTrue(output_path.is_file())
            self.assertGreater(output_path.stat().st_size, 0)
            with output_path.open("rb") as pdf_file:
                self.assertEqual(pdf_file.read(4), b"%PDF")

    def test_exporter_rejects_missing_plot_image_path(self):
        report_data = PDFReportData(
            title="ChromaTsvet Analysis Report",
            subtitle="Spectral data and chromatogram analysis",
            summary_rows=[],
            parameter_rows=[],
            peaks=[],
            matches=[],
            source_file_name="sample.csv",
            data_points_count=0,
            peaks_count=0,
        )

        with TemporaryDirectory() as temp_dir:
            missing_plot = Path(temp_dir) / "missing.png"
            output_path = Path(temp_dir) / "report.pdf"

            with self.assertRaises(FileNotFoundError) as error_context:
                PDFReportExporter().export(
                    output_path,
                    report_data,
                    plot_image_path=missing_plot,
                )
            self.assertNotIn(temp_dir, str(error_context.exception))


if __name__ == "__main__":
    unittest.main()
