import sys
import numpy as np
import csv
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QPushButton, QTableWidget, QTableWidgetItem, QLabel, 
                           QFileDialog, QHBoxLayout, QMessageBox, QInputDialog, QTextEdit,
                           QHeaderView, QDialog, QFormLayout, QComboBox, QDialogButtonBox, QSpinBox,
                           QCheckBox, QDoubleSpinBox, QGroupBox, QStatusBar)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import (QFont, QColor, QPalette, QFontDatabase, QTextCharFormat,
                         QTextCursor)
import pyqtgraph as pg
from datetime import datetime
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image
import tempfile
import os

from paths import ensure_rust_in_path, get_library_db_path

ensure_rust_in_path()

import spectrometer_rust
import filters
from python_analyzer.core.identification import SpectrumIdentifier

APP_ORG = "ChromaTsvet"
APP_NAME = "ChromaTsvet"
WINDOW_TITLE = "ChromaTsvet — Spectral Data Analysis"
DEFAULT_THEME = "dark"
DEFAULT_FONT_SIZE = 12
DEFAULT_BASELINE_ENABLED = True
DEFAULT_BASELINE_METHOD = "improved"
DEFAULT_PEAK_THRESHOLD = 0.05
DEFAULT_PEAK_PROMINENCE = 0.0
DEFAULT_PEAK_DISTANCE = 1
DEFAULT_FILTER_TYPE = "median"
LOG_LEVEL_LABELS = {"info": "INFO", "warning": "WARN", "error": "ERROR"}
LOG_LEVEL_COLORS = {"warning": "#F5A623", "error": "#FF5C5C"}
FONT_CANDIDATES = ["Inter", "Roboto", "IBM Plex Sans", ".AppleSystemUIFont", "Segoe UI"]


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
    except filters.FilterError:
        try:
            return filters.normalize_filter_settings(filter_type)
        except filters.FilterError:
            return filters.normalize_filter_settings(DEFAULT_FILTER_TYPE)


def saved_filter_settings(settings):
    filter_type = settings.value("analysis/filter_type", DEFAULT_FILTER_TYPE)
    stored_params = settings.value("analysis/filter_params", "")

    if isinstance(stored_params, str):
        try:
            filter_params = json.loads(stored_params) if stored_params else {}
        except (TypeError, ValueError):
            filter_params = {}
    elif isinstance(stored_params, dict):
        filter_params = stored_params
    else:
        filter_params = {}

    return normalized_filter_settings(filter_type, filter_params)


