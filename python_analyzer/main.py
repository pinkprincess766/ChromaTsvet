import sys
import numpy as np
import csv
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QPushButton, QTableWidget, QTableWidgetItem, QLabel, 
                           QFileDialog, QHBoxLayout, QMessageBox, QInputDialog, QSplitter, QTextEdit,
                           QHeaderView, QDialog, QFormLayout, QComboBox, QDialogButtonBox, QSpinBox)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QFont, QColor, QPalette, QFontDatabase
import pyqtgraph as pg
from datetime import datetime
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image
import tempfile
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import spectrometer_rust
from python_analyzer.core.identification import SpectrumIdentifier

APP_ORG = "ChromaTsvet"
APP_NAME = "ChromaTsvet"
DEFAULT_THEME = "dark"
DEFAULT_FONT_SIZE = 12
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
        "splitter": "#252B35" if is_dark else "#D8DEE8",
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
        QComboBox {{
            background-color: {colors["panel"]};
            border: 1px solid {colors["border"]};
            border-radius: 6px;
            padding: 5px 8px;
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
        QSplitter::handle {{
            background-color: {colors["splitter"]};
        }}
        QLabel {{
            color: {colors["muted"]};
        }}
    """
    app.setStyleSheet(qss)


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Настройки")
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
        self.theme_combo.addItem("Тёмная", "dark")
        self.theme_combo.addItem("Светлая", "light")
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(parent.theme))
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        form.addRow("Тема", self.theme_combo)

        self.font_combo = QComboBox()
        for family in self._font_choices():
            self.font_combo.addItem(family)
        self.font_combo.setCurrentText(parent.font_family)
        self.font_combo.currentTextChanged.connect(self._font_changed)
        form.addRow("Шрифт", self.font_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(9, 16)
        self.font_size_spin.setValue(parent.font_size)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.valueChanged.connect(self._font_size_changed)
        form.addRow("Размер шрифта", self.font_size_spin)

        layout.addLayout(form)

        hint = QLabel("Шрифт применяется сразу. Если отдельные элементы ОС не обновились, перезапустите приложение.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        self.reset_button = QPushButton("Сбросить настройки")
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChromaTsvet — Анализ спектральных данных")
        self.resize(1700, 950)

        self.identifier = SpectrumIdentifier()
        self.current_data = None
        self.current_result = None
        self.current_file_name = None
        self.settings = app_settings()
        self.theme = saved_theme(self.settings)
        self.font_family = saved_font_family(self.settings)
        self.font_size = saved_font_size(self.settings)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 8)
        main_layout.setSpacing(8)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        self.btn_open = QPushButton("Открыть файл")
        self.btn_run = QPushButton("Обработать")
        self.btn_add = QPushButton("➕ Добавить")
        self.btn_restore = QPushButton("♻ Восстановить базу")
        self.btn_export = QPushButton("📄 PDF Отчёт")
        self.btn_settings = QPushButton("⚙ Настройки")
        
        self.btn_open.clicked.connect(self.load_file)
        self.btn_run.clicked.connect(self.run_analysis)
        self.btn_add.clicked.connect(self.add_substance)
        self.btn_restore.clicked.connect(self.restore_database)
        self.btn_export.clicked.connect(self.export_pdf)
        self.btn_settings.clicked.connect(self.open_settings)

        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_run)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_restore)
        btn_layout.addWidget(self.btn_export)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_settings)
        main_layout.addLayout(btn_layout)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setFont(QFont("Consolas", 9))
        splitter.addWidget(self.terminal)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        self.plot = pg.PlotWidget()
        self._configure_plot()
        right_layout.addWidget(self.plot)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Вещество", "Формула", "Score", "Совп. пики"])
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_layout.addWidget(self.table)

        splitter.addWidget(right_widget)
        splitter.setSizes([450, 1250])

        self.status = QLabel("Готов к работе")
        main_layout.addWidget(self.status)

        self.log("✅ Программа запущена")

        self.current_data = [0.1, 0.3, 0.8, 2.5, 9.0, 22.0, 8.5, 3.0, 1.2, 0.4, 0.2]
        self.run_analysis()

    def _configure_plot(self):
        colors = self._plot_colors()
        self.plot.setBackground(colors["background"])
        self._set_plot_title("Спектр")
        self.plot.setLabel('bottom', 'Индекс', color=colors["muted"], size="10pt")
        self.plot.setLabel('left', 'Интенсивность', color=colors["muted"], size="10pt")
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
        if self.current_data is not None:
            self.run_analysis()

    def log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.terminal.append(f"[{timestamp}] {msg}")

    def load_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Открыть спектр", "", "CSV (*.csv);;TXT (*.txt)")
        if file:
            data, skipped_rows = self._read_spectrum_file(file)
            if not data:
                QMessageBox.warning(self, "Ошибка", "В файле не найдено ни одного числового значения. Проверьте формат файла.")
                return

            if skipped_rows:
                examples = "\n".join(
                    f"Строка {line_no}: {value}"
                    for line_no, value in skipped_rows[:5]
                )
                QMessageBox.warning(
                    self,
                    "Предупреждение",
                    f"Файл: {file}\n"
                    f"Загружено точек: {len(data)}\n"
                    f"Пропущено строк: {len(skipped_rows)}\n\n"
                    f"Проблемные значения:\n{examples}"
                )

            self.current_data = data
            self.current_file_name = Path(file).name
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
            return float(value)
        except ValueError:
            pass

        try:
            return float(value.replace(',', '.'))
        except ValueError:
            return None

    def run_analysis(self):
        if self.current_data is None:
            return
        result = spectrometer_rust.process_signal(
            data=self.current_data,
            sample_rate=1000.0,
            filter_type="median",
            window_type="hann",
            threshold=0.05
        )
        self.current_result = result

        matches = self.identifier.find_matches(np.array(result['spectrum']))

        self.plot.clear()
        plot_title = f"Спектр — {self.current_file_name}" if self.current_file_name else "Спектр"
        self._set_plot_title(plot_title)
        x = np.arange(len(result['spectrum']))
        colors = self._plot_colors()
        self.plot.plot(x, result['spectrum'], pen=pg.mkPen(colors["spectrum"], width=2.6))

        for p in result["peaks"]:
            self.plot.plot(
                [p.position],
                [p.intensity],
                pen=None,
                symbol='o',
                symbolSize=11,
                symbolBrush=pg.mkBrush(colors["peak"]),
                symbolPen=pg.mkPen(colors["peak_border"], width=1.4)
            )

        self.table.setRowCount(len(matches))
        for row, m in enumerate(matches):
            self.table.setItem(row, 0, QTableWidgetItem(m.substance_name))
            self.table.setItem(row, 1, QTableWidgetItem(m.formula))
            self.table.setItem(row, 2, QTableWidgetItem(f"{m.score:.3f}"))
            self.table.setItem(row, 3, QTableWidgetItem(str(m.matched_peaks)))

        self.log(f"Готово! Пиков: {len(result['peaks'])} | Совпадений: {len(matches)}")

    def add_substance(self):
        name, ok = QInputDialog.getText(self, "Новое вещество", "Название:")
        if not ok or not name: return
        formula, ok = QInputDialog.getText(self, "Формула", "Формула:")
        if not ok: return
        ints_str, ok = QInputDialog.getText(self, "Интенсивности", "Через запятую:")
        if not ok: return
        try:
            intensities = [float(x.strip()) for x in ints_str.split(',')]
            self.identifier.add_reference(name, intensities, formula)
            QMessageBox.information(self, "Успех", f"'{name}' добавлено!")
            self.run_analysis()
        except:
            QMessageBox.warning(self, "Ошибка", "Неверный формат")

    def clear_database(self):
        if QMessageBox.question(self, "Очистка", "Очистить базу?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.identifier.clear_database()
            self.log("🗑 База очищена")
            self.run_analysis()

    def restore_database(self):
        if QMessageBox.question(self, "Восстановление", "Восстановить стандартную базу?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.identifier.restore_default()
            self.log("♻ База восстановлена")
            self.run_analysis()

    def export_pdf(self):
        if not self.current_result:
            QMessageBox.warning(self, "Ошибка", "Сначала обработайте спектр!")
            return

        file, _ = QFileDialog.getSaveFileName(self, "Сохранить PDF", f"report_{datetime.now():%Y%m%d_%H%M}.pdf", "PDF (*.pdf)")
        if not file: 
            return

        try:
            c = canvas.Canvas(file, pagesize=A4)
            width, height = A4

            # Заголовок
            c.setFont("Helvetica-Bold", 18)
            c.drawString(100, height - 80, "ChromaTsvet Report")

            c.setFont("Helvetica", 12)
            c.drawString(100, height - 120, f"Date: {datetime.now():%d.%m.%Y %H:%M}")
            c.drawString(100, height - 140, f"Peaks found: {len(self.current_result['peaks'])}")
            c.drawString(100, height - 160, f"Points: {len(self.current_data) if self.current_data else 0}")

            # Таблица
            y = height - 220
            c.setFont("Helvetica-Bold", 13)
            c.drawString(100, y, "Identification Results:")
            y -= 35

            c.setFont("Helvetica", 11)
            for row in range(self.table.rowCount()):
                if y < 80:
                    c.showPage()
                    y = height - 80
                name = self.table.item(row, 0).text()
                formula = self.table.item(row, 1).text()
                score = self.table.item(row, 2).text()
                line = f"{name:12} | {formula:8} | Score: {score}"
                c.drawString(100, y, line)
                y -= 22

            c.save()
            QMessageBox.information(self, "Успех", f"PDF сохранён:\n{file}")
            self.log("📄 PDF отчёт создан (английская версия)")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось создать PDF:\n{str(e)}")
if __name__ == "__main__":
    app = QApplication(sys.argv)
    settings = app_settings()
    apply_app_theme(app, saved_theme(settings), saved_font_family(settings), saved_font_size(settings))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
