import json
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QDialog, QMessageBox

from python_analyzer.analysis.models import ReferencePeak
from python_analyzer.core.identification import SpectrumIdentifier
from python_analyzer.core.reference_library_io import (
    EXPORT_FORMAT,
    EXPORT_SCHEMA_VERSION,
    ReferenceLibraryFormatError,
    ReferenceLibraryRecord,
    read_reference_csv,
    read_reference_json,
    write_reference_csv,
    write_reference_json,
)
from python_analyzer.gui import reference_library
from python_analyzer.gui.reference_library import ReferenceLibraryDialog


def make_identifier() -> SpectrumIdentifier:
    identifier = SpectrumIdentifier(":memory:")
    identifier.add_reference("Legacy Sample", [1.0, 2.0, 3.0], "L")
    identifier.add_reference(
        "Raman Peak",
        None,
        "RP",
        peaks=[
            ReferencePeak(
                frequency=100.0,
                intensity=1.0,
                width=2.0,
                width_hz=0.5,
                area=3.0,
                snr=20.0,
            )
        ],
        data_type="raman",
    )
    return identifier


def test_reference_json_export_has_schema_and_no_local_paths(tmp_path: Path):
    private_db_dir = tmp_path / "Users" / "chemist" / "Library"
    private_db_dir.mkdir(parents=True)
    identifier = SpectrumIdentifier(private_db_dir / "library.db")
    try:
        assert identifier.add_reference(
            "Portable Raman",
            None,
            "C7H8",
            peaks=[ReferencePeak(frequency=1602.0, intensity=0.8)],
            data_type="raman",
        )
        output_path = tmp_path / "portable.json"

        write_reference_json(output_path, identifier.export_reference_records())
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        exported_text = output_path.read_text(encoding="utf-8")

        assert payload["format"] == EXPORT_FORMAT
        assert payload["schema_version"] == EXPORT_SCHEMA_VERSION
        assert payload["records"][0]["schema_version"] == 2
        assert "Portable Raman" in exported_text
        assert str(private_db_dir) not in exported_text
        assert "library.db" not in exported_text

        imported = read_reference_json(output_path)
        assert imported[0].name == "Portable Raman"
        assert imported[0].peaks[0].frequency == 1602.0
    finally:
        identifier.close()


def test_reference_csv_export_escapes_formula_like_text(tmp_path: Path):
    records = [
        ReferenceLibraryRecord(
            name="=HYPERLINK(\"http://example.test\")",
            formula="+SUM(A1:A2)",
            data_type="generic",
            spectrum=(1.0, 2.0),
        )
    ]
    output_path = tmp_path / "references.csv"

    write_reference_csv(output_path, records)
    exported_text = output_path.read_text(encoding="utf-8")

    assert "'=HYPERLINK" in exported_text
    assert "'+SUM" in exported_text

    imported = read_reference_csv(output_path)
    assert imported[0].name.startswith("=HYPERLINK")
    assert imported[0].formula == "+SUM(A1:A2)"


def test_reference_import_preview_and_skip_duplicate_policy():
    identifier = make_identifier()
    try:
        records = [
            ReferenceLibraryRecord(
                name="legacy sample",
                formula="Updated",
                spectrum=(9.0,),
            ),
            ReferenceLibraryRecord(
                name="New Reference",
                formula="N",
                spectrum=(4.0, 5.0),
            ),
        ]

        preview = identifier.preview_reference_import(records)
        result = identifier.import_reference_records(records, duplicate_policy="skip")

        assert preview.new_count == 1
        assert preview.duplicate_count == 1
        assert result.added == 1
        assert result.skipped == 1
        exported = {
            record.name: record for record in identifier.export_reference_records()
        }
        assert exported["Legacy Sample"].formula == "L"
        assert exported["New Reference"].spectrum == (4.0, 5.0)
    finally:
        identifier.close()


def test_reference_import_replace_duplicate_policy():
    identifier = make_identifier()
    try:
        result = identifier.import_reference_records(
            [
                ReferenceLibraryRecord(
                    name="Legacy Sample",
                    formula="Replacement",
                    data_type="uv_vis",
                    spectrum=(9.0, 8.0),
                )
            ],
            duplicate_policy="replace",
        )

        assert result.replaced == 1
        exported = {
            record.name: record for record in identifier.export_reference_records()
        }
        assert exported["Legacy Sample"].formula == "Replacement"
        assert exported["Legacy Sample"].data_type == "uv_vis"
        assert exported["Legacy Sample"].spectrum == (9.0, 8.0)
    finally:
        identifier.close()


def test_reference_import_merge_preserves_existing_peak_features():
    identifier = make_identifier()
    try:
        result = identifier.import_reference_records(
            [
                ReferenceLibraryRecord(
                    name="Raman Peak",
                    formula="Merged",
                    data_type="generic",
                    spectrum=(5.0, 6.0),
                )
            ],
            duplicate_policy="merge",
        )

        assert result.merged == 1
        exported = {
            record.name: record for record in identifier.export_reference_records()
        }
        merged = exported["Raman Peak"]
        assert merged.formula == "Merged"
        assert merged.data_type == "raman"
        assert merged.spectrum == (5.0, 6.0)
        assert merged.peaks[0].frequency == 100.0
    finally:
        identifier.close()


def test_reference_json_import_rejects_non_finite_values(tmp_path: Path):
    input_path = tmp_path / "bad.json"
    input_path.write_text(
        """
        {
          "format": "chromatsvet.reference_library",
          "schema_version": 1,
          "records": [
            {"name": "Bad", "schema_version": 1, "spectrum": [NaN], "peaks": []}
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ReferenceLibraryFormatError):
        read_reference_json(input_path)


def test_reference_library_dialog_imports_json_after_preview(
    qapp,
    tmp_path: Path,
    monkeypatch,
):
    identifier = make_identifier()
    input_path = tmp_path / "incoming.json"
    write_reference_json(
        input_path,
        [
            ReferenceLibraryRecord(
                name="Legacy Sample",
                formula="From GUI",
                spectrum=(7.0,),
            )
        ],
    )

    class FakePreviewDialog:
        duplicate_policy = "replace"

        def __init__(self, parent, preview):
            self.preview = preview

        def exec(self):
            return QDialog.Accepted

    try:
        dialog = ReferenceLibraryDialog(None, identifier)
        monkeypatch.setattr(
            reference_library.QFileDialog,
            "getOpenFileName",
            lambda *args, **kwargs: (str(input_path), "JSON (*.json)"),
        )
        monkeypatch.setattr(
            reference_library,
            "ReferenceImportPreviewDialog",
            FakePreviewDialog,
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

        dialog.import_references()

        exported = {
            record.name: record for record in identifier.export_reference_records()
        }
        assert dialog.changed
        assert exported["Legacy Sample"].formula == "From GUI"
        assert exported["Legacy Sample"].spectrum == (7.0,)
    finally:
        identifier.close()
        dialog.close()
