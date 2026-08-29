import logging
import sqlite3

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
            description="Certified Raman reference",
            cas_number="108-88-3",
            manufacturer="Example Standards",
            categories=("Aromatic", "Solvent"),
            sample_id="QC-2026-014",
            instrument="RamanScope 500",
            operator_name="Lab Operator",
            measurement_date="2026-08-29",
        )

        updated = {
            item.name: item for item in identifier.list_references()
        }["Reviewed Raman"]
        row = identifier.conn.execute(
            """
            SELECT formula, data_type, peaks_json, description, cas_number,
                   manufacturer, categories_json, sample_id, instrument,
                   operator_name, measurement_date, schema_version
            FROM compounds WHERE id = ?
            """,
            (entry.reference_id,),
        ).fetchone()

        assert updated.formula == "C7H8"
        assert updated.data_type == "raman"
        assert updated.description == "Certified Raman reference"
        assert updated.cas_number == "108-88-3"
        assert updated.manufacturer == "Example Standards"
        assert updated.categories == ("Aromatic", "Solvent")
        assert updated.sample_id == "QC-2026-014"
        assert updated.instrument == "RamanScope 500"
        assert updated.operator_name == "Lab Operator"
        assert updated.measurement_date == "2026-08-29"
        assert updated.peak_count == 1
        assert row[0] == "C7H8"
        assert row[1] == "raman"
        assert "100.0" in row[2]
        assert row[3] == "Certified Raman reference"
        assert row[4] == "108-88-3"
        assert row[5] == "Example Standards"
        assert row[6] == '["Aromatic", "Solvent"]'
        assert row[7] == "QC-2026-014"
        assert row[8] == "RamanScope 500"
        assert row[9] == "Lab Operator"
        assert row[10] == "2026-08-29"
        assert row[11] == 4
    finally:
        identifier.close()


def test_reference_metadata_update_rejects_invalid_inputs():
    identifier = make_identifier_with_references()
    try:
        entry = identifier.list_references()[0]

        assert not identifier.update_reference_metadata(entry.reference_id, "   ")
        assert not identifier.update_reference_metadata(0, "Valid")
        assert not identifier.update_reference_metadata(
            entry.reference_id,
            "Valid",
            cas_number="64-17-6",
        )
        assert not identifier.update_reference_metadata(
            entry.reference_id,
            "Valid",
            measurement_date="2026-02-30",
        )

        unchanged = {
            item.reference_id: item for item in identifier.list_references()
        }[entry.reference_id]
        assert unchanged.name == entry.name
        assert unchanged.measurement_date == ""
    finally:
        identifier.close()


def test_reference_metadata_sanitizes_control_characters_and_length():
    identifier = SpectrumIdentifier(":memory:")
    try:
        assert identifier.add_reference(
            "Unsafe\nName\t" + ("x" * 250),
            [1.0, 2.0, 3.0],
            "C\n7\tH8" + ("y" * 250),
        )
        row = identifier.conn.execute(
            "SELECT name, formula FROM compounds"
        ).fetchone()
    finally:
        identifier.close()

    assert "\n" not in row[0]
    assert "\t" not in row[0]
    assert len(row[0]) <= 200
    assert "\n" not in row[1]
    assert "\t" not in row[1]
    assert len(row[1]) <= 120


def test_reference_repository_rejects_unknown_migration_columns():
    identifier = SpectrumIdentifier(":memory:")
    try:
        try:
            identifier.repository._add_known_column_if_missing("name; DROP TABLE compounds")
        except ValueError as exc:
            assert "unknown reference-library migration column" in str(exc)
        else:
            raise AssertionError("unknown migration column was accepted")
    finally:
        identifier.close()


