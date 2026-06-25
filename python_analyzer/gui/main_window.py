# -*- coding: utf-8 -*-
"""MainWindow class - orchestration layer."""

from __future__ import annotations

import json
import csv
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import filters
import numpy as np
import spectrometer_rust
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QLabel,
    QFileDialog, QHBoxLayout, QMessageBox, QInputDialog, QTextEdit,
    QHeaderView, QDialog, QFormLayout, QComboBox, QDialogButtonBox, QSpinBox,
    QCheckBox, QDoubleSpinBox, QGroupBox, QStatusBar, QTabWidget
)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import (QFont, QColor, QPalette, QFontDatabase, QPixmap,
                         QTextCharFormat, QTextCursor)
import pyqtgraph as pg
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image

from paths import ensure_rust_in_path, get_library_db_path, get_project_root

# Local imports
from python_analyzer.core.identification import SpectrumIdentifier
from python_analyzer.readers import read_spectrum_file, SpectrumFileFormatError
from python_analyzer.analysis.models import AnalysisSettings, LoadedSpectrum
from python_analyzer.analysis.runner import run_analysis as run_analysis_pipeline
from python_analyzer.viz.spectrum_plot import SpectrumPlot
from python_analyzer.gui.dialogs import SettingsDialog, LogWindow, AnalysisSettingsDialog
from python_analyzer.gui.log_view import (
    LOG_LEVEL_LABELS,
    append_log_entry,
    log_level_from_entry,
)
from python_analyzer.gui.theme import FONT_CANDIDATES, apply_app_theme

# Top level constants and functions needed (copied from original for self contained)
APP_ORG = "ChromaTsvet"
APP_NAME = "ChromaTsvet"
APP_VERSION = "0.1.0"
WINDOW_TITLE = "ChromaTsvet — Spectral Data Analysis"
DEFAULT_THEME = "dark"
DEFAULT_FONT_SIZE = 12
DEFAULT_BASELINE_ENABLED = True
DEFAULT_BASELINE_METHOD = "improved"
DEFAULT_SAMPLE_RATE = 1000.0
DEFAULT_WINDOW_TYPE = "hann"
DEFAULT_PEAK_THRESHOLD = 0.05
DEFAULT_PEAK_PROMINENCE = 0.0
DEFAULT_PEAK_DISTANCE = 1
DEFAULT_FILTER_TYPE = "median"
DEFAULT_NORMALIZE_AREA = False
APP_LOGO_PATH = get_project_root() / "assets" / "chromatsvet_logo.png"

# Setup logging (from original)
try:
    from python_analyzer.core.logging_config import setup_logging
except Exception:
    from core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger("chromatsvet.gui")

def app_settings():
    return QSettings(APP_ORG, APP_NAME)

def saved_theme(settings):
    theme = settings.value("ui/theme", DEFAULT_THEME)
    return theme if theme in ("dark", "light") else DEFAULT_THEME

def available_font_family(preferred=None):
    families = set(QFontDatabase().families())
    for family in [preferred] + FONT_CANDIDATES:
        if family and family in families:
            return family
    return QApplication.font().family()

def saved_font_family(settings):
    return available_font_family(settings.value("ui/font_family", None))

def saved_font_size(settings):
    try:
        return max(9, min(16, int(settings.value("ui/font_size", DEFAULT_FONT_SIZE))))
    except (TypeError, ValueError):
        return DEFAULT_FONT_SIZE

def saved_bool(settings, key, default):
    value = settings.value(key, default)
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("1", "true", "yes", "on")

def saved_float(settings, key, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, float(settings.value(key, default))))
    except (TypeError, ValueError):
        return default

def saved_int(settings, key, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, int(settings.value(key, default))))
    except (TypeError, ValueError):
        return default

def normalized_filter_settings(filter_type, filter_params=None):
    try:
        return filters.normalize_filter_settings(filter_type, filter_params)
    except Exception:
        try:
            return filters.normalize_filter_settings(filter_type)
        except Exception:
            return "median", {"window_size": 5}

