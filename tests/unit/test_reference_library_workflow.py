from PyQt5.QtWidgets import QDialog

from python_analyzer.analysis.models import ReferencePeak
from python_analyzer.core.identification import SpectrumIdentifier
from python_analyzer.gui import reference_library
from python_analyzer.gui.reference_library import ReferenceLibraryDialog


def make_identifier_with_references() -> SpectrumIdentifier:
    identifier = SpectrumIdentifier(":memory:")
    identifier.add_reference("Legacy Sample", [1.0, 2.0, 3.0], "L")
    identifier.add_reference(
        "Raman Peak",
        None,
        "RP",
        peaks=[ReferencePeak(frequency=100.0, intensity=1.0)],
        data_type="raman",
    )
    identifier.add_reference(
        "IR Peak",
        None,
        "IP",
        peaks=[ReferencePeak(frequency=200.0, intensity=0.7)],
        data_type="ir",
    )
    return identifier


def test_reference_metadata_update_preserves_stored_signal_data():
    identifier = make_identifier_with_references()
    try:
        entry = next(
            item for item in identifier.list_references() if item.name == "Raman Peak"
        )

        assert identifier.update_reference_metadata(
            entry.reference_id,
            "Reviewed Raman",
            "C7H8",
            "RAMAN!",
        )

        updated = {
            item.name: item for item in identifier.list_references()
        }["Reviewed Raman"]
        row = identifier.conn.execute(
            "SELECT formula, data_type, peaks_json FROM compounds WHERE id = ?",
            (entry.reference_id,),
        ).fetchone()

        assert updated.formula == "C7H8"
        assert updated.data_type == "raman"
        assert updated.peak_count == 1
        assert row[0] == "C7H8"
        assert row[1] == "raman"
        assert "100.0" in row[2]
    finally:
        identifier.close()


def test_reference_metadata_update_rejects_invalid_inputs():
    identifier = make_identifier_with_references()
    try:
        entry = identifier.list_references()[0]

        assert not identifier.update_reference_metadata(entry.reference_id, "   ")
        assert not identifier.update_reference_metadata(0, "Valid")

        unchanged = {
            item.reference_id: item for item in identifier.list_references()
        }[entry.reference_id]
        assert unchanged.name == entry.name
    finally:
        identifier.close()


def test_reference_library_dialog_filters_by_text_and_data_type(qapp):
    identifier = make_identifier_with_references()
    try:
        dialog = ReferenceLibraryDialog(None, identifier)

        assert len(dialog.visible_entries) == 3
        assert "3 reference entries" in dialog.summary_label.text()

        dialog.search_edit.setText("peak")
        assert {entry.name for entry in dialog.visible_entries} == {
            "IR Peak",
            "Raman Peak",
        }

        dialog.data_type_filter.setCurrentIndex(dialog.data_type_filter.findData("raman"))
        assert [entry.name for entry in dialog.visible_entries] == ["Raman Peak"]
        assert "1 of 3 reference entries shown" in dialog.summary_label.text()
    finally:
        identifier.close()
        dialog.close()


def test_reference_library_dialog_edits_selected_metadata(qapp, monkeypatch):
    identifier = make_identifier_with_references()

    class FakeMetadataDialog:
        reference_name = "Edited Legacy"
        formula = "EL"
        data_type = "uv_vis"

        def __init__(self, parent, entry):
            self.entry = entry

        def exec(self):
            return QDialog.Accepted

    try:
        dialog = ReferenceLibraryDialog(None, identifier)
        dialog.search_edit.setText("legacy")
        dialog.table.selectRow(0)
        monkeypatch.setattr(
            reference_library,
            "ReferenceMetadataDialog",
            FakeMetadataDialog,
        )

        dialog.edit_selected()

        entries = {entry.name: entry for entry in identifier.list_references()}
        assert dialog.changed
        assert "Edited Legacy" in entries
        assert entries["Edited Legacy"].formula == "EL"
        assert entries["Edited Legacy"].data_type == "uv_vis"
    finally:
        identifier.close()
        dialog.close()
