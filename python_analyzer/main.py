import sys
import numpy as np
import csv
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QPushButton, QTableWidget, QTableWidgetItem, QLabel, 
                           QFileDialog, QHBoxLayout, QMessageBox, QInputDialog, QSplitter, QTextEdit)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChromaTsvet — Анализ спектральных данных")
        self.resize(1700, 950)

        self.identifier = SpectrumIdentifier()
        self.current_data = None
        self.current_result = None
        self.current_file_name = None

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        btn_layout = QHBoxLayout()
        self.btn_open = QPushButton("Открыть файл")
        self.btn_run = QPushButton("Обработать")
        self.btn_add = QPushButton("➕ Добавить")
        self.btn_restore = QPushButton("♻ Восстановить базу")
        self.btn_export = QPushButton("📄 PDF Отчёт")
        
        self.btn_open.clicked.connect(self.load_file)
        self.btn_run.clicked.connect(self.run_analysis)
        self.btn_add.clicked.connect(self.add_substance)
        self.btn_restore.clicked.connect(self.restore_database)
        self.btn_export.clicked.connect(self.export_pdf)

        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_run)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_restore)
        btn_layout.addWidget(self.btn_export)
        main_layout.addLayout(btn_layout)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setFont(QFont("Consolas", 10))
        self.terminal.setStyleSheet("background-color: #1e1e1e; color: #00ff88; padding: 8px;")
        splitter.addWidget(self.terminal)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.plot = pg.PlotWidget()
        self.plot.setBackground('w')
        self.plot.setTitle("Спектр", size="20pt")
        self.plot.setLabel('bottom', 'Индекс')
        self.plot.setLabel('left', 'Интенсивность')
        self.plot.showGrid(x=True, y=True, alpha=0.6)
        right_layout.addWidget(self.plot)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Вещество", "Формула", "Score", "Совп. пики"])
        right_layout.addWidget(self.table)

        splitter.addWidget(right_widget)
        splitter.setSizes([450, 1250])

        self.status = QLabel("Готов к работе")
        main_layout.addWidget(self.status)

        self.log("✅ Программа запущена")

        self.current_data = [0.1, 0.3, 0.8, 2.5, 9.0, 22.0, 8.5, 3.0, 1.2, 0.4, 0.2]
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
        self.plot.setTitle(plot_title, size="20pt")
        x = np.arange(len(result['spectrum']))
        self.plot.plot(x, result['spectrum'], pen=pg.mkPen('b', width=4))

        for p in result["peaks"]:
            self.plot.plot([p.position], [p.intensity], symbol='o', symbolSize=16, symbolBrush='r')

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
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
