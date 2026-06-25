#!/usr/bin/env python3
"""Capture deterministic ChromaTsvet v0.1 release screenshots."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = PROJECT_ROOT / "docs" / "screenshots"
REPORT_PATH = PROJECT_ROOT / "output" / "pdf" / "chromatsvet-v0.1-demo-report.pdf"
PDF_PREVIEW_PATH = SCREENSHOT_DIR / "04-pdf-report.png"

sys.path.insert(0, str(PROJECT_ROOT))

from python_analyzer import main  # noqa: E402


def demo_signal(sample_rate: float, point_count: int = 2048) -> np.ndarray:
    """Return a stable time-domain signal with three spectral components."""
    time = np.arange(point_count, dtype=float) / sample_rate
    rng = np.random.default_rng(42)
    return (
        1.00 * np.sin(2.0 * np.pi * 95.0 * time)
        + 0.72 * np.sin(2.0 * np.pi * 240.0 * time + 0.35)
        + 0.46 * np.sin(2.0 * np.pi * 410.0 * time + 0.80)
        + 0.025 * rng.standard_normal(point_count)
    )


def save_widget(widget, file_name: str) -> None:
    QApplication.processEvents()
    destination = SCREENSHOT_DIR / file_name
    pixmap = widget.grab()
    if pixmap.isNull() or not pixmap.save(str(destination), "PNG"):
        raise RuntimeError(f"Could not capture {destination}")


def save_pdf_preview() -> None:
    """Render the first PDF page as the README preview image."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        pdfium = None

    if pdfium is not None:
        pdf = pdfium.PdfDocument(str(REPORT_PATH))
        image = pdf[0].render(scale=2.1).to_pil()
        image.save(PDF_PREVIEW_PATH, "PNG", optimize=True)
        return

    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm is not None:
        output_prefix = PDF_PREVIEW_PATH.with_suffix("")
        subprocess.run(
            [
                pdftoppm,
                "-png",
                "-singlefile",
                "-r",
                "151",
                str(REPORT_PATH),
                str(output_prefix),
            ],
            check=True,
        )
        return

    if PDF_PREVIEW_PATH.exists():
        print(
            "Keeping existing 04-pdf-report.png; install pypdfium2 or Poppler "
            "to regenerate the PDF preview."
        )
        return

    raise RuntimeError(
        "Install pypdfium2 or Poppler to render docs/screenshots/04-pdf-report.png"
    )


def main_capture() -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    settings_dir = Path(tempfile.mkdtemp(prefix="chromatsvet-release-settings-"))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(settings_dir))

    QApplication.setAttribute(Qt.AA_Use96Dpi, True)
    app = QApplication.instance() or QApplication(sys.argv[:1])

    window = main.MainWindow()
    window.theme = "light"
    window.font_size = 11
    main.apply_app_theme(app, window.theme, window.font_family, window.font_size)

    window.sample_rate = 2048.0
    window.baseline_enabled = True
    window.baseline_method = "improved"
    window.filter_type = "none"
    window.filter_params = {}
    window.normalize_area = False
    window.peak_threshold = 0.025
    window.peak_prominence = 0.02
    window.peak_distance = 30
    window.current_data = demo_signal(window.sample_rate).tolist()
    window.current_file_name = "reference_mixture_v01.csv"
    window.current_file_path = f"data/{window.current_file_name}"
    window._update_file_display()
    window.run_analysis()

    window.resize(1700, 950)
    window.show()
    QApplication.processEvents()
    save_widget(window, "01-main-spectrum.png")

    settings_dialog = main.AnalysisSettingsDialog(window)
    settings_dialog.resize(620, 820)
    settings_dialog.show()
    QApplication.processEvents()
    save_widget(settings_dialog, "02-analysis-settings.png")
    settings_dialog.close()

    window.results_tabs.setCurrentIndex(0)
    window.log_panel.hide()
    window.plot.setMaximumHeight(430)
    window.results_tabs.setMinimumHeight(330)
    window.resize(1600, 900)
    QApplication.processEvents()
    save_widget(window, "03-peaks-table.png")

    with (
        patch.object(
            main.QFileDialog,
            "getSaveFileName",
            return_value=(str(REPORT_PATH), "PDF (*.pdf)"),
        ),
        patch.object(main.QMessageBox, "information", return_value=main.QMessageBox.Ok),
    ):
        window.export_pdf()
    save_pdf_preview()

    window.close()
    app.processEvents()


if __name__ == "__main__":
    main_capture()