def saved_filter_settings(settings):
    filter_type = settings.value("analysis/filter_type", DEFAULT_FILTER_TYPE)
    stored_params = settings.value("analysis/filter_params", "")
    if isinstance(stored_params, str):
        try:
            filter_params = json.loads(stored_params) if stored_params else {}
        except Exception:
            filter_params = {}
    else:
        filter_params = {}
    return normalized_filter_settings(filter_type, filter_params)



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1700, 950)

        self.identifier = SpectrumIdentifier()
        self.current_data = None
        self.current_result = None
        self.current_file_name = None
        self.current_file_path = None
        self.current_spectrum: LoadedSpectrum | None = None
        self.log_history = []
        self.log_window = None
        self.settings = app_settings()
        self.theme = saved_theme(self.settings)
        self.font_family = saved_font_family(self.settings)
        self.font_size = saved_font_size(self.settings)
        self.baseline_enabled = saved_bool(
            self.settings, "analysis/baseline_enabled", DEFAULT_BASELINE_ENABLED
        )
        self.baseline_method = self.settings.value(
            "analysis/baseline_method", DEFAULT_BASELINE_METHOD
        )
        if self.baseline_method not in ("improved", "simple"):
            self.baseline_method = DEFAULT_BASELINE_METHOD
        self.sample_rate = saved_float(
            self.settings,
            "analysis/sample_rate",
            DEFAULT_SAMPLE_RATE,
            0.001,
            10_000_000.0,
        )
        self.peak_threshold = saved_float(
            self.settings, "analysis/peak_threshold", DEFAULT_PEAK_THRESHOLD, 0.001, 1.0
        )
        self.peak_prominence = saved_float(
            self.settings, "analysis/peak_prominence", DEFAULT_PEAK_PROMINENCE, 0.0, 1_000_000.0
        )
        self.peak_distance = saved_int(
            self.settings, "analysis/peak_distance", DEFAULT_PEAK_DISTANCE, 1, 10_000
        )
        self.filter_type, self.filter_params = saved_filter_settings(self.settings)
        self.normalize_area = saved_bool(
            self.settings, "analysis/normalize_area", DEFAULT_NORMALIZE_AREA
        )

        self.analysis_settings = self._build_analysis_settings()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 8)
        main_layout.setSpacing(8)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        self.btn_open = QPushButton("Open file")
        self.btn_run = QPushButton("Analyze")
        self.btn_add = QPushButton("➕ Add")
        self.btn_restore = QPushButton("♻ Restore library")
        self.btn_export = QPushButton("📄 PDF Report")
        self.btn_export_peaks = QPushButton("Export Peaks (CSV)")
        self.btn_analysis_settings = QPushButton("Analysis Settings")
        self.btn_log = QPushButton("Log")
        self.btn_settings = QPushButton("⚙ Settings")
        self.logo_label = QLabel()
        self.logo_label.setObjectName("appLogo")
        self.logo_label.setFixedSize(58, 44)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setAccessibleName("ChromaTsvet logo")
        self.logo_label.setToolTip("ChromaTsvet")
        logo_pixmap = QPixmap(str(APP_LOGO_PATH))
        if logo_pixmap.isNull():
            self.logo_label.hide()
        else:
            self.logo_label.setPixmap(
                logo_pixmap.scaled(
                    self.logo_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

        self.btn_open.clicked.connect(self.load_file)
        self.btn_run.clicked.connect(self.run_analysis)
        self.btn_add.clicked.connect(self.add_substance)
        self.btn_restore.clicked.connect(self.restore_database)
        self.btn_export.clicked.connect(self.export_pdf)
        self.btn_export_peaks.clicked.connect(self.export_peaks_csv)
        self.btn_analysis_settings.clicked.connect(self.open_analysis_settings)
        self.btn_log.clicked.connect(self.open_log)
        self.btn_settings.clicked.connect(self.open_settings)

        btn_layout.addWidget(self.btn_open)
        self.file_label = QLabel()
        self.file_label.setObjectName("fileLabel")
        self.file_label.setMinimumWidth(220)
        self.file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.file_label.setAccessibleName("Current spectrum file")
        btn_layout.addWidget(self.file_label)
        btn_layout.addWidget(self.btn_run)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_restore)
        btn_layout.addWidget(self.btn_export)
        btn_layout.addWidget(self.btn_export_peaks)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_analysis_settings)
        btn_layout.addWidget(self.btn_log)
        btn_layout.addWidget(self.btn_settings)
        btn_layout.addWidget(self.logo_label)
        main_layout.addLayout(btn_layout)

        self.plot = pg.PlotWidget()
        self.spectrum_plot = SpectrumPlot(self.plot)
        self.spectrum_plot.configure(self.theme, self.font_family, self.font_size)
        main_layout.addWidget(self.plot)

        self.results_tabs = QTabWidget()

        self.peak_table = QTableWidget()
        self.peak_table.setColumnCount(6)
        self.peak_table.setHorizontalHeaderLabels(
            ["Frequency (Hz)", "Bin", "Intensity", "Width (bins)", "Area", "SNR"]
        )
        self.peak_table.setAlternatingRowColors(True)
        self.peak_table.verticalHeader().setVisible(False)
        self.peak_table.horizontalHeader().setStretchLastSection(True)
        self.peak_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_tabs.addTab(self.peak_table, "Detected Peaks")

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Substance", "Formula", "Score", "Compared points"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_tabs.addTab(self.table, "Identification Results")
        self._update_result_tab_titles(0, 0)
        main_layout.addWidget(self.results_tabs)

        self.log_panel = QWidget()
        self.log_panel.setObjectName("embeddedLogPanel")
        self.log_panel.setFixedHeight(140)
        log_layout = QVBoxLayout(self.log_panel)
        log_layout.setContentsMargins(8, 6, 8, 8)
        log_layout.setSpacing(5)

        log_controls = QHBoxLayout()
        log_controls.setSpacing(6)
        log_title = QLabel("Application Log")
        log_title.setStyleSheet("font-weight: 600;")
        self.log_clear_button = QPushButton("Clear")
        self.log_copy_button = QPushButton("Copy")
        self.log_autoscroll_checkbox = QCheckBox("Auto-scroll")
        self.log_autoscroll_checkbox.setChecked(True)
        self.log_clear_button.clicked.connect(self.clear_log)
        self.log_copy_button.clicked.connect(self.copy_embedded_log)
        log_controls.addWidget(log_title)
        log_controls.addStretch()
        log_controls.addWidget(self.log_autoscroll_checkbox)
        log_controls.addWidget(self.log_copy_button)
        log_controls.addWidget(self.log_clear_button)
        log_layout.addLayout(log_controls)

        self.embedded_log_view = QTextEdit()
        self.embedded_log_view.setReadOnly(True)
        self.embedded_log_view.setMinimumHeight(78)
        self.embedded_log_view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.embedded_log_view.setAccessibleName("Application log")
        log_layout.addWidget(self.embedded_log_view)
        main_layout.addWidget(self.log_panel)

        self.status_bar = QStatusBar(self)
        self.status_bar.setSizeGripEnabled(False)
        self.status_source_label = QLabel("No file loaded")
        self.status_source_label.setObjectName("statusSourceLabel")
        self.status_bar.addPermanentWidget(self.status_source_label)
        self.setStatusBar(self.status_bar)

        self._update_file_display()
        self._update_export_actions()

        self.log("Application started", status_message="Ready")
        self.status_bar.showMessage("Ready")

    def open_settings(self):
        SettingsDialog(self).exec()

    def open_analysis_settings(self):
        AnalysisSettingsDialog(self).exec()

    def open_log(self):
        if self.log_window is None:
            self.log_window = LogWindow(self)
        self.log_window.show()
        self.log_window.raise_()
        self.log_window.activateWindow()

    def set_analysis_settings(
        self,
        baseline_enabled,
        baseline_method,
        peak_threshold,
        peak_prominence,
        peak_distance,
        filter_type=DEFAULT_FILTER_TYPE,
        filter_params=None,
        sample_rate=DEFAULT_SAMPLE_RATE,
        normalize_area=DEFAULT_NORMALIZE_AREA,
    ):
        try:
            normalized_filter_type, normalized_filter_params = (
                filters.normalize_filter_settings(filter_type, filter_params)
            )
            normalized_baseline_enabled = bool(baseline_enabled)
            normalized_baseline_method = (
                baseline_method
                if baseline_method in ("improved", "simple")
                else DEFAULT_BASELINE_METHOD
            )
            normalized_peak_threshold = max(0.001, min(1.0, float(peak_threshold)))
            normalized_peak_prominence = max(
                0.0, min(1_000_000.0, float(peak_prominence))
            )
            normalized_peak_distance = max(1, min(10_000, int(peak_distance)))
            normalized_sample_rate = max(
                0.001, min(10_000_000.0, float(sample_rate))
            )
            normalized_area_enabled = bool(normalize_area)
        except (filters.FilterError, TypeError, ValueError) as exc:
            self._show_error(
                "Invalid analysis settings",
                "The analysis settings are invalid and were not applied.",
                exception=exc,
                status_message="Invalid analysis settings",
            )
            return

        self.baseline_enabled = normalized_baseline_enabled
        self.baseline_method = normalized_baseline_method
        self.peak_threshold = normalized_peak_threshold
        self.peak_prominence = normalized_peak_prominence
        self.peak_distance = normalized_peak_distance
        self.sample_rate = normalized_sample_rate
        self.filter_type = normalized_filter_type
        self.filter_params = normalized_filter_params
        self.normalize_area = normalized_area_enabled

        self.analysis_settings = self._build_analysis_settings()

        self.settings.setValue("analysis/baseline_enabled", self.baseline_enabled)
        self.settings.setValue("analysis/baseline_method", self.baseline_method)
        self.settings.setValue("analysis/sample_rate", self.sample_rate)
        self.settings.setValue("analysis/peak_threshold", self.peak_threshold)
        self.settings.setValue("analysis/peak_prominence", self.peak_prominence)
        self.settings.setValue("analysis/peak_distance", self.peak_distance)
        self.settings.setValue("analysis/filter_type", self.filter_type)
        self.settings.setValue("analysis/normalize_area", self.normalize_area)
        self.settings.setValue(
            "analysis/filter_params",
            json.dumps(self.filter_params, sort_keys=True, separators=(",", ":")),
        )
        self.settings.sync()
        if self.settings.status() != QSettings.NoError:
            self.log(
                "Analysis settings were applied but could not be persisted",
                status_message="Could not save analysis settings",
                level="warning",
            )

        baseline_description = self.baseline_method if self.baseline_enabled else "disabled"
        self.log(
            "Analysis settings applied: "
            f"baseline={baseline_description}, threshold={self.peak_threshold:.3f}, "
            f"prominence={self.peak_prominence:g}, distance={self.peak_distance}, "
            f"sample_rate={self.sample_rate:g} Hz, "
            f"filter={self.filter_type}, filter_params={self.filter_params}, "
            f"normalization={'area' if self.normalize_area else 'disabled'}",
            status_message="Analysis settings applied",
        )
        if self.current_data is not None:
            self.run_analysis()

    def set_theme(self, theme):
        self.theme = theme if theme in ("dark", "light") else DEFAULT_THEME
        self.settings.setValue("ui/theme", self.theme)
        self.apply_ui_settings()

    def set_font_family(self, family):
        self.font_family = available_font_family(family)
        self.settings.setValue("ui/font_family", self.font_family)
        self.apply_ui_settings()

    def set_font_size(self, size):
        self.font_size = max(9, min(16, int(size)))
        self.settings.setValue("ui/font_size", self.font_size)
        self.apply_ui_settings()

    def reset_ui_settings(self):
        self.settings.remove("ui/theme")
        self.settings.remove("ui/font_family")
        self.settings.remove("ui/font_size")
        self.theme = DEFAULT_THEME
        self.font_family = available_font_family()
        self.font_size = DEFAULT_FONT_SIZE
        self.apply_ui_settings()

    def apply_ui_settings(self):
        apply_app_theme(QApplication.instance(), self.theme, self.font_family, self.font_size)
        if hasattr(self, "spectrum_plot"):
            self.spectrum_plot.configure(self.theme, self.font_family, self.font_size)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        fixed_font.setPointSize(max(9, self.font_size - 2))
        self.embedded_log_view.setFont(fixed_font)
        self._refresh_embedded_log()
        if self.current_data is not None:
            self.run_analysis()

    def log(
        self,
        msg: str,
        status_message=None,
        level: str = "info",
        exc_info: bool = False,
    ) -> None:
        """Add a timestamped log entry and update the status bar.

        Supported levels are ``info``, ``warning``, and ``error``. Unknown
        values are treated as ``info`` so logging never becomes a new failure.
        """
        normalized_level = level.strip().lower() if isinstance(level, str) else "info"
        if normalized_level not in LOG_LEVEL_LABELS:
            normalized_level = "info"

        timestamp = datetime.now().strftime("%H:%M:%S")
        label = LOG_LEVEL_LABELS[normalized_level]
        entry = f"[{timestamp}] [{label}] {msg}"
        if exc_info:
            logger.exception(msg)
        else:
            logger.log(
                {
                    "info": logging.INFO,
                    "warning": logging.WARNING,
                    "error": logging.ERROR,
                }[normalized_level],
                msg,
            )
        self.log_history.append(entry)
        self.status_bar.showMessage(status_message or msg)
        append_log_entry(
            self.embedded_log_view,
            entry,
            normalized_level,
            auto_scroll=self.log_autoscroll_checkbox.isChecked(),
        )
        if self.log_window is not None:
            self.log_window.append_entry(entry, normalized_level)

    def _show_warning(self, title, user_message, *, log_message=None, status_message=None):
        self.log(
            log_message or user_message,
            status_message=status_message or user_message,
            level="warning",
        )
        QMessageBox.warning(self, title, user_message)

    def _show_error(
        self,
        title,
        user_message,
        *,
        exception=None,
        critical=False,
        status_message=None,
    ):
        log_message = user_message
        if exception is not None:
            details = str(exception).strip() or repr(exception)
            log_message = f"{user_message} ({type(exception).__name__}: {details})"

        self.log(
            log_message,
            status_message=status_message or user_message,
            level="error",
            exc_info=exception is not None,
        )
        message_box = QMessageBox.critical if critical else QMessageBox.warning
        message_box(self, title, user_message)

    def clear_log(self):
        self.log_history.clear()
        self.embedded_log_view.clear()
        if self.log_window is not None:
            self.log_window.clear()
        self.status_bar.showMessage("Log cleared")

    def copy_embedded_log(self):
        QApplication.clipboard().setText(self.embedded_log_view.toPlainText())

    def _refresh_embedded_log(self):
        self.embedded_log_view.clear()
        for entry in self.log_history:
            append_log_entry(
                self.embedded_log_view,
                entry,
                log_level_from_entry(entry),
                auto_scroll=False,
            )
        if self.log_autoscroll_checkbox.isChecked():
            self.embedded_log_view.moveCursor(QTextCursor.End)
            self.embedded_log_view.ensureCursorVisible()

    def display_source_name(self):
        if self.current_file_name:
            return self.current_file_name
        if self.current_data:
            return "In-memory data"
        return "No file loaded"

    def _update_file_display(self):
        if self.current_file_name:
            self.file_label.setText(f"File: {self.current_file_name}")
            self.file_label.setToolTip(self.current_file_path or self.current_file_name)
            self.status_source_label.setText(self.current_file_name)
            self.status_source_label.setToolTip(self.current_file_path or self.current_file_name)
            self.setWindowTitle(f"{WINDOW_TITLE} — {self.current_file_name}")
            return

        self.file_label.setText("File not loaded")
        self.file_label.setToolTip("Open a CSV or TXT spectrum file")
        self.status_source_label.setText("No file loaded")
        self.status_source_label.setToolTip("Open a CSV or TXT spectrum file")
        self.setWindowTitle(WINDOW_TITLE)

    def _update_export_actions(self):
        peaks = (
            self.current_result.get("peaks", [])
            if self.current_result is not None
            else []
        )
        self.btn_export_peaks.setEnabled(bool(peaks))

    def _update_result_tab_titles(self, peak_count, match_count):
        self.results_tabs.setTabText(0, f"Detected Peaks ({peak_count})")
        self.results_tabs.setTabText(1, f"Identification Results ({match_count})")

    def _build_analysis_settings(self):
        return AnalysisSettings(
            sample_rate=self.sample_rate,
            filter_type=self.filter_type,
            filter_params=dict(self.filter_params),
            baseline_enabled=self.baseline_enabled,
            baseline_method=self.baseline_method,
            peak_threshold=self.peak_threshold,
            peak_prominence=self.peak_prominence,
            peak_distance=self.peak_distance,
            normalize_area=self.normalize_area,
            window_type=DEFAULT_WINDOW_TYPE,
        )

    def _readonly_table_item(self, value):
        item = QTableWidgetItem(str(value))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _format_peak_value(self, value, precision=6):
        if value is None:
            return ""
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return str(value)
        if not np.isfinite(numeric_value):
            return ""
        return f"{numeric_value:.{precision}g}"

    def _peak_frequency(self, peak):
        frequency = getattr(peak, "frequency", None)
        try:
            frequency = float(frequency)
        except (TypeError, ValueError):
            frequency = None

        if frequency is not None and np.isfinite(frequency):
            return frequency
        return getattr(peak, "position", None)

    def _set_peak_table(self, peaks):
        self.peak_table.setRowCount(len(peaks))
        for row, peak in enumerate(peaks):
            values = [
                self._format_peak_value(self._peak_frequency(peak), precision=7),
                self._format_peak_value(getattr(peak, "position", None), precision=7),
                self._format_peak_value(getattr(peak, "intensity", None), precision=7),
                self._format_peak_value(getattr(peak, "width", None)),
                self._format_peak_value(getattr(peak, "area", None)),
                self._format_peak_value(getattr(peak, "snr", None)),
            ]
            for column, value in enumerate(values):
                self.peak_table.setItem(row, column, self._readonly_table_item(value))

    def _set_match_table(self, matches):
        self.table.setRowCount(len(matches))
        for row, match in enumerate(matches):
            compared_points = getattr(
                match,
                "compared_points",
                getattr(match, "matched_points", 0),
            )
            values = [
                match.substance_name,
                match.formula,
                f"{match.score:.3f}",
                compared_points,
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, self._readonly_table_item(value))

    def load_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Open spectrum", "", "CSV (*.csv);;TXT (*.txt)")
        if not file:
            return

        file_path = Path(file)
        try:
            if file_path.stat().st_size == 0:
                self._show_warning(
                    "Empty file",
                    "The selected file is empty.",
                    log_message=f"Empty spectrum file selected: {file_path}",
                    status_message="Empty spectrum file",
                )
                return

            data, skipped_rows = read_spectrum_file(file)
        except SpectrumFileFormatError as exc:
            self._show_warning(
                "Unsupported spectrum format",
                str(exc),
                log_message=f"Invalid spectrum file format in {file_path}: {exc}",
                status_message="Unsupported spectrum file format",
            )
            return
        except (OSError, UnicodeError, csv.Error) as exc:
            self._show_error(
                "Could not open file",
                "The selected spectrum file could not be read. Check its encoding and permissions.",
                exception=exc,
                status_message="Could not read spectrum file",
            )
            return
        except Exception as exc:
            self._show_error(
                "Could not open file",
                "An unexpected error occurred while reading the spectrum file.",
                exception=exc,
                critical=True,
                status_message="Could not read spectrum file",
            )
            return

        if not data:
            self._show_warning(
                "No spectrum data",
                "No numeric values were found. Check the file format and delimiter.",
                log_message=(
                    f"No numeric values found in {file_path}; "
                    f"non-numeric rows: {len(skipped_rows)}"
                ),
                status_message="No numeric spectrum data found",
            )
            return

        if skipped_rows:
            examples = "\n".join(
                f"Line {line_no}: {value}" for line_no, value in skipped_rows[:5]
            )
            self._show_warning(
                "Some rows were skipped",
                f"Loaded points: {len(data)}\n"
                f"Skipped rows: {len(skipped_rows)}\n\n"
                f"Problematic values:\n{examples}",
                log_message=(
                    f"Loaded {file_path} with {len(skipped_rows)} skipped rows "
                    f"and {len(data)} valid points"
                ),
                status_message=f"Loaded with {len(skipped_rows)} skipped rows",
            )

        self.current_data = data
        self.current_file_name = file_path.name
        self.current_file_path = str(file_path.resolve())

        self.current_spectrum = LoadedSpectrum(
            data=data,
            file_path=self.current_file_path,
            file_name=self.current_file_name,
        )
        self._update_file_display()
        self.log(
            f"Loaded file: {self.current_file_path} ({len(data)} points)",
            status_message=f"Loaded: {self.current_file_name}",
        )
        self.run_analysis()

    def run_analysis(self):
        if self.current_data is None:
            return

        self.current_result = None
        self._set_peak_table([])
        self._set_match_table([])
        self._update_result_tab_titles(0, 0)
        self._update_export_actions()
        self.analysis_settings = self._build_analysis_settings()

        try:
            result = run_analysis_pipeline(
                self.current_data,
                self.analysis_settings,
            )
        except filters.FilterError as exc:
            self._show_error(
                "Signal filtering error",
                "The selected signal filter could not be applied. The analysis was not run.",
                exception=exc,
                status_message="Signal filtering failed",
            )
            return
        except Exception as exc:
            self._show_error(
                "Analysis error",
                "The spectrum analysis could not be completed. The application can continue to be used.",
                exception=exc,
                critical=True,
                status_message="Spectrum analysis failed",
            )
            return

        try:
            spectrum = np.asarray(result.get("spectrum", []), dtype=float)
            frequency_axis = self.spectrum_plot.frequency_axis(result, len(spectrum))
            peaks = result.get("peaks", [])
            matches = self.identifier.find_matches(spectrum)

            self.spectrum_plot.clear()
            plot_title = (
                f"Spectrum — {self.current_file_name}"
                if self.current_file_name
                else "Spectrum"
            )
            self.spectrum_plot.set_title(plot_title)
            self.spectrum_plot.plot_spectrum(frequency_axis, spectrum)
            self.spectrum_plot.add_peak_markers(peaks)
            self._set_peak_table(peaks)
            self._set_match_table(matches)
            self._update_result_tab_titles(len(peaks), len(matches))
        except Exception as exc:
            self._show_error(
                "Analysis error",
                "The spectrum analysis could not be completed. The application can continue to be used.",
                exception=exc,
                critical=True,
                status_message="Spectrum analysis failed",
            )
            return

        self.current_result = result
        self._update_export_actions()

        source_name = self.current_file_name or "In-memory data"
        self.log(
            f"Analysis done. Peaks: {len(peaks)} | Matches: {len(matches)}",
            status_message=f"{source_name} | Analysis done. Peaks: {len(peaks)}",
        )

    def add_substance(self):
        name, ok = QInputDialog.getText(self, "New substance", "Name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            self._show_warning("Invalid name", "Substance name cannot be empty.")
            return

        formula, ok = QInputDialog.getText(self, "Formula", "Formula:")
        if not ok:
            return

        ints_str, ok = QInputDialog.getText(self, "Intensities", "Comma-separated values:")
        if not ok:
            return

        try:
            values = [value.strip() for value in ints_str.split(',')]
            if not values or any(not value for value in values):
                raise ValueError("intensity values cannot be empty")
            intensities = [float(value) for value in values]
            if not np.isfinite(intensities).all():
                raise ValueError("intensities must be finite numbers")
        except (TypeError, ValueError) as exc:
            self._show_error(
                "Invalid intensities",
                "Enter one or more finite numbers separated by commas.",
                exception=exc,
                status_message="Invalid substance intensities",
            )
            return

        try:
            added = self.identifier.add_reference(name, intensities, formula.strip())
            if added is False:
                raise RuntimeError("the reference library rejected the new substance")
        except Exception as exc:
            self._show_error(
                "Library error",
                f"'{name}' could not be added to the reference library.",
                exception=exc,
                critical=True,
                status_message="Could not add substance",
            )
            return

        self.log(
            f"Added substance to reference library: {name}",
            status_message=f"Added: {name}",
        )
        QMessageBox.information(self, "Success", f"'{name}' has been added.")
        self.run_analysis()

    def clear_database(self):
        answer = QMessageBox.question(
            self,
            "Clear library",
            "Clear the reference library?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            if self.identifier.clear_database() is False:
                raise RuntimeError("the reference library could not be cleared")
        except Exception as exc:
            self._show_error(
                "Library error",
                "The reference library could not be cleared.",
                exception=exc,
                critical=True,
                status_message="Could not clear reference library",
            )
            return

        self.log("Reference library cleared", status_message="Reference library cleared")
        self.run_analysis()

    def restore_database(self):
        answer = QMessageBox.question(
            self,
            "Restore library",
            "Restore the default reference library?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            if self.identifier.restore_default() is False:
                raise RuntimeError("the default reference library could not be restored")
        except Exception as exc:
            self._show_error(
                "Library error",
                "The default reference library could not be restored.",
                exception=exc,
                critical=True,
                status_message="Could not restore reference library",
            )
            return

        self.log("Reference library restored", status_message="Reference library restored")
        self.run_analysis()

    def export_pdf(self):
        if not self.current_result:
            self._show_warning(
                "No analysis results",
                "Analyze a spectrum before exporting a report.",
                status_message="No analysis results to export",
            )
            return

        file, _ = QFileDialog.getSaveFileName(self, "Save PDF report", f"report_{datetime.now():%Y%m%d_%H%M}.pdf", "PDF (*.pdf)")
        if not file:
            return

        plot_path = None
        try:
            plot_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            plot_path = plot_file.name
            plot_file.close()
            QApplication.processEvents()
            if not self.plot.grab().save(plot_path, "PNG"):
                raise OSError("the spectrum plot could not be rendered")

            c = canvas.Canvas(file, pagesize=A4)
            width, height = A4
            margin = 50
            y = height - 55

            if APP_LOGO_PATH.is_file():
                c.drawImage(
                    str(APP_LOGO_PATH),
                    width - margin - 78,
                    height - 72,
                    width=78,
                    height=58,
                    preserveAspectRatio=True,
                    mask='auto',
                )

            c.setFont("Helvetica-Bold", 18)
            c.drawString(margin, y, "ChromaTsvet Analysis Report")
            y -= 22

            c.setFont("Helvetica", 9)
            c.setFillColorRGB(0.35, 0.38, 0.43)
            c.drawString(margin, y, "Spectral data and chromatogram analysis")
            c.setFillColorRGB(0, 0, 0)
            y -= 30

            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Summary")
            y -= 18

            c.setFont("Helvetica", 10)
            summary_rows = [
                ("Date", f"{datetime.now():%Y-%m-%d %H:%M}"),
                ("App version", APP_VERSION),
                ("Rust core", spectrometer_rust.get_version()),
                ("Source file", self.display_source_name()),
                ("Source path", self.current_file_path or self.display_source_name()),
                ("Data points", str(len(self.current_data) if self.current_data else 0)),
                ("Peaks found", str(len(self.current_result["peaks"]))),
            ]
            for label, value in summary_rows:
                c.drawString(margin, y, f"{label}:")
                c.drawString(margin + 95, y, str(value)[:78])
                y -= 15
            y -= 14

            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Analysis Parameters")
            y -= 18

            c.setFont("Helvetica", 10)
            baseline_description = (
                self.baseline_method if self.baseline_enabled else "disabled"
            )
            normalization_description = (
                "area" if self.current_result.get("normalized") else "disabled"
            )
            parameter_rows = [
                ("Sample rate", f"{self.sample_rate:g} Hz"),
                ("FFT window", DEFAULT_WINDOW_TYPE),
                ("Signal filter", self.filter_type),
                ("Filter params", self.filter_params),
                ("Baseline", baseline_description),
                ("Normalization", normalization_description),
                ("Threshold", f"{self.peak_threshold:.3f}"),
                ("Prominence", "automatic" if self.peak_prominence == 0 else f"{self.peak_prominence:g}"),
                ("Distance", f"{self.peak_distance} points"),
            ]
            for label, value in parameter_rows:
                c.drawString(margin, y, f"{label}:")
                c.drawString(margin + 95, y, str(value)[:78])
                y -= 15
            y -= 12

            if y < 340:
                c.showPage()
                y = height - margin

            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Spectrum")
            y -= 218
            c.drawImage(plot_path, margin, y, width=width - margin * 2, height=200, preserveAspectRatio=True, anchor='c')
            y -= 25

            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Detected Peaks")
            y -= 20

            c.setFont("Helvetica-Bold", 9)
            c.drawString(margin, y, "Frequency Hz")
            c.drawString(margin + 88, y, "Bin")
            c.drawString(margin + 135, y, "Intensity")
            c.drawString(margin + 205, y, "Width")
            c.drawString(margin + 270, y, "Area")
            c.drawString(margin + 350, y, "SNR")
            y -= 13
            c.line(margin, y, width - margin, y)
            y -= 12

            c.setFont("Helvetica", 9)
            peaks = self.current_result["peaks"]
            if peaks:
                for peak in peaks:
                    if y < 90:
                        c.showPage()
                        y = height - margin
                        c.setFont("Helvetica-Bold", 9)
                        c.drawString(margin, y, "Frequency Hz")
                        c.drawString(margin + 88, y, "Bin")
                        c.drawString(margin + 135, y, "Intensity")
                        c.drawString(margin + 205, y, "Width")
                        c.drawString(margin + 270, y, "Area")
                        c.drawString(margin + 350, y, "SNR")
                        y -= 13
                        c.line(margin, y, width - margin, y)
                        y -= 12
                        c.setFont("Helvetica", 9)
                    c.drawString(margin, y, self._format_peak_value(self._peak_frequency(peak)))
                    c.drawString(margin + 88, y, self._format_peak_value(peak.position))
                    c.drawString(margin + 135, y, self._format_peak_value(peak.intensity))
                    c.drawString(margin + 205, y, self._format_peak_value(peak.width))
                    c.drawString(margin + 270, y, self._format_peak_value(peak.area))
                    c.drawString(margin + 350, y, self._format_peak_value(peak.snr))
                    y -= 14
            else:
                c.drawString(margin, y, "No peaks detected.")
                y -= 16

            y -= 10
            if y < 150:
                c.showPage()
                y = height - margin

            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Identification Results")
            y -= 20

            c.setFont("Helvetica-Bold", 9)
            c.drawString(margin, y, "Substance")
            c.drawString(margin + 170, y, "Formula")
            c.drawString(margin + 270, y, "Score")
            c.drawString(margin + 340, y, "Compared points")
            y -= 13
            c.line(margin, y, width - margin, y)
            y -= 12

            c.setFont("Helvetica", 9)
            for row in range(self.table.rowCount()):
                if y < 80:
                    c.showPage()
                    y = height - margin
                    c.setFont("Helvetica", 9)
                name = self.table.item(row, 0).text()
                formula = self.table.item(row, 1).text()
                score = self.table.item(row, 2).text()
                compared_points = self.table.item(row, 3).text()
                c.drawString(margin, y, name[:28])
                c.drawString(margin + 170, y, formula[:14])
                c.drawString(margin + 270, y, score)
                c.drawString(margin + 340, y, compared_points)
                y -= 14

            c.save()
            QMessageBox.information(self, "Success", f"PDF report saved:\n{file}")
            self.log(
                f"PDF report created: {file}",
                status_message=f"PDF report saved: {Path(file).name}",
            )
        except PermissionError as exc:
            self._show_error(
                "Could not save report",
                "The PDF report could not be saved because access to the selected location was denied.",
                exception=exc,
                status_message="PDF report was not saved",
            )
        except Exception as exc:
            self._show_error(
                "Could not create report",
                "The PDF report could not be created. Choose another location and try again.",
                exception=exc,
                critical=True,
                status_message="PDF report creation failed",
            )
        finally:
            if plot_path and os.path.exists(plot_path):
                try:
                    os.unlink(plot_path)
                except OSError as exc:
                    self.log(
                        f"Could not remove temporary report image: {plot_path} "
                        f"({type(exc).__name__}: {exc})",
                        status_message="Temporary report file could not be removed",
                        level="warning",
                    )

    def export_peaks_csv(self):
        if self.current_result is None:
            self._show_warning(
                "No analysis results",
                "Analyze a spectrum before exporting detected peaks.",
                status_message="No analysis results to export",
            )
            self._update_export_actions()
            return

        peaks = self.current_result.get("peaks", [])
        if not peaks:
            self._show_warning(
                "No detected peaks",
                "The current analysis has no detected peaks to export.",
                status_message="No detected peaks to export",
            )
            self._update_export_actions()
            return

        file, _ = QFileDialog.getSaveFileName(
            self,
            "Export detected peaks",
            f"peaks_{datetime.now():%Y%m%d_%H%M}.csv",
            "CSV (*.csv)",
        )
        if not file:
            return

        try:
            with open(file, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(
                    ["frequency_hz", "position", "intensity", "width", "area", "snr"]
                )
                for peak in peaks:
                    writer.writerow(
                        [
                            self._peak_frequency(peak),
                            peak.position,
                            peak.intensity,
                            peak.width,
                            peak.area,
                            peak.snr,
                        ]
                    )

            QMessageBox.information(self, "Success", f"Peak list saved:\n{file}")
            self.log(
                f"Peak list exported: {file} ({len(peaks)} peaks)",
                status_message=f"Peak list saved: {Path(file).name}",
            )
        except PermissionError as exc:
            self._show_error(
                "Could not save peak list",
                "The peak list could not be saved because access to the selected location was denied.",
                exception=exc,
                status_message="Peak list was not saved",
            )
        except Exception as exc:
            self._show_error(
                "Could not export peak list",
                "The detected peaks could not be exported. Choose another location and try again.",
                exception=exc,
                critical=True,
                status_message="Peak list export failed",
            )
