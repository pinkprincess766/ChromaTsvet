import json
import csv
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QDialog, QMessageBox

from python_analyzer.analysis.models import ReferencePeak
from python_analyzer.core import reference_library_io
from python_analyzer.core.identification import SpectrumIdentifier
from python_analyzer.core.reference_library_io import (
    EXPORT_FORMAT,
    EXPORT_SCHEMA_VERSION,
    ReferenceLibraryFormatError,
    ReferenceLibraryRecord,
    coerce_reference_record,
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
            description="Portable reference without source paths",
            cas_number="108-88-3",
            manufacturer="Reference Works",
            categories=("Aromatic", "QC"),
            sample_id="TOL-2026-08",
            instrument="RamanScope 500",
            operator_name="Operator A",
            measurement_date="2026-08-29",
        )
        output_path = tmp_path / "portable.json"

        write_reference_json(output_path, identifier.export_reference_records())
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        exported_text = output_path.read_text(encoding="utf-8")

        assert payload["format"] == EXPORT_FORMAT
        assert payload["schema_version"] == EXPORT_SCHEMA_VERSION
        assert payload["records"][0]["schema_version"] == 4
        assert payload["records"][0]["cas_number"] == "108-88-3"
        assert payload["records"][0]["categories"] == ["Aromatic", "QC"]
        assert payload["records"][0]["sample_id"] == "TOL-2026-08"
        assert payload["records"][0]["instrument"] == "RamanScope 500"
        assert payload["records"][0]["operator_name"] == "Operator A"
        assert payload["records"][0]["measurement_date"] == "2026-08-29"
        assert "Portable Raman" in exported_text
        assert str(private_db_dir) not in exported_text
        assert "library.db" not in exported_text

        imported = read_reference_json(output_path)
        assert imported[0].name == "Portable Raman"
        assert imported[0].manufacturer == "Reference Works"
        assert imported[0].sample_id == "TOL-2026-08"
        assert imported[0].peaks[0].frequency == 1602.0
    finally:
        identifier.close()


def test_reference_csv_export_escapes_formula_like_text(tmp_path: Path):
    records = [
        ReferenceLibraryRecord(
            name="=HYPERLINK(\"http://example.test\")",
            formula="+SUM(A1:A2)",
            description="@IMPORT(\"private\")",
            manufacturer="-2+3",
            sample_id="=SAMPLE()",
            instrument="@INSTRUMENT()",
            operator_name="+OPERATOR()",
            categories=("=unsafe", "Safe"),
            data_type="generic",
            spectrum=(1.0, 2.0),
        )
    ]
    output_path = tmp_path / "references.csv"

    write_reference_csv(output_path, records)
    exported_text = output_path.read_text(encoding="utf-8")

    assert "'=HYPERLINK" in exported_text
    assert "'+SUM" in exported_text
    assert "'@IMPORT" in exported_text
    assert "'-2+3" in exported_text
    assert "'=SAMPLE" in exported_text
    assert "'@INSTRUMENT" in exported_text
    assert "'+OPERATOR" in exported_text

    imported = read_reference_csv(output_path)
    assert imported[0].name.startswith("=HYPERLINK")
    assert imported[0].formula == "+SUM(A1:A2)"
    assert imported[0].description == '@IMPORT("private")'
    assert imported[0].manufacturer == "-2+3"
    assert imported[0].sample_id == "=SAMPLE()"
    assert imported[0].instrument == "@INSTRUMENT()"
    assert imported[0].operator_name == "+OPERATOR()"
    assert imported[0].categories == ("=unsafe", "Safe")


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


def test_reference_import_preview_uses_sanitized_metadata():
    identifier = make_identifier()
    try:
        preview = identifier.preview_reference_import(
            [
                ReferenceLibraryRecord(
                    name="Safe\u202e Name\n",
                    categories=(" QC\t", "qc"),
                    spectrum=(1.0,),
                )
            ]
        )

        assert preview.rows[0].name == "Safe Name"
        assert preview.rows[0].categories == ("QC",)
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
                    description="Incoming metadata",
                    cas_number="108-88-3",
                    manufacturer="Reference Works",
                    categories=("Aromatic",),
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
        assert merged.description == "Incoming metadata"
        assert merged.cas_number == "108-88-3"
        assert merged.manufacturer == "Reference Works"
        assert merged.categories == ("Aromatic",)
        assert merged.data_type == "raman"
        assert merged.spectrum == (5.0, 6.0)
        assert merged.peaks[0].frequency == 100.0
    finally:
        identifier.close()


