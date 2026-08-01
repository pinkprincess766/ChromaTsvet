"""Reference library management dialog."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from python_analyzer.core.identification import (
    DATA_TYPE_CHOICES,
    ReferenceLibraryEntry,
    normalize_data_type,
)


class ReferenceMetadataDialog(QDialog):
    """Edit UI-safe metadata for one reference-library record."""

    def __init__(self, parent, entry: ReferenceLibraryEntry) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Reference")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(entry.name)
        self.formula_edit = QLineEdit(entry.formula)
        self.data_type_combo = QComboBox()
        for label, value in DATA_TYPE_CHOICES:
            self.data_type_combo.addItem(label, value)
        current_index = self.data_type_combo.findData(normalize_data_type(entry.data_type))
        self.data_type_combo.setCurrentIndex(max(0, current_index))

        form.addRow("Name", self.name_edit)
        form.addRow("Formula", self.formula_edit)
        form.addRow("Data type", self.data_type_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def reference_name(self) -> str:
        return self.name_edit.text().strip()

    @property
    def formula(self) -> str:
        return self.formula_edit.text().strip()

    @property
    def data_type(self) -> str:
        return normalize_data_type(self.data_type_combo.currentData())

    def accept(self) -> None:
        if not self.reference_name:
            QMessageBox.warning(self, "Invalid name", "Reference name cannot be empty.")
            return
        super().accept()


class ReferenceLibraryDialog(QDialog):
    """Inspect and maintain reference-library records."""

    def __init__(self, parent, identifier) -> None:
        super().__init__(parent)
        self.identifier = identifier
        self.changed = False
        self.entries: list[ReferenceLibraryEntry] = []
        self.visible_entries: list[ReferenceLibraryEntry] = []

        self.setWindowTitle("Reference Library")
        self.resize(900, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        filters = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by name or formula")
        self.search_edit.textChanged.connect(self._apply_filters)

        self.data_type_filter = QComboBox()
        self.data_type_filter.addItem("All data types", None)
        for label, value in DATA_TYPE_CHOICES:
            self.data_type_filter.addItem(label, value)
        self.data_type_filter.currentIndexChanged.connect(self._apply_filters)

        filters.addWidget(self.search_edit, stretch=1)
        filters.addWidget(self.data_type_filter)
        layout.addLayout(filters)

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
        self.table.itemSelectionChanged.connect(self._update_button_state)
        layout.addWidget(self.table)

        controls = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.edit_button = QPushButton("Edit selected")
        self.delete_button = QPushButton("Delete selected")
        self.refresh_button.clicked.connect(self.refresh)
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        controls.addWidget(self.refresh_button)
        controls.addWidget(self.edit_button)
        controls.addWidget(self.delete_button)
        controls.addStretch()

        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.rejected.connect(self.reject)
        controls.addWidget(close_buttons)
        layout.addLayout(controls)

        self.refresh()

    def refresh(self) -> None:
        self.entries = self.identifier.list_references()
        self._apply_filters()

    def _apply_filters(self) -> None:
        search_text = self.search_edit.text().strip().lower()
        selected_type = self.data_type_filter.currentData()
        normalized_type = normalize_data_type(selected_type) if selected_type else None

        self.visible_entries = [
            entry
            for entry in self.entries
            if self._entry_matches(entry, search_text, normalized_type)
        ]

        self.table.setRowCount(len(self.visible_entries))
        for row, entry in enumerate(self.visible_entries):
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
        self.summary_label.setText(self._summary_text())
        self._update_button_state()

    def edit_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            QMessageBox.information(
                self,
                "No reference selected",
                "Select a reference entry to edit.",
            )
            return

        dialog = ReferenceMetadataDialog(self, entry)
        if dialog.exec() != QDialog.Accepted:
            return

        if not self.identifier.update_reference_metadata(
            entry.reference_id,
            dialog.reference_name,
            dialog.formula,
            dialog.data_type,
        ):
            QMessageBox.warning(
                self,
                "Could not update reference",
                "The selected reference could not be updated.",
            )
            return

        self.changed = True
        self.refresh()

    def delete_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            QMessageBox.information(
                self,
                "No reference selected",
                "Select a reference entry to delete.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete reference",
            f"Delete '{entry.name}' from the reference library?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        if not self.identifier.delete_reference(entry.reference_id):
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

    def _selected_entry(self) -> ReferenceLibraryEntry | None:
        row = self._selected_row()
        if row is None or row < 0 or row >= len(self.visible_entries):
            return None
        return self.visible_entries[row]

    def _update_button_state(self) -> None:
        has_selection = self._selected_entry() is not None
        self.edit_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

    def _entry_matches(
        self,
        entry: ReferenceLibraryEntry,
        search_text: str,
        data_type: str | None,
    ) -> bool:
        if data_type and normalize_data_type(entry.data_type) != data_type:
            return False
        if not search_text:
            return True
        haystack = f"{entry.name} {entry.formula}".lower()
        return search_text in haystack

    def _summary_text(self) -> str:
        total = len(self.entries)
        visible = len(self.visible_entries)
        peak_backed = sum(1 for entry in self.entries if entry.peak_count > 0)
        legacy = total - peak_backed
        if visible == total:
            return f"{total} reference entries · {peak_backed} peak-based · {legacy} legacy"
        return (
            f"{visible} of {total} reference entries shown · "
            f"{peak_backed} peak-based · {legacy} legacy"
        )
