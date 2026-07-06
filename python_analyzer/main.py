"""Thin entry point for ChromaTsvet.

Run with:
    python python_analyzer/main.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pyqtgraph as pg
from PyQt5.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import filters
import spectrometer_rust
from python_analyzer.core.identification import SpectrumIdentifier
from python_analyzer.gui import main_window as _main_window
from python_analyzer.gui.dialogs import AnalysisSettingsDialog, LogWindow, SettingsDialog
from python_analyzer.gui.main_window import (
    APP_LOGO_PATH,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_WINDOW_TYPE,
    app_settings,
    saved_bool,
    saved_float,
    saved_font_family,
    saved_font_size,
    saved_theme,
)
from python_analyzer.gui.theme import apply_app_theme
from python_analyzer.readers import SpectrumFileFormatError

# Compatibility exports: tests and small automation scripts historically imported
# these symbols from python_analyzer.main while the implementation was monolithic.
__all__ = [
    "APP_LOGO_PATH",
    "AnalysisSettingsDialog",
    "DEFAULT_SAMPLE_RATE",
    "DEFAULT_WINDOW_TYPE",
    "LogWindow",
    "MainWindow",
    "QApplication",
    "QFileDialog",
    "QInputDialog",
    "QMessageBox",
    "SettingsDialog",
    "SpectrumFileFormatError",
    "SpectrumIdentifier",
    "app_settings",
    "apply_app_theme",
    "filters",
    "pg",
    "run_app",
    "saved_bool",
    "saved_float",
    "saved_font_family",
    "saved_font_size",
    "saved_theme",
    "spectrometer_rust",
    "tempfile",
]


class MainWindow(_main_window.MainWindow):
    """Compatibility facade for the refactored GUI main window.

    Older tests and scripts patch ``python_analyzer.main.SpectrumIdentifier``.
    The real implementation lives in ``gui.main_window`` now, so we copy the
    current facade dependency across immediately before construction.
    """

    def __init__(self, *args, **kwargs):
        _main_window.SpectrumIdentifier = SpectrumIdentifier
        super().__init__(*args, **kwargs)


def run_app() -> None:
    app = QApplication(sys.argv)
    settings = app_settings()
    apply_app_theme(
        app,
        saved_theme(settings),
        saved_font_family(settings),
        saved_font_size(settings),
    )
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
