"""Reusable GUI-test fakes for MainWindow-facing tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


class FakeIdentifier:
    def find_matches(self, spectrum):
        return []

    def find_peak_matches(self, unknown_peaks, frequency_tolerance=5.0, data_type=None):
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


class FakeGraphExporter:
    payload = b"graph-export"

    def __init__(self, plot_item):
        self.plot_item = plot_item

    def export(self, file_path):
        Path(file_path).write_bytes(self.payload)


def create_test_plot_image(directory) -> Path:
    plot_path = Path(directory) / "plot.png"
    Image.new("RGB", (320, 180), "white").save(plot_path)
    return plot_path
