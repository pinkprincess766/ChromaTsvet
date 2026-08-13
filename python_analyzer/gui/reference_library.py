"""Reference library management dialog."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
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
from python_analyzer.core.reference_library_io import (
    DUPLICATE_POLICIES,
    ReferenceImportPreview,
    ReferenceLibraryFormatError,
    read_reference_csv,
    read_reference_json,
    write_reference_csv,
    write_reference_json,
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


class ReferenceImportPreviewDialog(QDialog):
    """Preview portable references before importing them."""

    def __init__(self, parent, preview: ReferenceImportPreview) -> None:
        super().__init__(parent)
        self.preview = preview
        self.setWindowTitle("Import References")
        self.resize(720, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        layout.addWidget(
            QLabel(
                f"{preview.total_count} references · "
                f"{preview.new_count} new · {preview.duplicate_count} duplicates"
            )
        )

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Data type", "Points", "Peaks", "Import status"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setRowCount(len(preview.rows))
        for row, preview_row in enumerate(preview.rows):
            values = [
                preview_row.name,
                preview_row.data_type,
                str(preview_row.spectrum_points),
                str(preview_row.peak_count),
                preview_row.status,
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        layout.addWidget(self.table)

        form = QFormLayout()
        self.policy_combo = QComboBox()
        self.policy_combo.addItem("Skip duplicate names", "skip")
        self.policy_combo.addItem("Merge into existing names", "merge")
        self.policy_combo.addItem("Replace duplicate names", "replace")
        form.addRow("Duplicate handling", self.policy_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def duplicate_policy(self) -> str:
        policy = self.policy_combo.currentData()
        return policy if policy in DUPLICATE_POLICIES else "skip"


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
        self.export_selected_button = QPushButton("Export selected")
        self.export_all_button = QPushButton("Export all")
        self.import_button = QPushButton("Import...")
        self.refresh_button.clicked.connect(self.refresh)
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.export_selected_button.clicked.connect(self.export_selected)
        self.export_all_button.clicked.connect(self.export_all)
        self.import_button.clicked.connect(self.import_references)
        controls.addWidget(self.refresh_button)
        controls.addWidget(self.edit_button)
        controls.addWidget(self.delete_button)
        controls.addWidget(self.export_selected_button)
        controls.addWidget(self.export_all_button)
        controls.addWidget(self.import_button)
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

    def export_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            QMessageBox.information(
                self,
                "No reference selected",
                "Select a reference entry to export.",
            )
            return
        records = self.identifier.export_reference_records([entry.reference_id])
        self._export_records(
            records,
            default_name=f"{self._safe_default_filename(entry.name)}_reference",
        )

    def export_all(self) -> None:
        records = self.identifier.export_reference_records()
        if not records:
            QMessageBox.information(
                self,
                "No references",
                "The reference library does not contain exportable records.",
            )
            return
        self._export_records(records, default_name="chromatsvet_reference_library")

    def import_references(self) -> None:
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import reference library",
            "",
            "Reference Library (*.json *.csv);;JSON (*.json);;CSV (*.csv)",
        )
        if not file_path:
            return

        path = Path(file_path)
        try:
            records = self._read_reference_records(path)
            if not records:
                QMessageBox.information(
                    self,
                    "No references",
                    "The selected file does not contain reference records.",
                )
                return
            preview = self.identifier.preview_reference_import(records)
        except (OSError, ReferenceLibraryFormatError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Could not import references",
                f"{self._safe_file_label(path)} could not be imported "
                f"({type(exc).__name__}).",
            )
            return

        dialog = ReferenceImportPreviewDialog(self, preview)
        if dialog.exec() != QDialog.Accepted:
            return

        result = self.identifier.import_reference_records(
            records,
            duplicate_policy=dialog.duplicate_policy,
        )
        self.changed = self.changed or result.changed > 0
        self.refresh()
        self._show_import_result(result)

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
        self.export_selected_button.setEnabled(has_selection)
        self.export_all_button.setEnabled(bool(self.entries))

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

    def _export_records(self, records: list, *, default_name: str) -> None:
        if not records:
            QMessageBox.information(
                self,
                "No references",
                "There are no exportable references for the current selection.",
            )
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export reference library",
            f"{default_name}.json",
            "JSON (*.json);;CSV (*.csv)",
        )
        if not file_path:
            return

        path = self._path_with_export_suffix(Path(file_path), selected_filter)
        try:
            if path.suffix.lower() == ".csv":
                write_reference_csv(path, records)
            else:
                write_reference_json(path, records)
        except (OSError, ValueError, ReferenceLibraryFormatError) as exc:
            QMessageBox.warning(
                self,
                "Could not export references",
                f"{self._safe_file_label(path)} could not be exported "
                f"({type(exc).__name__}).",
            )
            return

        QMessageBox.information(
            self,
            "References exported",
            f"Exported {len(records)} references to {self._safe_file_label(path)}.",
        )

    def _read_reference_records(self, path: Path) -> list:
        if path.suffix.lower() == ".csv":
            return read_reference_csv(path)
        return read_reference_json(path)

    def _path_with_export_suffix(self, path: Path, selected_filter: str) -> Path:
        if path.suffix.lower() in {".json", ".csv"}:
            return path
        suffix = ".csv" if "CSV" in selected_filter else ".json"
        return path.with_suffix(suffix)

    def _show_import_result(self, result) -> None:
        message = (
            f"Added: {result.added}\n"
            f"Merged: {result.merged}\n"
            f"Replaced: {result.replaced}\n"
            f"Skipped: {result.skipped}\n"
            f"Failed: {result.failed}"
        )
        if result.failed:
            QMessageBox.warning(self, "References imported with warnings", message)
            return
        QMessageBox.information(self, "References imported", message)

    def _safe_file_label(self, path: Path) -> str:
        return path.name or "reference-library file"

    def _safe_default_filename(self, value: object) -> str:
        text = str(value or "reference").strip().lower()
        safe = "".join(
            char if char.isalnum() or char in {"-", "_"} else "_"
            for char in text
        )
        safe = "_".join(part for part in safe.split("_") if part)
        return safe[:80] or "reference"
