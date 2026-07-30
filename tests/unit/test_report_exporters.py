from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from openpyxl import load_workbook
from PIL import Image

from python_analyzer.exporters import (
    ExcelReportExporter,
    HTMLReportExporter,
    PDFMatchRow,
    PDFReportData,
)


def sample_report_data():
    peak = SimpleNamespace(
        frequency=120.5,
        position=42.0,
        intensity=0.84,
        width=3.2,
        width_hz=1.6,
        area=2.4,
        snr=18.0,
    )
    return PDFReportData(
        title="ChromaTsvet <Analysis> Report",
        subtitle="Spectral data and chromatogram analysis",
        summary_rows=[
            ("Source file", "sample.csv"),
            ("Data points", "128"),
            ("Peaks found", "1"),
        ],
        parameter_rows=[
            ("Sample rate", "1000 Hz"),
            ("Baseline", "improved"),
            ("Normalization", "disabled"),
        ],
        processing_passport_rows=[
            ("Generated at", "2026-07-24 12:30:00"),
            ("Analysis method", "Raman QC"),
            ("Processing warnings", "none"),
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


class ReportExportersTest(unittest.TestCase):
    def test_html_report_contains_escaped_report_content_and_embedded_plot(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "report.html"
            plot_path = temp_path / "plot.png"
            Image.new("RGB", (160, 90), "white").save(plot_path)

            HTMLReportExporter().export(
                output_path,
                sample_report_data(),
                plot_image_path=plot_path,
            )

            html = output_path.read_text(encoding="utf-8")

        self.assertIn("ChromaTsvet &lt;Analysis&gt; Report", html)
        self.assertIn("sample.csv", html)
        self.assertIn("Processing Passport", html)
        self.assertIn("Raman QC", html)
        self.assertIn("Reference", html)
        self.assertIn("120.5", html)
        self.assertIn("data:image/png;base64,", html)

    def test_html_report_rejects_missing_plot_without_path_leak(self):
        with TemporaryDirectory() as temp_dir:
            missing_plot = Path(temp_dir) / "missing.png"
            output_path = Path(temp_dir) / "report.html"

            with self.assertRaises(FileNotFoundError) as error_context:
                HTMLReportExporter().export(
                    output_path,
                    sample_report_data(),
                    plot_image_path=missing_plot,
                )

            self.assertNotIn(temp_dir, str(error_context.exception))
            self.assertFalse(output_path.exists())

    def test_excel_report_writes_expected_sheets_and_cells(self):
        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "report.xlsx"

            ExcelReportExporter().export(output_path, sample_report_data())

            workbook = load_workbook(output_path, data_only=True)

        self.assertEqual(
            workbook.sheetnames,
            ["Summary", "Parameters", "Processing Passport", "Peaks", "Matches"],
        )
        self.assertEqual(workbook["Summary"]["A2"].value, "Source file")
        self.assertEqual(workbook["Summary"]["B2"].value, "sample.csv")
        self.assertEqual(workbook["Parameters"]["A2"].value, "Sample rate")
        self.assertEqual(
            workbook["Processing Passport"]["A3"].value,
            "Analysis method",
        )
        self.assertEqual(workbook["Processing Passport"]["B3"].value, "Raman QC")
        self.assertEqual(workbook["Peaks"]["A2"].value, 120.5)
        self.assertEqual(workbook["Peaks"]["G2"].value, 18.0)
        self.assertEqual(workbook["Matches"]["A2"].value, "Reference")
        self.assertEqual(workbook["Matches"]["C2"].value, "0.900")


if __name__ == "__main__":
    unittest.main()
