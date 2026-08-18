from __future__ import annotations

import logging
from types import SimpleNamespace

import numpy as np
import pytest
from PyQt5.QtWidgets import QLabel, QTabWidget, QTableWidget

import python_analyzer.gui.identification_details as identification_details
from python_analyzer.analysis.identification_evidence import (
    EVIDENCE_INSUFFICIENT,
    EVIDENCE_MODERATE,
    EVIDENCE_STRONG,
    EVIDENCE_WEAK,
    classify_match_evidence,
    summarize_match_evidence,
)
from python_analyzer.analysis.models import (
    PeakBasedMatchResult,
    PeakMatch,
    ReferencePeak,
)
from python_analyzer.core.identification import SpectrumIdentifier
from python_analyzer.gui.identification_details import (
    IdentificationDetailsDialog,
    identification_overview_values,
)


@pytest.mark.parametrize(
    ("score", "matched", "sample_coverage", "reference_coverage", "expected"),
    [
        (0.99, 1, 1.0, 1.0, EVIDENCE_WEAK),
        (0.65, 2, 0.40, 0.40, EVIDENCE_MODERATE),
        (0.85, 3, 0.60, 0.60, EVIDENCE_STRONG),
        (float("nan"), 5, 1.0, 1.0, EVIDENCE_INSUFFICIENT),
        (1.0, 0, 1.0, 1.0, EVIDENCE_INSUFFICIENT),
    ],
)
def test_evidence_bands_are_conservative_at_boundaries(
    score,
    matched,
    sample_coverage,
    reference_coverage,
    expected,
):
    assert classify_match_evidence(
        score=score,
        matched_count=matched,
        sample_coverage=sample_coverage,
        reference_coverage=reference_coverage,
    ) == expected


def test_evidence_summary_ignores_non_finite_frequency_errors():
    matches = [
        PeakMatch(100.0, 101.0, 1.0, 1.0, 0.9),
        PeakMatch(200.0, 200.0, float("nan"), 1.0, 0.9),
    ]

    evidence = summarize_match_evidence(
        score=0.8,
        matches=matches,
        unknown_peak_count=4,
        reference_peak_count=2,
    )

    assert evidence.sample_coverage == pytest.approx(0.5)
    assert evidence.reference_coverage == pytest.approx(1.0)
    assert evidence.mean_frequency_error == pytest.approx(1.0)
    assert evidence.max_frequency_error == pytest.approx(1.0)


def test_evidence_summary_rejects_non_numeric_values_and_zero_denominators():
    evidence = summarize_match_evidence(
        score="not-a-number",
        matches=[SimpleNamespace(frequency_diff="invalid")],
        unknown_peak_count=0,
        reference_peak_count=0,
    )

    assert evidence.sample_coverage == 0.0
    assert evidence.reference_coverage == 0.0
    assert evidence.mean_frequency_error is None
    assert evidence.max_frequency_error is None
    assert evidence.evidence_level == EVIDENCE_INSUFFICIENT


def test_peak_candidates_are_ranked_deterministically_with_full_diagnostics():
    identifier = SpectrumIdentifier(":memory:")
    try:
        identifier.add_reference(
            "Zeta",
            None,
            "Z",
            peaks=[
                ReferencePeak(100.0, 1.0),
                ReferencePeak(200.0, 0.8),
                ReferencePeak(300.0, 0.6),
            ],
            data_type="raman",
        )
        identifier.add_reference(
            "Alpha",
            None,
            "A",
            peaks=[
                ReferencePeak(100.0, 1.0),
                ReferencePeak(200.0, 0.8),
                ReferencePeak(300.0, 0.6),
            ],
            data_type="raman",
        )
        unknown = [
            ReferencePeak(100.0, 1.0),
            ReferencePeak(200.0, 0.8),
            ReferencePeak(300.0, 0.6),
        ]

        results = identifier.find_peak_matches(
            unknown,
            frequency_tolerance=2.0,
            data_type="raman",
        )
    finally:
        identifier.close()

    assert [result.substance_name for result in results] == ["Alpha", "Zeta"]
    assert results[0].num_matched == 3
    assert results[0].sample_coverage == pytest.approx(1.0)
    assert results[0].reference_coverage == pytest.approx(1.0)
    assert results[0].mean_frequency_error == pytest.approx(0.0)
    assert results[0].evidence_level == EVIDENCE_STRONG
    assert len(results[0].matched_peaks) == 3
    assert results[0].unmatched_unknown == []
    assert results[0].unmatched_reference == []


def test_malformed_legacy_reference_is_skipped_without_echoing_its_name(caplog):
    identifier = SpectrumIdentifier(":memory:")
    unsafe_name = "/Users/scientist/private/reference\nforged"
    try:
        identifier.add_reference("Safe", [1.0, 2.0], "S")
        identifier.conn.execute(
            "UPDATE compounds SET name = ?, spectrum = ? WHERE name = ?",
            (unsafe_name, "[1.0, NaN]", "Safe"),
        )
        identifier.conn.commit()

        with caplog.at_level(logging.WARNING, logger="chromatsvet.identification"):
            results = identifier.find_matches(np.asarray([1.0, 2.0]))
    finally:
        identifier.close()

    assert results == []
    assert "Skipping malformed legacy reference record" in caplog.text
    assert "scientist" not in caplog.text
    assert "forged" not in caplog.text


def test_overview_and_dialog_expose_peak_evidence_without_claiming_identity(qapp):
    match = PeakBasedMatchResult(
        substance_name="Reference\nA",
        formula="RA",
        score=0.91,
        matched_peaks=[PeakMatch(100.0, 100.5, 0.5, 1.1, 0.9)],
        unmatched_unknown=[ReferencePeak(200.0, 0.4)],
        unmatched_reference=[ReferencePeak(300.0, 0.3)],
        num_matched=1,
        unknown_peak_count=2,
        reference_peak_count=2,
        sample_coverage=0.5,
        reference_coverage=0.5,
        mean_frequency_error=0.5,
        max_frequency_error=0.5,
        evidence_level=EVIDENCE_WEAK,
    )

    values = identification_overview_values(match)
    dialog = IdentificationDetailsDialog(None, match)
    try:
        tabs = dialog.findChild(QTabWidget)
        matched_table = tabs.widget(0)

        assert values == [
            "Reference A",
            "RA",
            "0.910",
            "1",
            "50.0%",
            "50.0%",
            "0.5000",
            "weak",
        ]
        assert tabs.count() == 3
        assert isinstance(matched_table, QTableWidget)
        assert matched_table.rowCount() == 1
        assert any(
            "validated chemical identification" in label.text()
            for label in dialog.findChildren(QLabel)
        )
    finally:
        dialog.close()


def test_details_dialog_caps_rows_from_large_untrusted_session(qapp, monkeypatch):
    monkeypatch.setattr(identification_details, "MAX_DETAIL_TABLE_ROWS", 1)
    match = PeakBasedMatchResult(
        substance_name="Candidate",
        formula="C",
        score=0.5,
        matched_peaks=[
            PeakMatch(100.0, 100.0, 0.0, 1.0, 1.0),
            PeakMatch(200.0, 200.0, 0.0, 1.0, 1.0),
        ],
        unmatched_unknown=[],
        unmatched_reference=[],
        num_matched=2,
    )

    dialog = IdentificationDetailsDialog(None, match)
    try:
        tabs = dialog.findChild(QTabWidget)

        assert tabs.tabText(0) == "Matched (1/2)"
        assert tabs.widget(0).rowCount() == 1
    finally:
        dialog.close()