def test_reference_import_merge_unions_categories_without_case_duplicates():
    identifier = SpectrumIdentifier(":memory:")
    try:
        assert identifier.add_reference(
            "Categorized",
            [1.0],
            categories=("QC", "Solvent"),
        )
        result = identifier.import_reference_records(
            [
                ReferenceLibraryRecord(
                    name="Categorized",
                    categories=("qc", "Aromatic"),
                    spectrum=(2.0,),
                )
            ],
            duplicate_policy="merge",
        )

        merged = identifier.export_reference_records()[0]
        assert result.merged == 1
        assert merged.categories == ("QC", "Solvent", "Aromatic")
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


def test_reference_json_v1_remains_importable(tmp_path: Path):
    input_path = tmp_path / "legacy.json"
    input_path.write_text(
        json.dumps(
            {
                "format": EXPORT_FORMAT,
                "schema_version": 1,
                "records": [
                    {
                        "name": "Legacy JSON",
                        "formula": "H2O",
                        "data_type": "generic",
                        "schema_version": 1,
                        "spectrum": [1.0, 2.0],
                        "peaks": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    record = read_reference_json(input_path)[0]

    assert record.name == "Legacy JSON"
    assert record.description == ""
    assert record.cas_number == ""
    assert record.manufacturer == ""
    assert record.categories == ()
    assert record.sample_id == ""
    assert record.instrument == ""
    assert record.operator_name == ""
    assert record.measurement_date == ""


def test_reference_csv_v1_remains_importable(tmp_path: Path):
    input_path = tmp_path / "legacy.csv"
    with input_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "format",
                "export_schema_version",
                "name",
                "formula",
                "data_type",
                "record_schema_version",
                "spectrum_json",
                "peaks_json",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "format": EXPORT_FORMAT,
                "export_schema_version": 1,
                "name": "Legacy CSV",
                "formula": "H2O",
                "data_type": "generic",
                "record_schema_version": 1,
                "spectrum_json": "[1.0, 2.0]",
                "peaks_json": "[]",
            }
        )

    record = read_reference_csv(input_path)[0]

    assert record.name == "Legacy CSV"
    assert record.categories == ()
    assert record.sample_id == ""
    assert record.instrument == ""
    assert record.operator_name == ""
    assert record.measurement_date == ""


def test_reference_json_rejects_future_schema(tmp_path: Path):
    input_path = tmp_path / "future.json"
    input_path.write_text(
        json.dumps(
            {
                "format": EXPORT_FORMAT,
                "schema_version": EXPORT_SCHEMA_VERSION + 1,
                "records": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReferenceLibraryFormatError, match="unsupported.*schema"):
        read_reference_json(input_path)


@pytest.mark.parametrize("schema_version", [0, 5, 2.5, True, "2.0"])
def test_reference_json_rejects_unknown_or_non_integer_record_schema(
    tmp_path: Path,
    schema_version,
):
    input_path = tmp_path / "bad-record-schema.json"
    input_path.write_text(
        json.dumps(
            {
                "format": EXPORT_FORMAT,
                "schema_version": EXPORT_SCHEMA_VERSION,
                "records": [
                    {
                        "name": "Bad schema",
                        "schema_version": schema_version,
                        "spectrum": [],
                        "peaks": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReferenceLibraryFormatError):
        read_reference_json(input_path)


def test_reference_csv_v2_requires_metadata_columns(tmp_path: Path):
    input_path = tmp_path / "incomplete-v2.csv"
    with input_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "format",
                "export_schema_version",
                "name",
                "formula",
                "data_type",
                "record_schema_version",
                "spectrum_json",
                "peaks_json",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "format": EXPORT_FORMAT,
                "export_schema_version": 2,
                "name": "Incomplete",
                "formula": "",
                "data_type": "generic",
                "record_schema_version": 1,
                "spectrum_json": "[]",
                "peaks_json": "[]",
            }
        )

    with pytest.raises(ReferenceLibraryFormatError, match="missing v2 metadata"):
        read_reference_csv(input_path)


def test_reference_csv_v3_requires_acquisition_columns(tmp_path: Path):
    input_path = tmp_path / "incomplete-v3.csv"
    fieldnames = [
        *reference_library_io.BASE_CSV_HEADERS,
        *reference_library_io.METADATA_CSV_HEADERS,
    ]
    with input_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "format": EXPORT_FORMAT,
                "export_schema_version": 3,
                "name": "Incomplete",
                "formula": "",
                "data_type": "generic",
                "record_schema_version": 1,
                "spectrum_json": "[]",
                "peaks_json": "[]",
                "description": "",
                "cas_number": "",
                "manufacturer": "",
                "categories_json": "[]",
            }
        )

    with pytest.raises(ReferenceLibraryFormatError, match="missing v3 acquisition"):
        read_reference_csv(input_path)


@pytest.mark.parametrize(
    "measurement_date",
    ["2026-02-30", "29-08-2026", "2026-8-9", "tomorrow"],
)
def test_reference_import_rejects_invalid_measurement_dates(
    tmp_path: Path,
    measurement_date: str,
):
    input_path = tmp_path / "invalid-measurement-date.json"
    input_path.write_text(
        json.dumps(
            {
                "format": EXPORT_FORMAT,
                "schema_version": EXPORT_SCHEMA_VERSION,
                "records": [
                    {
                        "name": "Invalid date",
                        "measurement_date": measurement_date,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReferenceLibraryFormatError, match="YYYY-MM-DD"):
        read_reference_json(input_path)


@pytest.mark.parametrize("suffix", ["json", "csv"])
def test_reference_import_rejects_non_utf8_documents(tmp_path: Path, suffix: str):
    input_path = tmp_path / f"invalid-encoding.{suffix}"
    input_path.write_bytes(b"\xff\xfe\xfa")

    reader = read_reference_json if suffix == "json" else read_reference_csv
    with pytest.raises(ReferenceLibraryFormatError):
        reader(input_path)


def test_reference_csv_rejects_unexpected_columns(tmp_path: Path):
    input_path = tmp_path / "extra-column.csv"
    input_path.write_text(
        ",".join(reference_library_io.BASE_CSV_HEADERS) + "\n"
        + ",".join(
            [
                EXPORT_FORMAT,
                "1",
                "Reference",
                "",
                "generic",
                "1",
                "[]",
                "[]",
                "unexpected",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ReferenceLibraryFormatError, match="unexpected columns"):
        read_reference_csv(input_path)


@pytest.mark.parametrize("cas_number", ["64-17-6", "not-a-cas", "12345678-00-0"])
def test_reference_import_rejects_invalid_cas_numbers(
    tmp_path: Path,
    cas_number: str,
):
    input_path = tmp_path / "invalid-cas.json"
    input_path.write_text(
        json.dumps(
            {
                "format": EXPORT_FORMAT,
                "schema_version": EXPORT_SCHEMA_VERSION,
                "records": [
                    {
                        "name": "Unsafe CAS",
                        "cas_number": cas_number,
                        "spectrum": [],
                        "peaks": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReferenceLibraryFormatError):
        read_reference_json(input_path)


def test_reference_metadata_removes_controls_and_deduplicates_categories():
    record = ReferenceLibraryRecord(
        name="Safe\u202eName\n",
        description="Line one\nLine two\u0000",
        categories=(" QC ", "qc", "Aromatic\tstandard"),
    )

    output = coerce_reference_record(record)

    assert output.name == "Safe Name"
    assert output.description == "Line one Line two"
    assert output.categories == ("QC", "Aromatic standard")


def test_reference_record_keeps_legacy_positional_argument_order():
    record = ReferenceLibraryRecord(
        "Legacy positional",
        "H2O",
        "raman",
        2,
        (1.0, 2.0),
        (),
    )

    assert record.data_type == "raman"
    assert record.schema_version == 2
    assert record.spectrum == (1.0, 2.0)
    assert record.description == ""


def test_reference_import_rejects_oversized_file_before_parsing(
    tmp_path: Path,
    monkeypatch,
):
    input_path = tmp_path / "oversized.json"
    input_path.write_text("{}" * 20, encoding="utf-8")
    monkeypatch.setattr(reference_library_io, "MAX_REFERENCE_FILE_BYTES", 16)

    with pytest.raises(ReferenceLibraryFormatError, match="file is too large"):
        read_reference_json(input_path)


def test_reference_export_rejects_excessive_aggregate_points(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(reference_library_io, "MAX_TOTAL_SPECTRUM_POINTS", 3)
    output_path = tmp_path / "too-many-points.json"
    records = [
        ReferenceLibraryRecord(name="One", spectrum=(1.0, 2.0)),
        ReferenceLibraryRecord(name="Two", spectrum=(3.0, 4.0)),
    ]

    with pytest.raises(
        ReferenceLibraryFormatError,
        match="too many spectrum points",
    ):
        write_reference_json(output_path, records)
    assert not output_path.exists()


def test_direct_reference_import_rejects_oversized_collection_before_mutation(
    monkeypatch,
):
    identifier = SpectrumIdentifier(":memory:")
    monkeypatch.setattr(reference_library_io, "MAX_TOTAL_SPECTRUM_POINTS", 3)
    try:
        result = identifier.import_reference_records(
            [
                ReferenceLibraryRecord(name="One", spectrum=(1.0, 2.0)),
                ReferenceLibraryRecord(name="Two", spectrum=(3.0, 4.0)),
            ]
        )

        assert result.failed == 2
        assert identifier.list_references() == []
    finally:
        identifier.close()


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
