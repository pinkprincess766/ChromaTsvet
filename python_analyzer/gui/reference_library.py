"""Reference library management dialog."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class ReferenceLibraryDialog(QDialog):
    """Inspect and maintain reference-library records."""

    def __init__(self, parent, identifier) -> None:
        super().__init__(parent)
        self.identifier = identifier
        self.changed = False

        self.setWindowTitle("Reference Library")
        self.resize(820, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Formula", "Data type", "Schema", "Points", "Peaks"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        controls = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.delete_button = QPushButton("Delete selected")
        self.refresh_button.clicked.connect(self.refresh)
        self.delete_button.clicked.connect(self.delete_selected)
        controls.addWidget(self.refresh_button)
        controls.addWidget(self.delete_button)
        controls.addStretch()

        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.rejected.connect(self.reject)
        controls.addWidget(close_buttons)
        layout.addLayout(controls)

        self.refresh()

    def refresh(self) -> None:
        entries = self.identifier.list_references()
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            values = [
                entry.name,
                entry.formula,
                entry.data_type,
                str(entry.schema_version),
                str(entry.spectrum_points),
                str(entry.peak_count),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if column == 0:
                    item.setData(Qt.UserRole, entry.reference_id)
                self.table.setItem(row, column, item)
        self.summary_label.setText(f"{len(entries)} reference entries")
        self.delete_button.setEnabled(bool(entries))

    def delete_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(
                self,
                "No reference selected",
                "Select a reference entry to delete.",
            )
            return

        name_item = self.table.item(row, 0)
        reference_id = name_item.data(Qt.UserRole) if name_item else None
        reference_name = name_item.text() if name_item else "selected reference"
        if reference_id is None:
            QMessageBox.warning(
                self,
                "Could not delete reference",
                "The selected reference row does not contain a valid identifier.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete reference",
            f"Delete '{reference_name}' from the reference library?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        if not self.identifier.delete_reference(int(reference_id)):
            QMessageBox.warning(
                self,
                "Could not delete reference",
                "The selected reference could not be deleted.",
            )
            return

        self.changed = True
        self.refresh()

    def _selected_row(self) -> int | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        return selected[0].row()
