"""Unit tests for the spectrum reader module.

These tests focus purely on file parsing logic and are independent
of the GUI (MainWindow).
"""

import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from python_analyzer.readers import (
    read_spectrum_file,
    SpectrumFileFormatError,
)


class SpectrumReaderTest(unittest.TestCase):
    def test_non_finite_file_values_are_skipped(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "spectrum.txt"
            file_path.write_text("intensity\nnan\ninf\n1.25\n", encoding="utf-8")

            data, skipped_rows = read_spectrum_file(file_path)

        self.assertEqual(data, [1.25])
        self.assertEqual(skipped_rows, [(2, "nan"), (3, "inf")])

    def test_keeps_legacy_single_column_files(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "spectrum.txt"
            file_path.write_text("0.1\n0.3\n1.25\n", encoding="utf-8")

            data, skipped_rows = read_spectrum_file(file_path)

        self.assertEqual(data, [0.1, 0.3, 1.25])
        self.assertEqual(skipped_rows, [])

    def test_reads_named_intensity_column_from_comma_csv(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "spectrum.csv"
            file_path.write_text(
                "wavelength,intensity\n400,1.5\n401,2.75\n",
                encoding="utf-8",
            )

            data, skipped_rows = read_spectrum_file(file_path)

        self.assertEqual(data, [1.5, 2.75])
        self.assertEqual(skipped_rows, [])

    def test_reads_tab_delimited_named_intensity_column(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "spectrum.txt"
            file_path.write_text(
                "time\tsignal\n0\t2.5\n1\t3.5\n",
                encoding="utf-8",
            )

            data, skipped_rows = read_spectrum_file(file_path)

        self.assertEqual(data, [2.5, 3.5])
        self.assertEqual(skipped_rows, [])

    def test_reads_semicolon_file_with_decimal_commas(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "spectrum.csv"
            file_path.write_text(
                "wavelength;intensity\n400,0;1,25\n401,0;2,50\n",
                encoding="utf-8",
            )

            data, skipped_rows = read_spectrum_file(file_path)

        self.assertEqual(data, [1.25, 2.5])
        self.assertEqual(skipped_rows, [])

    def test_reads_single_column_decimal_commas_with_header(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "spectrum.txt"
            file_path.write_text(
                "intensity\n1,25\n2,50\n",
                encoding="utf-8",
            )

            data, skipped_rows = read_spectrum_file(file_path)

        self.assertEqual(data, [1.25, 2.5])
        self.assertEqual(skipped_rows, [])

    def test_uses_second_column_for_headerless_two_column_table(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "spectrum.txt"
            file_path.write_text("0\t5.0\n1\t7.5\n", encoding="utf-8")

            data, skipped_rows = read_spectrum_file(file_path)

        self.assertEqual(data, [5.0, 7.5])
        self.assertEqual(skipped_rows, [])

    def test_rejects_inconsistent_column_counts(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "broken.csv"
            file_path.write_text(
                "position;intensity\n0;1.0\n1;2.0;unexpected\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SpectrumFileFormatError, "3 columns"):
                read_spectrum_file(file_path)

    def test_rejects_table_without_intensity_column(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "ambiguous.csv"
            file_path.write_text(
                "wavelength,temperature\n400,20\n401,21\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                SpectrumFileFormatError, "Could not identify"
            ):
                read_spectrum_file(file_path)

    def test_rejects_malformed_csv_quotes(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "broken.csv"
            file_path.write_text(
                'position,intensity\n0,"1.0\n',
                encoding="utf-8",
            )

            with self.assertRaises(csv.Error):
                read_spectrum_file(file_path)
