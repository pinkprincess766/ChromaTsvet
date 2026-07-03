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
    QCheckBox, QDoubleSpinBox, QGroupBox, QStatusBar, QTabWidget, QAction
)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import (QFont, QColor, QPalette, QFontDatabase, QPixmap,
                         QTextCharFormat, QTextCursor)
import pyqtgraph as pg

from paths import ensure_rust_in_path, get_library_db_path, get_project_root

# Local imports
from python_analyzer.core.identification import (
    MatchResult,
    SpectrumIdentifier,
    normalize_data_type,
    peak_to_reference_peak,
)
from python_analyzer.readers import read_spectrum_file, SpectrumFileFormatError
from python_analyzer.analysis.models import AnalysisSettings, LoadedSpectrum
from python_analyzer.analysis.runner import run_analysis as run_analysis_pipeline
from python_analyzer.exporters import (
    PDFReportData,
    PDFReportExporter,
    write_peaks_csv,
)
from python_analyzer.viz.spectrum_plot import SpectrumPlot
from python_analyzer.gui.dialogs import SettingsDialog, LogWindow, AnalysisSettingsDialog
from python_analyzer.gui.log_view import (
    LOG_LEVEL_LABELS,
    append_log_entry,
    log_level_from_entry,
)
from python_analyzer.gui.recent_files import (
    clear_recent_files as clear_recent_file_history,
    forget_recent_file,
    load_last_directory,
    load_recent_files,
    remember_recent_file,
    remember_last_directory,
    suggested_dialog_path,
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
DEFAULT_PEAK_MIN_SNR = 0.0
DEFAULT_FILTER_TYPE = "median"
DEFAULT_NORMALIZE_AREA = False
DEFAULT_SPECTRUM_SMOOTHING_ENABLED = False
DEFAULT_SPECTRUM_SMOOTHING_METHOD = "savgol"
DEFAULT_SPECTRUM_SMOOTHING_WINDOW = 7
APP_LOGO_PATH = get_project_root() / "assets" / "chromatsvet_logo.png"
DEBUG_TRACEBACK_ENV = "CHROMATSVET_DEBUG_TRACEBACKS"

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

def debug_tracebacks_enabled():
    value = os.environ.get(DEBUG_TRACEBACK_ENV, "")
    return str(value).strip().lower() in ("1", "true", "yes", "on")

def display_file_label(path):
    try:
        return Path(path).name or "selected file"
    except (TypeError, ValueError):
        return "selected file"

def safe_exception_details(exception):
    if isinstance(exception, OSError):
        if getattr(exception, "strerror", None):
            return exception.strerror
        details = str(exception).strip()
        if details and not getattr(exception, "filename", None):
            return details
        return type(exception).__name__
    return str(exception).strip() or repr(exception)

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
        self.current_peaks = []
        self.current_file_name = None
        self.current_file_path = None
        self.current_spectrum: LoadedSpectrum | None = None
        self.analysis_status = "idle"
        self.log_history = []
        self.log_window = None
        self.settings = app_settings()
        self.recent_files = load_recent_files(self.settings)
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
        self.peak_min_snr = saved_float(
            self.settings, "analysis/peak_min_snr", DEFAULT_PEAK_MIN_SNR, 0.0, 1_000_000.0
        )
        self.filter_type, self.filter_params = saved_filter_settings(self.settings)
        self.normalize_area = saved_bool(
            self.settings, "analysis/normalize_area", DEFAULT_NORMALIZE_AREA
        )
        self.spectrum_smoothing_enabled = saved_bool(
            self.settings,
            "analysis/spectrum_smoothing_enabled",
            DEFAULT_SPECTRUM_SMOOTHING_ENABLED,
        )
        self.spectrum_smoothing_method = (
            self.settings.value(
                "analysis/spectrum_smoothing_method",
                DEFAULT_SPECTRUM_SMOOTHING_METHOD,
            )
            or DEFAULT_SPECTRUM_SMOOTHING_METHOD
        )
        if self.spectrum_smoothing_method not in ("savgol", "median"):
            self.spectrum_smoothing_method = DEFAULT_SPECTRUM_SMOOTHING_METHOD
        self.spectrum_smoothing_window = saved_int(
            self.settings,
            "analysis/spectrum_smoothing_window",
            DEFAULT_SPECTRUM_SMOOTHING_WINDOW,
            3,
            501,
        )
        if self.spectrum_smoothing_window % 2 == 0:
            self.spectrum_smoothing_window += 1
        self.peak_frequency_tolerance = saved_float(
            self.settings, "analysis/peak_frequency_tolerance", 5.0, 0.1, 1000.0
        )
        self.data_type = self.settings.value("analysis/data_type", "generic") or "generic"

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

        self._create_menus()

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
        self.peak_table.setColumnCount(7)
        self.peak_table.setHorizontalHeaderLabels(
            [
                "Frequency (Hz)",
                "Bin",
                "Intensity",
                "Width (bins)",
                "Width (Hz)",
                "Area",
                "SNR",
            ]
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
        self.status_details_label = QLabel("No data | idle")
        self.status_details_label.setObjectName("statusDetailsLabel")
        self.status_bar.addPermanentWidget(self.status_source_label)
        self.status_bar.addPermanentWidget(self.status_details_label)
        self.setStatusBar(self.status_bar)

        self._update_file_display()
        self._update_export_actions()

        self.log("Application started", status_message="Ready")
        self.status_bar.showMessage("Ready")

    def _create_menus(self):
        file_menu = self.menuBar().addMenu("&File")

        self.open_file_action = QAction("Open Spectrum...", self)
        self.open_file_action.setStatusTip("Open a CSV or TXT spectrum file")
        self.open_file_action.triggered.connect(self.load_file)
        file_menu.addAction(self.open_file_action)

        self.recent_files_menu = file_menu.addMenu("Recent Files")
        self.recent_files_menu.aboutToShow.connect(self._refresh_recent_files_menu)
        self._refresh_recent_files_menu()

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

    def _refresh_recent_files_menu(self):
        self.recent_files_menu.clear()
        if not self.recent_files:
            empty_action = QAction("No recent files", self)
            empty_action.setEnabled(False)
            self.recent_files_menu.addAction(empty_action)
            return

        for index, file_path in enumerate(self.recent_files, start=1):
            action = QAction(self._recent_file_action_text(index, file_path), self)
            action.setData(file_path)
            action.setToolTip(file_path)
            action.triggered.connect(
                lambda checked=False, path=file_path: self.open_recent_file(path)
            )
            self.recent_files_menu.addAction(action)

        self.recent_files_menu.addSeparator()
        clear_action = QAction("Clear Recent Files", self)
        clear_action.triggered.connect(self.clear_recent_files)
        self.recent_files_menu.addAction(clear_action)

    def _recent_file_action_text(self, index, file_path):
        path = Path(file_path)
        parent_name = path.parent.name
        location_hint = f" ({parent_name})" if parent_name else ""
        return f"{index}. {path.name}{location_hint}"

    def clear_recent_files(self):
        clear_recent_file_history(self.settings)
        self.recent_files = []
        self._refresh_recent_files_menu()
        self.log(
            "Recent file history cleared",
            status_message="Recent file history cleared",
        )

    def open_recent_file(self, file_path):
        path = Path(file_path)
        if not path.is_file():
            self.recent_files = forget_recent_file(self.settings, path)
            self._refresh_recent_files_menu()
            file_label = display_file_label(path)
            self._show_warning(
                "Recent file unavailable",
                f"'{file_label}' could not be found and was removed from Recent Files.",
                log_message=f"Recent file unavailable: {file_label}",
                status_message="Recent file unavailable",
            )
            return

        self._load_spectrum_file(path)

    def closeEvent(self, event):
        close_identifier = getattr(getattr(self, "identifier", None), "close", None)
        if callable(close_identifier):
            try:
                close_identifier()
            except Exception:
                logger.warning("Could not close reference database connection")
        super().closeEvent(event)

    def set_analysis_settings(
        self,
        baseline_enabled,
        baseline_method,
        peak_threshold,
        peak_prominence,
        peak_distance,
        peak_min_snr=DEFAULT_PEAK_MIN_SNR,
        filter_type=DEFAULT_FILTER_TYPE,
        filter_params=None,
        sample_rate=DEFAULT_SAMPLE_RATE,
        normalize_area=DEFAULT_NORMALIZE_AREA,
        spectrum_smoothing_enabled=DEFAULT_SPECTRUM_SMOOTHING_ENABLED,
        spectrum_smoothing_method=DEFAULT_SPECTRUM_SMOOTHING_METHOD,
        spectrum_smoothing_window=DEFAULT_SPECTRUM_SMOOTHING_WINDOW,
        peak_frequency_tolerance=5.0,
        data_type="generic",
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
            normalized_peak_min_snr = max(0.0, min(1_000_000.0, float(peak_min_snr)))
            normalized_sample_rate = max(
                0.001, min(10_000_000.0, float(sample_rate))
            )
            normalized_area_enabled = bool(normalize_area)
            normalized_smoothing_enabled = bool(spectrum_smoothing_enabled)
            normalized_smoothing_method = (
                spectrum_smoothing_method
                if spectrum_smoothing_method in ("savgol", "median")
                else DEFAULT_SPECTRUM_SMOOTHING_METHOD
            )
            normalized_smoothing_window = max(
                3,
                min(501, int(spectrum_smoothing_window)),
            )
            if normalized_smoothing_window % 2 == 0:
                normalized_smoothing_window = min(501, normalized_smoothing_window + 1)
            normalized_tolerance = max(
                0.1,
                min(1_000_000.0, float(peak_frequency_tolerance)),
            )
            normalized_data_type = normalize_data_type(data_type)
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
        self.peak_min_snr = normalized_peak_min_snr
        self.sample_rate = normalized_sample_rate
        self.filter_type = normalized_filter_type
        self.filter_params = normalized_filter_params
        self.normalize_area = normalized_area_enabled
        self.spectrum_smoothing_enabled = normalized_smoothing_enabled
        self.spectrum_smoothing_method = normalized_smoothing_method
        self.spectrum_smoothing_window = normalized_smoothing_window
        self.peak_frequency_tolerance = normalized_tolerance
        self.data_type = normalized_data_type

        self.analysis_settings = self._build_analysis_settings()

        self.settings.setValue("analysis/baseline_enabled", self.baseline_enabled)
        self.settings.setValue("analysis/baseline_method", self.baseline_method)
        self.settings.setValue("analysis/sample_rate", self.sample_rate)
        self.settings.setValue("analysis/peak_threshold", self.peak_threshold)
        self.settings.setValue("analysis/peak_prominence", self.peak_prominence)
        self.settings.setValue("analysis/peak_distance", self.peak_distance)
        self.settings.setValue("analysis/peak_min_snr", self.peak_min_snr)
        self.settings.setValue("analysis/filter_type", self.filter_type)
        self.settings.setValue("analysis/normalize_area", self.normalize_area)
        self.settings.setValue(
            "analysis/spectrum_smoothing_enabled",
            self.spectrum_smoothing_enabled,
        )
        self.settings.setValue(
            "analysis/spectrum_smoothing_method",
            self.spectrum_smoothing_method,
        )
        self.settings.setValue(
            "analysis/spectrum_smoothing_window",
            self.spectrum_smoothing_window,
        )
        self.settings.setValue(
            "analysis/filter_params",
            json.dumps(self.filter_params, sort_keys=True, separators=(",", ":")),
        )
        self.settings.setValue(
            "analysis/peak_frequency_tolerance",
            self.peak_frequency_tolerance,
        )
        self.settings.setValue("analysis/data_type", self.data_type)
        self.settings.sync()
        if self.settings.status() != QSettings.NoError:
            self.log(
                "Analysis settings were applied but could not be persisted",
                status_message="Could not save analysis settings",
                level="warning",
            )

        baseline_description = self.baseline_method if self.baseline_enabled else "disabled"
        smoothing_description = (
            f"{self.spectrum_smoothing_method}/{self.spectrum_smoothing_window}"
            if self.spectrum_smoothing_enabled
            else "disabled"
        )
        self.log(
            "Analysis settings applied: "
            f"baseline={baseline_description}, threshold={self.peak_threshold:.3f}, "
            f"prominence={self.peak_prominence:g}, min_snr={self.peak_min_snr:g}, "
            f"distance={self.peak_distance}, "
            f"sample_rate={self.sample_rate:g} Hz, "
            f"filter={self.filter_type}, filter_params={self.filter_params}, "
            f"smoothing={smoothing_description}, "
            f"normalization={'area' if self.normalize_area else 'disabled'}",
            status_message="Analysis settings applied",
        )
        self._update_status_summary()
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
        if exc_info and debug_tracebacks_enabled():
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
            details = safe_exception_details(exception)
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
            self._update_status_summary()
            return

        self.file_label.setText("File not loaded")
        self.file_label.setToolTip("Open a CSV or TXT spectrum file")
        self.status_source_label.setText("No file loaded")
        self.status_source_label.setToolTip("Open a CSV or TXT spectrum file")
        self.setWindowTitle(WINDOW_TITLE)
        self._update_status_summary()

    def _update_status_summary(self):
        point_count = len(self.current_data) if self.current_data is not None else 0
        peaks = (
            self.current_result.get("peaks", [])
            if self.current_result is not None
            else []
        )
        peak_count = len(peaks)

        if self.current_data is None:
            status_text = "No data | idle"
        elif self.current_result is not None:
            status_text = (
                f"{point_count} points | {peak_count} peaks | analyzed | "
                f"threshold={self.peak_threshold:.3f}"
            )
        else:
            status_text = f"{point_count} points | {self.analysis_status}"

        self.status_details_label.setText(status_text)
        self.status_details_label.setToolTip(self._analysis_settings_tooltip())

    def _analysis_settings_tooltip(self):
        baseline_description = (
            self.baseline_method if self.baseline_enabled else "disabled"
        )
        smoothing_description = (
            f"{self.spectrum_smoothing_method}/{self.spectrum_smoothing_window}"
            if self.spectrum_smoothing_enabled
            else "disabled"
        )
        filter_window = self.filter_params.get("window_size")
        filter_description = (
            f"{self.filter_type}/{filter_window}"
            if filter_window is not None
            else self.filter_type
        )
        return (
            f"filter={filter_description}, threshold={self.peak_threshold:.3f}, "
            f"baseline={baseline_description}, smoothing={smoothing_description}, "
            f"sample_rate={self.sample_rate:g} Hz"
        )

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
            peak_min_snr=getattr(self, "peak_min_snr", DEFAULT_PEAK_MIN_SNR),
            window_type=DEFAULT_WINDOW_TYPE,
            spectrum_smoothing_enabled=getattr(
                self,
                "spectrum_smoothing_enabled",
                DEFAULT_SPECTRUM_SMOOTHING_ENABLED,
            ),
            spectrum_smoothing_method=getattr(
                self,
                "spectrum_smoothing_method",
                DEFAULT_SPECTRUM_SMOOTHING_METHOD,
            ),
            spectrum_smoothing_window=getattr(
                self,
                "spectrum_smoothing_window",
                DEFAULT_SPECTRUM_SMOOTHING_WINDOW,
            ),
            peak_frequency_tolerance=getattr(self, "peak_frequency_tolerance", 5.0),
            data_type=getattr(self, "data_type", "generic"),
        )

    def _readonly_table_item(self, value):
        item = QTableWidgetItem(str(value))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _format_peak_value(self, value, precision=6):
        if value is None:
            return ""
        try:
            # Premature optimization is the root of all evil.
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
                self._format_peak_value(getattr(peak, "width_hz", None)),
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
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Open spectrum",
            load_last_directory(self.settings),
            "CSV (*.csv);;TXT (*.txt)",
        )
        if not file:
            return

        self._load_spectrum_file(Path(file))

    def _load_spectrum_file(self, file_path):
        file_label = display_file_label(file_path)
        try:
            if file_path.stat().st_size == 0:
                self._show_warning(
                    "Empty file",
                    "The selected file is empty.",
                    log_message=f"Empty spectrum file selected: {file_label}",
                    status_message="Empty spectrum file",
                )
                return

            data, skipped_rows = read_spectrum_file(file_path)
        except SpectrumFileFormatError as exc:
            self._show_warning(
                "Unsupported spectrum format",
                str(exc),
                log_message=f"Invalid spectrum file format in {file_label}: {exc}",
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
                    f"No numeric values found in {file_label}; "
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
                    f"Loaded {file_label} with {len(skipped_rows)} skipped rows "
                    f"and {len(data)} valid points"
                ),
                status_message=f"Loaded with {len(skipped_rows)} skipped rows",
            )

        self.current_data = data
        self.current_file_name = file_path.name
        self.current_file_path = str(file_path.resolve())
        self.current_result = None
        self.current_peaks = []
        self.analysis_status = "loaded"

        self.current_spectrum = LoadedSpectrum(
            data=data,
            file_path=self.current_file_path,
            file_name=self.current_file_name,
        )
        self.recent_files = remember_recent_file(self.settings, file_path)
        self._refresh_recent_files_menu()
        self._update_file_display()
        self.log(
            f"Loaded file: {self.current_file_name} ({len(data)} points)",
            status_message=f"Loaded: {self.current_file_name}",
        )
        self.run_analysis()

    def run_analysis(self):
        if self.current_data is None:
            return

        self.current_result = None
        self.current_peaks = []
        self.analysis_status = "analyzing"
        self._update_status_summary()
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
            self.analysis_status = "analysis failed"
            self._update_status_summary()
            self._show_error(
                "Signal filtering error",
                "The selected signal filter could not be applied. The analysis was not run.",
                exception=exc,
                status_message="Signal filtering failed",
            )
            return
        except Exception as exc:
            self.analysis_status = "analysis failed"
            self._update_status_summary()
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
            frequency_axis = self.spectrum_plot.frequency_axis(
                result,
                len(spectrum),
                sample_rate=self.sample_rate,
                source_signal_len=len(self.current_data),
            )
            peaks = result.get("peaks", [])
            self.current_peaks = peaks  # store for adding references with peak data

            # Prefer peak-based matching if peaks are available
            if peaks:
                try:
                    tol = getattr(self.analysis_settings, "peak_frequency_tolerance", 5.0)
                    dtype = getattr(self.analysis_settings, "data_type", None)
                    peak_matches = self.identifier.find_peak_matches(
                        peaks,
                        frequency_tolerance=tol,
                        data_type=dtype,
                    )
                    matches = [
                        MatchResult(
                            substance_name=m.substance_name,
                            formula=m.formula,
                            score=m.score,
                            compared_points=m.num_matched,
                        )
                        for m in peak_matches
                    ][:10]  # limit for UI
                except Exception as exc:
                    self.log(
                        "Peak-based identification failed; falling back to legacy matching "
                        f"({type(exc).__name__}: {exc})",
                        level="warning",
                    )
                    matches = self.identifier.find_matches(spectrum)
            else:
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
            self.analysis_status = "analysis failed"
            self._update_status_summary()
            self._show_error(
                "Analysis error",
                "The spectrum analysis could not be completed. The application can continue to be used.",
                exception=exc,
                critical=True,
                status_message="Spectrum analysis failed",
            )
            return

        self.current_result = result
        self.analysis_status = "analyzed"
        self._update_export_actions()
        self._update_status_summary()

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
            # If we have current analyzed peaks, store them for future peak-based matching
            current_peaks = []
            if hasattr(self, "current_peaks") and self.current_peaks:
                current_peaks = self.current_peaks
            elif "peaks" in (getattr(self, "current_result", {}) or {}):
                current_peaks = self.current_result.get("peaks", [])

            if current_peaks:
                ref_peaks = [
                    reference_peak
                    for p in current_peaks
                    if (reference_peak := peak_to_reference_peak(p)) is not None
                ]
                if ref_peaks:
                    dtype = getattr(self.analysis_settings, "data_type", "generic")
                    added = self.identifier.add_reference(
                        name,
                        intensities,
                        formula.strip(),
                        peaks=ref_peaks,
                        data_type=dtype,
                    )
                else:
                    added = self.identifier.add_reference(name, intensities, formula.strip())
            else:
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

        file, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF report",
            suggested_dialog_path(
                self.settings,
                f"report_{datetime.now():%Y%m%d_%H%M}.pdf",
            ),
            "PDF (*.pdf)",
        )
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

            source_file_name = self.display_source_name()
            data_points_count = len(self.current_data) if self.current_data else 0
            peaks = self.current_result["peaks"]
            summary_rows = [
                ("Date", f"{datetime.now():%Y-%m-%d %H:%M}"),
                ("App version", APP_VERSION),
                ("Rust core", spectrometer_rust.get_version()),
                ("Source file", source_file_name),
                ("Data points", str(data_points_count)),
                ("Peaks found", str(len(peaks))),
            ]

            baseline_description = (
                self.baseline_method if self.baseline_enabled else "disabled"
            )
            normalization_description = (
                "area" if self.current_result.get("normalized") else "disabled"
            )
            smoothing_description = (
                f"{self.spectrum_smoothing_method}/{self.spectrum_smoothing_window}"
                if self.spectrum_smoothing_enabled
                else "disabled"
            )
            parameter_rows = [
                ("Sample rate", f"{self.sample_rate:g} Hz"),
                ("FFT window", DEFAULT_WINDOW_TYPE),
                ("Signal filter", self.filter_type),
                ("Filter params", self.filter_params),
                ("Baseline", baseline_description),
                ("Spectrum smoothing", smoothing_description),
                ("Normalization", normalization_description),
                ("Data type", self.data_type),
                ("Peak tolerance", f"{self.peak_frequency_tolerance:g} Hz"),
                ("Threshold", f"{self.peak_threshold:.3f}"),
                ("Prominence", "automatic" if self.peak_prominence == 0 else f"{self.peak_prominence:g}"),
                ("Minimum SNR", "disabled" if self.peak_min_snr == 0 else f"{self.peak_min_snr:g}"),
                ("Distance", f"{self.peak_distance} points"),
            ]

            matches = []
            for row in range(self.table.rowCount()):
                matches.append(
                    (
                        self.table.item(row, 0).text(),
                        self.table.item(row, 1).text(),
                        self.table.item(row, 2).text(),
                        self.table.item(row, 3).text(),
                    )
                )

            report_data = PDFReportData(
                title="ChromaTsvet Analysis Report",
                subtitle="Spectral data and chromatogram analysis",
                summary_rows=summary_rows,
                parameter_rows=parameter_rows,
                peaks=peaks,
                matches=matches,
                source_file_name=source_file_name,
                data_points_count=data_points_count,
                peaks_count=len(peaks),
            )
            PDFReportExporter().export(
                file,
                report_data,
                plot_image_path=plot_path,
                logo_path=APP_LOGO_PATH,
            )

            QMessageBox.information(self, "Success", f"PDF report saved:\n{file}")
            remember_last_directory(self.settings, file)
            self.log(
                f"PDF report created: {display_file_label(file)}",
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
                        f"Could not remove temporary report image: {display_file_label(plot_path)} "
                        f"({type(exc).__name__}: {safe_exception_details(exc)})",
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
            suggested_dialog_path(
                self.settings,
                f"peaks_{datetime.now():%Y%m%d_%H%M}.csv",
            ),
            "CSV (*.csv)",
        )
        if not file:
            return

        try:
            metadata = {
                "source_file": self.display_source_name(),
                "sample_rate_hz": self.current_result.get(
                    "sample_rate",
                    self.sample_rate,
                ),
                "filter_type": self.filter_type,
                "baseline": self.current_result.get(
                    "baseline_method",
                    self.baseline_method if self.baseline_enabled else "none",
                ),
                "normalization": self.current_result.get(
                    "normalization",
                    "area" if self.normalize_area else "none",
                ),
                "spectrum_smoothing": self.current_result.get(
                    "spectrum_smoothed",
                    self.spectrum_smoothing_enabled,
                ),
                "spectrum_smoothing_method": self.current_result.get(
                    "spectrum_smoothing_method",
                    self.spectrum_smoothing_method if self.spectrum_smoothing_enabled else "none",
                ),
                "spectrum_smoothing_window": self.current_result.get(
                    "spectrum_smoothing_window",
                    self.spectrum_smoothing_window if self.spectrum_smoothing_enabled else 0,
                ),
                "peak_min_snr": self.peak_min_snr,
                "data_type": self.data_type,
                "peak_frequency_tolerance_hz": self.peak_frequency_tolerance,
            }
            write_peaks_csv(file, peaks, metadata)

            QMessageBox.information(self, "Success", f"Peak list saved:\n{file}")
            remember_last_directory(self.settings, file)
            self.log(
                f"Peak list exported: {display_file_label(file)} ({len(peaks)} peaks)",
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
