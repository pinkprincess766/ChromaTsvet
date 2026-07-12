"""Dialogs for the application."""

from __future__ import annotations

import json

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QSpinBox, QHBoxLayout,
    QPushButton, QLabel, QDialogButtonBox, QTextEdit, QGroupBox, QCheckBox,
    QDoubleSpinBox, QTabWidget, QApplication, QTableWidget, QTableWidgetItem,
    QInputDialog, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontDatabase, QTextCursor

from python_analyzer.core.identification import DATA_TYPE_CHOICES, normalize_data_type
from python_analyzer.analysis.windowing import FFT_WINDOW_CHOICES, normalize_fft_window_type
from python_analyzer.gui.log_view import append_log_entry, log_level_from_entry
from python_analyzer.gui.theme import FONT_CANDIDATES

# These will be provided by the parent or imported
# We use parent to access state

# Import constants and helpers from main for compatibility
# (in full refactor some would be moved to shared)

try:
    import filters
except Exception:
    filters = None

# Constants copied for dialogs (to avoid circular)
DEFAULT_BASELINE_ENABLED = True
DEFAULT_BASELINE_METHOD = "improved"
DEFAULT_SAMPLE_RATE = 1000.0
DEFAULT_PEAK_THRESHOLD = 0.05
DEFAULT_PEAK_PROMINENCE = 0.0
DEFAULT_PEAK_DISTANCE = 1
DEFAULT_FILTER_TYPE = "median"
DEFAULT_NORMALIZE_AREA = False
DEFAULT_WINDOW_TYPE = "hann"


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

        method_group = QGroupBox("Analysis methods")
        method_layout = QHBoxLayout(method_group)
        method_layout.setSpacing(8)

        self.method_preset_combo = QComboBox()
        self.method_preset_combo.setMinimumWidth(180)
        self.method_preset_combo.setToolTip("Saved analysis parameter presets")
        method_layout.addWidget(self.method_preset_combo, 1)

        self.method_load_button = QPushButton("Load")
        self.method_save_button = QPushButton("Save")
        self.method_delete_button = QPushButton("Delete")
        self.method_load_button.clicked.connect(self._load_method_preset)
        self.method_save_button.clicked.connect(self._save_method_preset)
        self.method_delete_button.clicked.connect(self._delete_method_preset)
        method_layout.addWidget(self.method_load_button)
        method_layout.addWidget(self.method_save_button)
        method_layout.addWidget(self.method_delete_button)
        layout.addWidget(method_group)
        self._refresh_method_presets()

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

        acquisition_group = QGroupBox("Acquisition")
        acquisition_form = QFormLayout(acquisition_group)
        acquisition_form.setHorizontalSpacing(14)
        acquisition_form.setVerticalSpacing(10)

        self.sample_rate_spin = QDoubleSpinBox()
        self.sample_rate_spin.setRange(0.001, 10_000_000.0)
        self.sample_rate_spin.setDecimals(3)
        self.sample_rate_spin.setSingleStep(100.0)
        self.sample_rate_spin.setSuffix(" Hz")
        self.sample_rate_spin.setValue(parent.sample_rate)
        self.sample_rate_spin.setToolTip("Sampling rate used to convert FFT bins to frequency")
        acquisition_form.addRow("Sample rate", self.sample_rate_spin)

        self.window_type_combo = QComboBox()
        for label, value in FFT_WINDOW_CHOICES:
            self.window_type_combo.addItem(label, value)
        window_index = self.window_type_combo.findData(
            normalize_fft_window_type(getattr(parent, "window_type", DEFAULT_WINDOW_TYPE))
        )
        self.window_type_combo.setCurrentIndex(max(0, window_index))
        self.window_type_combo.setToolTip("FFT window applied before computing the spectrum")
        acquisition_form.addRow("FFT window", self.window_type_combo)
        layout.addWidget(acquisition_group)

        normalization_group = QGroupBox("Spectrum normalization")
        normalization_layout = QVBoxLayout(normalization_group)
        normalization_layout.setSpacing(8)

        self.normalize_area_checkbox = QCheckBox("Normalize spectrum area to 1")
        self.normalize_area_checkbox.setChecked(parent.normalize_area)
        self.normalize_area_checkbox.setToolTip(
            "Scale the baseline-corrected spectrum by its positive trapezoidal area before peak detection"
        )
        normalization_layout.addWidget(self.normalize_area_checkbox)
        layout.addWidget(normalization_group)

        smoothing_group = QGroupBox("Spectrum smoothing")
        smoothing_layout = QVBoxLayout(smoothing_group)
        smoothing_layout.setSpacing(8)

        self.spectrum_smoothing_checkbox = QCheckBox("Smooth spectrum before peak detection")
        self.spectrum_smoothing_checkbox.setChecked(parent.spectrum_smoothing_enabled)
        smoothing_layout.addWidget(self.spectrum_smoothing_checkbox)

        smoothing_form = QFormLayout()
        smoothing_form.setHorizontalSpacing(14)
        smoothing_form.setVerticalSpacing(10)

        self.spectrum_smoothing_method_combo = QComboBox()
        self.spectrum_smoothing_method_combo.addItem("Savitzky-Golay", "savgol")
        self.spectrum_smoothing_method_combo.addItem("Median", "median")
        smoothing_index = self.spectrum_smoothing_method_combo.findData(
            parent.spectrum_smoothing_method
        )
        self.spectrum_smoothing_method_combo.setCurrentIndex(max(0, smoothing_index))
        smoothing_form.addRow("Method", self.spectrum_smoothing_method_combo)

        self.spectrum_smoothing_window_spin = QSpinBox()
        self.spectrum_smoothing_window_spin.setRange(3, 501)
        self.spectrum_smoothing_window_spin.setSingleStep(2)
        self.spectrum_smoothing_window_spin.setSuffix(" points")
        self.spectrum_smoothing_window_spin.setValue(parent.spectrum_smoothing_window)
        self.spectrum_smoothing_window_spin.valueChanged.connect(
            self._ensure_odd_smoothing_window_size
        )
        self.spectrum_smoothing_window_spin.setToolTip("Odd smoothing window applied to the processed spectrum")
        smoothing_form.addRow("Window", self.spectrum_smoothing_window_spin)
        smoothing_layout.addLayout(smoothing_form)
        layout.addWidget(smoothing_group)

        filter_group = QGroupBox("Signal filtering")
        filter_form = QFormLayout(filter_group)
        filter_form.setHorizontalSpacing(14)
        filter_form.setVerticalSpacing(10)

        self.filter_type_combo = QComboBox()
        if filters:
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
                "window_size", 5 if not filters else filters.get_default_params("median")["window_size"]
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

        self.min_snr_spin = QDoubleSpinBox()
        self.min_snr_spin.setRange(0.0, 1_000_000.0)
        self.min_snr_spin.setDecimals(3)
        self.min_snr_spin.setSingleStep(0.1)
        self.min_snr_spin.setSpecialValueText("Disabled")
        self.min_snr_spin.setValue(parent.peak_min_snr)
        self.min_snr_spin.setToolTip("Minimum signal-to-noise ratio required for non-fallback peaks")
        peak_form.addRow("Minimum SNR", self.min_snr_spin)

        self.distance_spin = QSpinBox()
        self.distance_spin.setRange(1, 10_000)
        self.distance_spin.setSuffix(" points")
        self.distance_spin.setValue(parent.peak_distance)
        self.distance_spin.setToolTip("Minimum distance between detected peaks")
        peak_form.addRow("Distance", self.distance_spin)
        layout.addWidget(peak_group)

        identification_group = QGroupBox("Identification")
        identification_form = QFormLayout(identification_group)
        identification_form.setHorizontalSpacing(14)
        identification_form.setVerticalSpacing(10)

        self.data_type_combo = QComboBox()
        for label, value in DATA_TYPE_CHOICES:
            self.data_type_combo.addItem(label, value)
        data_type_index = self.data_type_combo.findData(
            normalize_data_type(getattr(parent, "data_type", "generic"))
        )
        self.data_type_combo.setCurrentIndex(max(0, data_type_index))
        self.data_type_combo.setToolTip("Reference library entries are matched only against compatible data types")
        identification_form.addRow("Data type", self.data_type_combo)

        self.peak_tolerance_spin = QDoubleSpinBox()
        self.peak_tolerance_spin.setRange(0.001, 1_000_000.0)
        self.peak_tolerance_spin.setDecimals(3)
        self.peak_tolerance_spin.setSingleStep(1.0)
        self.peak_tolerance_spin.setSuffix(" Hz")
        self.peak_tolerance_spin.setValue(
            getattr(parent, "peak_frequency_tolerance", 5.0)
        )
        self.peak_tolerance_spin.setToolTip("Maximum frequency difference allowed when matching peaks")
        identification_form.addRow("Peak tolerance", self.peak_tolerance_spin)
        layout.addWidget(identification_group)

        hint = QLabel("Apply saves the settings and reruns the current analysis.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.baseline_checkbox.toggled.connect(self.baseline_method_combo.setEnabled)
        self.baseline_method_combo.setEnabled(self.baseline_checkbox.isChecked())
        self.spectrum_smoothing_checkbox.toggled.connect(
            self.spectrum_smoothing_method_combo.setEnabled
        )
        self.spectrum_smoothing_checkbox.toggled.connect(
            self.spectrum_smoothing_window_spin.setEnabled
        )
        self.spectrum_smoothing_method_combo.setEnabled(
            self.spectrum_smoothing_checkbox.isChecked()
        )
        self.spectrum_smoothing_window_spin.setEnabled(
            self.spectrum_smoothing_checkbox.isChecked()
        )
        self.filter_type_combo.currentIndexChanged.connect(
            self._update_filter_params_visibility
        )
        self._update_filter_params_visibility()

    def _refresh_method_presets(self, selected_name=None):
        names = self.main_window.list_method_presets()
        self.method_preset_combo.clear()
        if not names:
            self.method_preset_combo.addItem("No saved methods", "")
            self.method_load_button.setEnabled(False)
            self.method_delete_button.setEnabled(False)
            return

        for name in names:
            self.method_preset_combo.addItem(name, name)
        current_name = selected_name or getattr(
            self.main_window,
            "current_method_preset_name",
            "",
        )
        index = self.method_preset_combo.findData(current_name)
        self.method_preset_combo.setCurrentIndex(max(0, index))
        self.method_load_button.setEnabled(True)
        self.method_delete_button.setEnabled(True)

    def _selected_method_preset_name(self):
        return self.method_preset_combo.currentData() or ""

    def _load_method_preset(self):
        preset_name = self._selected_method_preset_name()
        if not preset_name:
            return
        if self.main_window.apply_method_preset(preset_name):
            self.accept()

    def _save_method_preset(self):
        default_name = (
            self._selected_method_preset_name()
            or getattr(self.main_window, "current_method_preset_name", "")
            or "New method"
        )
        name, ok = QInputDialog.getText(
            self,
            "Save analysis method",
            "Method name:",
            text=default_name,
        )
        if not ok:
            return

        self.apply_settings()
        saved_name = self.main_window.save_current_method_preset(name)
        if saved_name:
            self._refresh_method_presets(saved_name)

    def _delete_method_preset(self):
        preset_name = self._selected_method_preset_name()
        if not preset_name:
            return

        reply = QMessageBox.question(
            self,
            "Delete analysis method",
            f"Delete analysis method '{preset_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if self.main_window.delete_method_preset(preset_name):
            self._refresh_method_presets()

    def _update_filter_params_visibility(self):
        median_selected = self.filter_type_combo.currentData() == "median"
        self.filter_window_label.setVisible(median_selected)
        self.filter_window_spin.setVisible(median_selected)

    def _ensure_odd_window_size(self, window_size):
        if window_size % 2 == 0:
            self.filter_window_spin.setValue(min(51, window_size + 1))

    def _ensure_odd_smoothing_window_size(self, window_size):
        if window_size % 2 == 0:
            self.spectrum_smoothing_window_spin.setValue(min(501, window_size + 1))

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
            peak_min_snr=self.min_snr_spin.value(),
            filter_type=filter_type,
            filter_params=filter_params,
            sample_rate=self.sample_rate_spin.value(),
            window_type=self.window_type_combo.currentData(),
            normalize_area=self.normalize_area_checkbox.isChecked(),
            spectrum_smoothing_enabled=self.spectrum_smoothing_checkbox.isChecked(),
            spectrum_smoothing_method=self.spectrum_smoothing_method_combo.currentData(),
            spectrum_smoothing_window=self.spectrum_smoothing_window_spin.value(),
            peak_frequency_tolerance=self.peak_tolerance_spin.value(),
            data_type=self.data_type_combo.currentData(),
        )