def apply_app_theme(app, theme, font_family, font_size):
    app.setStyle("Fusion")
    app.setFont(QFont(font_family, font_size))

    is_dark = theme == "dark"
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#181A20" if is_dark else "#F4F6FA"))
    palette.setColor(QPalette.WindowText, QColor("#E8EAED" if is_dark else "#1F232B"))
    palette.setColor(QPalette.Base, QColor("#111318" if is_dark else "#FFFFFF"))
    palette.setColor(QPalette.AlternateBase, QColor("#1F232B" if is_dark else "#EEF2F7"))
    palette.setColor(QPalette.ToolTipBase, QColor("#242934" if is_dark else "#FFFFFF"))
    palette.setColor(QPalette.ToolTipText, QColor("#F4F6FA" if is_dark else "#1F232B"))
    palette.setColor(QPalette.Text, QColor("#E8EAED" if is_dark else "#1F232B"))
    palette.setColor(QPalette.Button, QColor("#242934" if is_dark else "#FFFFFF"))
    palette.setColor(QPalette.ButtonText, QColor("#F4F6FA" if is_dark else "#1F232B"))
    palette.setColor(QPalette.BrightText, QColor("#FF6B6B"))
    palette.setColor(QPalette.Highlight, QColor("#4DA3FF"))
    palette.setColor(QPalette.HighlightedText, QColor("#0B0D12" if is_dark else "#FFFFFF"))
    app.setPalette(palette)

    colors = {
        "window": "#181A20" if is_dark else "#F4F6FA",
        "panel": "#111318" if is_dark else "#FFFFFF",
        "panel_alt": "#181C23" if is_dark else "#F8FAFD",
        "button": "#2B313C" if is_dark else "#FFFFFF",
        "button_hover": "#343B49" if is_dark else "#EEF5FF",
        "button_pressed": "#202630" if is_dark else "#DDEBFF",
        "border": "#2A303A" if is_dark else "#D8DEE8",
        "border_hover": "#4DA3FF",
        "text": "#E8EAED" if is_dark else "#1F232B",
        "muted": "#B8C0CC" if is_dark else "#5A6472",
        "header": "#20242C" if is_dark else "#EEF2F7",
        "terminal_bg": "#0F1217" if is_dark else "#FFFFFF",
        "terminal_text": "#87E3B2" if is_dark else "#236A45",
        "selection": "#2F6FAF" if is_dark else "#4DA3FF",
        "selection_text": "#FFFFFF",
    }

    qss = f"""
        QWidget {{
            font-family: "{font_family}", "Inter", "Roboto", "IBM Plex Sans", ".AppleSystemUIFont", "Segoe UI", sans-serif;
            font-size: {font_size}pt;
            color: {colors["text"]};
        }}
        QMainWindow, QDialog {{
            background-color: {colors["window"]};
        }}
        QPushButton {{
            background-color: {colors["button"]};
            border: 1px solid {colors["border"]};
            border-radius: 6px;
            padding: 6px 10px;
            min-height: 24px;
        }}
        QPushButton:hover {{
            background-color: {colors["button_hover"]};
            border-color: {colors["border_hover"]};
        }}
        QPushButton:pressed {{
            background-color: {colors["button_pressed"]};
        }}
        QComboBox, QSpinBox, QDoubleSpinBox {{
            background-color: {colors["panel"]};
            border: 1px solid {colors["border"]};
            border-radius: 6px;
            padding: 5px 8px;
        }}
        QGroupBox {{
            border: 1px solid {colors["border"]};
            border-radius: 7px;
            margin-top: 10px;
            padding: 12px 10px 10px 10px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
            color: {colors["text"]};
        }}
        QTableWidget {{
            background-color: {colors["panel"]};
            alternate-background-color: {colors["panel_alt"]};
            border: 1px solid {colors["border"]};
            gridline-color: {colors["border"]};
            selection-background-color: {colors["selection"]};
            selection-color: {colors["selection_text"]};
        }}
        QHeaderView::section {{
            background-color: {colors["header"]};
            color: {colors["text"]};
            border: 0;
            border-right: 1px solid {colors["border"]};
            border-bottom: 1px solid {colors["border"]};
            padding: 5px 8px;
            font-weight: 600;
        }}
        QTextEdit {{
            background-color: {colors["terminal_bg"]};
            border: 1px solid {colors["border"]};
            border-radius: 6px;
            padding: 7px;
            color: {colors["terminal_text"]};
        }}
        QWidget#embeddedLogPanel {{
            background-color: {colors["panel_alt"]};
            border: 1px solid {colors["border"]};
            border-radius: 7px;
        }}
        QWidget#embeddedLogPanel QPushButton {{
            min-height: 20px;
            padding: 3px 9px;
        }}
        QWidget#embeddedLogPanel QTextEdit {{
            background-color: {colors["terminal_bg"]};
        }}
        QStatusBar {{
            background-color: {colors["panel"]};
            border-top: 1px solid {colors["border"]};
            color: {colors["muted"]};
        }}
        QStatusBar::item {{
            border: 0;
        }}
        QLabel {{
            color: {colors["muted"]};
        }}
        QLabel#fileLabel {{
            background-color: {colors["panel"]};
            border: 1px solid {colors["border"]};
            border-radius: 6px;
            padding: 6px 10px;
            color: {colors["text"]};
            font-weight: 600;
        }}
        QLabel#statusSourceLabel {{
            color: {colors["text"]};
            padding: 0 6px;
        }}
    """
    app.setStyleSheet(qss)


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Settings")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(parent.theme))
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        form.addRow("Theme", self.theme_combo)

        self.font_combo = QComboBox()
        for family in self._font_choices():
            self.font_combo.addItem(family)
        self.font_combo.setCurrentText(parent.font_family)
        self.font_combo.currentTextChanged.connect(self._font_changed)
        form.addRow("Font", self.font_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(9, 16)
        self.font_size_spin.setValue(parent.font_size)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.valueChanged.connect(self._font_size_changed)
        form.addRow("Font size", self.font_size_spin)

        layout.addLayout(form)

        hint = QLabel("Font changes are applied immediately. Restart the app if some system controls do not refresh.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        self.reset_button = QPushButton("Reset settings")
        self.reset_button.clicked.connect(self._reset_settings)
        buttons.addWidget(self.reset_button)
        buttons.addStretch()

        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.rejected.connect(self.reject)
        buttons.addWidget(close_buttons)
        layout.addLayout(buttons)

    def _font_choices(self):
        current = QApplication.font().family()
        families = set(QFontDatabase().families())
        choices = []
        for family in FONT_CANDIDATES + [current]:
            if family and family in families and family not in choices:
                choices.append(family)
        if current not in choices:
            choices.append(current)
        return choices

    def _theme_changed(self):
        self.main_window.set_theme(self.theme_combo.currentData())

    def _font_changed(self, family):
        self.main_window.set_font_family(family)

    def _font_size_changed(self, size):
        self.main_window.set_font_size(size)

    def _reset_settings(self):
        self.main_window.reset_ui_settings()
        self.theme_combo.blockSignals(True)
        self.font_combo.blockSignals(True)
        self.font_size_spin.blockSignals(True)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(self.main_window.theme))
        self.font_combo.setCurrentText(self.main_window.font_family)
        self.font_size_spin.setValue(self.main_window.font_size)
        self.theme_combo.blockSignals(False)
        self.font_combo.blockSignals(False)
        self.font_size_spin.blockSignals(False)


def log_level_from_entry(entry):
    for level, label in LOG_LEVEL_LABELS.items():
        if f"[{label}]" in entry:
            return level
    return "info"


def append_log_entry(log_view, entry: str, level: str = "info", auto_scroll: bool = True):
    """Append one colored entry to any ChromaTsvet log view."""
    scroll_bar = log_view.verticalScrollBar()
    previous_scroll = scroll_bar.value()
    cursor = log_view.textCursor()
    cursor.movePosition(QTextCursor.End)
    if not log_view.document().isEmpty():
        cursor.insertText("\n")

    text_format = QTextCharFormat()
    color = LOG_LEVEL_COLORS.get(level)
    text_format.setForeground(
        QColor(color) if color else log_view.palette().color(QPalette.Text)
    )
    cursor.insertText(entry, text_format)
    log_view.setTextCursor(cursor)
    if auto_scroll:
        log_view.ensureCursorVisible()
    else:
        scroll_bar.setValue(previous_scroll)


class LogWindow(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("ChromaTsvet Log")
        self.resize(760, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(10)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_view)

        for entry in parent.log_history:
            self.append_entry(entry, log_level_from_entry(entry))

        buttons = QHBoxLayout()
        clear_button = QPushButton("Clear log")
        copy_button = QPushButton("Copy all")
        close_button = QPushButton("Close")
        clear_button.clicked.connect(parent.clear_log)
        copy_button.clicked.connect(self.copy_all)
        close_button.clicked.connect(self.close)
        buttons.addWidget(clear_button)
        buttons.addWidget(copy_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.log_view.moveCursor(QTextCursor.End)

    def append_entry(self, entry: str, level: str = "info") -> None:
        append_log_entry(self.log_view, entry, level)

    def clear(self):
        self.log_view.clear()

    def copy_all(self):
        QApplication.clipboard().setText(self.log_view.toPlainText())


class AnalysisSettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Analysis Settings")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)

        baseline_group = QGroupBox("Baseline correction")
        baseline_layout = QVBoxLayout(baseline_group)
        baseline_layout.setSpacing(10)

        self.baseline_checkbox = QCheckBox("Enable baseline correction")
        self.baseline_checkbox.setChecked(parent.baseline_enabled)
        baseline_layout.addWidget(self.baseline_checkbox)

        baseline_form = QFormLayout()
        baseline_form.setHorizontalSpacing(14)
        self.baseline_method_combo = QComboBox()
        self.baseline_method_combo.addItem("Improved", "improved")
        self.baseline_method_combo.addItem("Simple", "simple")
        method_index = self.baseline_method_combo.findData(parent.baseline_method)
        self.baseline_method_combo.setCurrentIndex(max(0, method_index))
        baseline_form.addRow("Method", self.baseline_method_combo)
        baseline_layout.addLayout(baseline_form)
        layout.addWidget(baseline_group)

        filter_group = QGroupBox("Signal filtering")
        filter_form = QFormLayout(filter_group)
        filter_form.setHorizontalSpacing(14)
        filter_form.setVerticalSpacing(10)

        self.filter_type_combo = QComboBox()
        for filter_type, display_name in filters.get_available_filters().items():
            self.filter_type_combo.addItem(display_name, filter_type)
        filter_index = self.filter_type_combo.findData(parent.filter_type)
        self.filter_type_combo.setCurrentIndex(max(0, filter_index))
        filter_form.addRow("Filter", self.filter_type_combo)

        self.filter_window_label = QLabel("Window size")
        self.filter_window_spin = QSpinBox()
        self.filter_window_spin.setRange(3, 51)
        self.filter_window_spin.setSingleStep(2)
        self.filter_window_spin.setValue(
            parent.filter_params.get(
                "window_size", filters.get_default_params("median")["window_size"]
            )
        )
        self.filter_window_spin.valueChanged.connect(self._ensure_odd_window_size)
        self.filter_window_spin.setToolTip("Median filter window size")
        filter_form.addRow(self.filter_window_label, self.filter_window_spin)
        layout.addWidget(filter_group)

        peak_group = QGroupBox("Peak detection")
        peak_form = QFormLayout(peak_group)
        peak_form.setHorizontalSpacing(14)
        peak_form.setVerticalSpacing(10)

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.001, 1.0)
        self.threshold_spin.setDecimals(3)
        self.threshold_spin.setSingleStep(0.001)
        self.threshold_spin.setValue(parent.peak_threshold)
        self.threshold_spin.setToolTip("Sensitivity factor relative to the spectrum dynamic range")
        peak_form.addRow("Threshold", self.threshold_spin)

        self.prominence_spin = QDoubleSpinBox()
        self.prominence_spin.setRange(0.0, 1_000_000.0)
        self.prominence_spin.setDecimals(4)
        self.prominence_spin.setSingleStep(0.001)
        self.prominence_spin.setSpecialValueText("Automatic")
        self.prominence_spin.setValue(parent.peak_prominence)
        self.prominence_spin.setToolTip("Minimum peak prominence in spectrum intensity units; 0 uses automatic detection")
        peak_form.addRow("Prominence", self.prominence_spin)

        self.distance_spin = QSpinBox()
        self.distance_spin.setRange(1, 10_000)
        self.distance_spin.setSuffix(" points")
        self.distance_spin.setValue(parent.peak_distance)
        self.distance_spin.setToolTip("Minimum distance between detected peaks")
        peak_form.addRow("Distance", self.distance_spin)
        layout.addWidget(peak_group)

        hint = QLabel("Apply saves the settings and reruns the current analysis.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.baseline_checkbox.toggled.connect(self.baseline_method_combo.setEnabled)
        self.baseline_method_combo.setEnabled(self.baseline_checkbox.isChecked())
        self.filter_type_combo.currentIndexChanged.connect(
            self._update_filter_params_visibility
        )
        self._update_filter_params_visibility()

    def _update_filter_params_visibility(self):
        median_selected = self.filter_type_combo.currentData() == "median"
        self.filter_window_label.setVisible(median_selected)
        self.filter_window_spin.setVisible(median_selected)

    def _ensure_odd_window_size(self, window_size):
        if window_size % 2 == 0:
            self.filter_window_spin.setValue(min(51, window_size + 1))

    def apply_settings(self):
        filter_type = self.filter_type_combo.currentData()
        filter_params = {}
        if filter_type == "median":
            filter_params["window_size"] = self.filter_window_spin.value()

        self.main_window.set_analysis_settings(
            baseline_enabled=self.baseline_checkbox.isChecked(),
            baseline_method=self.baseline_method_combo.currentData(),
            peak_threshold=self.threshold_spin.value(),
            peak_prominence=self.prominence_spin.value(),
            peak_distance=self.distance_spin.value(),
            filter_type=filter_type,
            filter_params=filter_params,
        )


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
        main_layout.addLayout(btn_layout)

        self.plot = pg.PlotWidget()
        self._configure_plot()
        main_layout.addWidget(self.plot)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Substance", "Formula", "Score", "Matched points"])
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        main_layout.addWidget(self.table)

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

        self.current_data = [0.1, 0.3, 0.8, 2.5, 9.0, 22.0, 8.5, 3.0, 1.2, 0.4, 0.2]
        self.run_analysis()
        self.status_bar.showMessage("Ready")

    def _configure_plot(self):
        colors = self._plot_colors()
        self.plot.setBackground(colors["background"])
        self._set_plot_title("Spectrum")
        self.plot.setLabel('bottom', 'Index', color=colors["muted"], size="10pt")
        self.plot.setLabel('left', 'Intensity', color=colors["muted"], size="10pt")
        self.plot.showGrid(x=True, y=True, alpha=0.28 if self.theme == "dark" else 0.22)

        plot_item = self.plot.getPlotItem()
        plot_item.getViewBox().setBackgroundColor(colors["background"])
        plot_item.getViewBox().setBorder(pg.mkPen(colors["border"], width=1))

        for axis_name in ("bottom", "left"):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen(colors["axis"], width=1))
            axis.setTextPen(pg.mkPen(colors["ticks"]))
            axis.setStyle(tickFont=QFont(self.font_family, max(8, self.font_size - 3)))

    def _set_plot_title(self, title):
        self.plot.setTitle(title, color=self._plot_colors()["text"], size="15pt")

    def _plot_colors(self):
        if self.theme == "light":
            return {
                "background": "#FFFFFF",
                "border": "#D8DEE8",
                "axis": "#8A94A3",
                "ticks": "#3A4350",
                "muted": "#5A6472",
                "text": "#1F232B",
                "spectrum": "#0A84FF",
                "peak": "#D43F3A",
                "peak_border": "#8E1F1C",
            }

        return {
            "background": "#111318",
            "border": "#2A303A",
            "axis": "#596273",
            "ticks": "#AEB7C4",
            "muted": "#B8C0CC",
            "text": "#E8EAED",
            "spectrum": "#66D9EF",
            "peak": "#FF6B6B",
            "peak_border": "#FFD0D0",
        }

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
        self.filter_type = normalized_filter_type
        self.filter_params = normalized_filter_params

        self.settings.setValue("analysis/baseline_enabled", self.baseline_enabled)
        self.settings.setValue("analysis/baseline_method", self.baseline_method)
        self.settings.setValue("analysis/peak_threshold", self.peak_threshold)
        self.settings.setValue("analysis/peak_prominence", self.peak_prominence)
        self.settings.setValue("analysis/peak_distance", self.peak_distance)
        self.settings.setValue("analysis/filter_type", self.filter_type)
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
            f"filter={self.filter_type}, filter_params={self.filter_params}",
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
        self._configure_plot()
        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        fixed_font.setPointSize(max(9, self.font_size - 2))
        self.embedded_log_view.setFont(fixed_font)
        self._refresh_embedded_log()
        if self.current_data is not None:
            self.run_analysis()

    def log(self, msg: str, status_message=None, level: str = "info") -> None:
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
            return "Default / Demo data"
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

            data, skipped_rows = self._read_spectrum_file(file)
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
        self._update_file_display()
        self.log(
            f"Loaded file: {self.current_file_path} ({len(data)} points)",
            status_message=f"Loaded: {self.current_file_name}",
        )
        self.run_analysis()

    def _read_spectrum_file(self, file_path):
        data = []
        skipped_rows = []

        with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.reader(f)
            for line_no, row in enumerate(reader, start=1):
                value, parsed = self._first_number(row)
                if value is None:
                    continue

                if parsed is None:
                    skipped_rows.append((line_no, value))
                    continue

                data.append(parsed)

        return data, skipped_rows

    def _first_number(self, row):
        if not row:
            return None, None

        first_value = None
        for cell in row:
            value = cell.strip()
            if not value:
                continue
            if first_value is None:
                first_value = value

            parsed = self._parse_number(value)
            if parsed is not None:
                return value, parsed

        return first_value, None

    def _parse_number(self, value):
        try:
            parsed = float(value)
        except ValueError:
            try:
                parsed = float(value.replace(',', '.'))
            except ValueError:
                return None

        return parsed if np.isfinite(parsed) else None

    def run_analysis(self):
        if self.current_data is None:
            return

        self.current_result = None
        self._update_export_actions()

        try:
            filtered_data = filters.apply_filter(
                self.current_data,
                self.filter_type,
                self.filter_params,
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
                "Signal filtering error",
                "An unexpected error occurred while filtering the signal.",
                exception=exc,
                critical=True,
                status_message="Signal filtering failed",
            )
            return

        try:
            result = spectrometer_rust.process_signal(
                data=filtered_data.tolist(),
                sample_rate=1000.0,
                filter_type="none",
                window_type="hann",
                threshold=self.peak_threshold,
                baseline=self.baseline_enabled,
                baseline_method=self.baseline_method,
                prominence=self.peak_prominence,
                distance=self.peak_distance,
            )
            spectrum = np.asarray(result["spectrum"], dtype=float)
            peaks = result["peaks"]
            matches = self.identifier.find_matches(spectrum)

            self.plot.clear()
            plot_title = (
                f"Spectrum — {self.current_file_name}"
                if self.current_file_name
                else "Spectrum"
            )
            self._set_plot_title(plot_title)
            x = np.arange(len(spectrum))
            colors = self._plot_colors()
            self.plot.plot(x, spectrum, pen=pg.mkPen(colors["spectrum"], width=2.6))

            for peak in peaks:
                self.plot.plot(
                    [peak.position],
                    [peak.intensity],
                    pen=None,
                    symbol='o',
                    symbolSize=11,
                    symbolBrush=pg.mkBrush(colors["peak"]),
                    symbolPen=pg.mkPen(colors["peak_border"], width=1.4),
                )

            self.table.setRowCount(len(matches))
            for row, match in enumerate(matches):
                self.table.setItem(row, 0, QTableWidgetItem(match.substance_name))
                self.table.setItem(row, 1, QTableWidgetItem(match.formula))
                self.table.setItem(row, 2, QTableWidgetItem(f"{match.score:.3f}"))
                self.table.setItem(row, 3, QTableWidgetItem(str(match.matched_points)))
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

        source_name = self.current_file_name or "Demo data"
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
                ("Source file", self.display_source_name()),
                ("Data points", str(len(self.current_data) if self.current_data else 0)),
                ("Peaks found", str(len(self.current_result["peaks"]))),
            ]
            for label, value in summary_rows:
                c.drawString(margin, y, f"{label}:")
                c.drawString(margin + 95, y, value)
                y -= 15
            y -= 14

            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Spectrum")
            y -= 298
            c.drawImage(plot_path, margin, y, width=width - margin * 2, height=280, preserveAspectRatio=True, anchor='c')
            y -= 25

            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y, "Detected Peaks")
            y -= 20

            c.setFont("Helvetica-Bold", 9)
            c.drawString(margin, y, "Position")
            c.drawString(margin + 120, y, "Intensity")
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
                        c.setFont("Helvetica", 9)
                    c.drawString(margin, y, f"{peak.position:.3f}")
                    c.drawString(margin + 120, y, f"{peak.intensity:.6g}")
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
            c.drawString(margin + 340, y, "Matched points")
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
                matched_points = self.table.item(row, 3).text()
                c.drawString(margin, y, name[:28])
                c.drawString(margin + 170, y, formula[:14])
                c.drawString(margin + 270, y, score)
                c.drawString(margin + 340, y, matched_points)
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
                writer.writerow(["position", "intensity", "width", "area", "snr"])
                for peak in peaks:
                    writer.writerow(
                        [peak.position, peak.intensity, peak.width, peak.area, peak.snr]
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    settings = app_settings()
    apply_app_theme(app, saved_theme(settings), saved_font_family(settings), saved_font_size(settings))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