def test_reference_repository_migrates_legacy_database_without_data_loss(tmp_path):
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE compounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            formula TEXT,
            spectrum TEXT
        )
        """
    )
    connection.execute(
        "INSERT INTO compounds (name, formula, spectrum) VALUES (?, ?, ?)",
        ("Legacy", "H2O", "[1.0, 2.0]"),
    )
    connection.commit()
    connection.close()

    identifier = SpectrumIdentifier(database_path)
    try:
        entry = identifier.list_references()[0]
        columns = {
            row[1] for row in identifier.conn.execute("PRAGMA table_info(compounds)")
        }
    finally:
        identifier.close()

    assert entry.name == "Legacy"
    assert entry.formula == "H2O"
    assert entry.description == ""
    assert entry.cas_number == ""
    assert entry.manufacturer == ""
    assert entry.categories == ()
    assert entry.sample_id == ""
    assert entry.instrument == ""
    assert entry.operator_name == ""
    assert entry.measurement_date == ""
    assert {
        "description",
        "cas_number",
        "manufacturer",
        "categories_json",
        "sample_id",
        "instrument",
        "operator_name",
        "measurement_date",
    }.issubset(columns)


def test_reference_repository_does_not_log_rejected_private_name(caplog):
    identifier = SpectrumIdentifier(":memory:")
    private_name = "/Users/example/private/reference\nname"
    try:
        with caplog.at_level(logging.ERROR, logger="chromatsvet.reference_repository"):
            assert not identifier.add_reference(private_name, [float("nan")])
    finally:
        identifier.close()

    assert private_name not in caplog.text
    assert "/Users/example" not in caplog.text


def test_reference_listing_sanitizes_manually_corrupted_database_text():
    identifier = SpectrumIdentifier(":memory:")
    try:
        identifier.conn.execute(
            """
            INSERT INTO compounds
            (name, formula, spectrum, description, cas_number, manufacturer)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "Unsafe\nName\u202e",
                "H2O\t",
                "[]",
                "Description\u0000",
                "7732-18-5\n",
                "Lab\tName",
            ),
        )
        identifier.conn.commit()

        entry = identifier.list_references()[0]
    finally:
        identifier.close()

    assert entry.name == "Unsafe Name"
    assert entry.formula == "H2O"
    assert entry.description == "Description"
    assert entry.cas_number == "7732-18-5"
    assert entry.manufacturer == "Lab Name"


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
        description = "Updated description"
        cas_number = "7732-18-5"
        manufacturer = "Standards Lab"
        categories = ("Water", "Calibration")
        sample_id = "WATER-17"
        instrument = "UV-Vis 200"
        operator_name = "Operator A"
        measurement_date = "2026-08-28"

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
        assert entries["Edited Legacy"].description == "Updated description"
        assert entries["Edited Legacy"].cas_number == "7732-18-5"
        assert entries["Edited Legacy"].manufacturer == "Standards Lab"
        assert entries["Edited Legacy"].categories == ("Water", "Calibration")
        assert entries["Edited Legacy"].sample_id == "WATER-17"
        assert entries["Edited Legacy"].instrument == "UV-Vis 200"
        assert entries["Edited Legacy"].operator_name == "Operator A"
        assert entries["Edited Legacy"].measurement_date == "2026-08-28"
    finally:
        identifier.close()
        dialog.close()


def test_reference_library_dialog_searches_and_filters_extended_metadata(qapp):
    identifier = make_identifier_with_references()
    try:
        entry = next(
            item for item in identifier.list_references() if item.name == "Raman Peak"
        )
        assert identifier.update_reference_metadata(
            entry.reference_id,
            entry.name,
            entry.formula,
            entry.data_type,
            description="Quality-control aromatic standard",
            cas_number="108-88-3",
            manufacturer="Reference Works",
            categories=("QC", "Aromatic"),
            sample_id="RAMAN-QC-1",
            instrument="RamanScope 500",
            operator_name="Operator B",
            measurement_date="2026-08-27",
        )

        dialog = ReferenceLibraryDialog(None, identifier)
        dialog.search_edit.setText("108-88-3")
        assert [item.name for item in dialog.visible_entries] == ["Raman Peak"]

        dialog.search_edit.setText("RamanScope 500")
        assert [item.name for item in dialog.visible_entries] == ["Raman Peak"]

        dialog.search_edit.clear()
        category_index = dialog.category_filter.findData("Aromatic")
        dialog.category_filter.setCurrentIndex(category_index)
        assert [item.name for item in dialog.visible_entries] == ["Raman Peak"]
    finally:
        identifier.close()
        dialog.close()
