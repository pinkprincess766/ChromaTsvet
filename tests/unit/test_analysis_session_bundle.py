import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import python_analyzer.analysis.session_bundle as session_bundle
from python_analyzer.analysis.models import (
    AnalysisSettings,
    PeakBasedMatchResult,
    PeakMatch,
    ReferencePeak,
)
from python_analyzer.analysis.peak_review import (
    PEAK_REVIEW_REJECTED,
    PEAK_REVIEW_SUSPICIOUS,
    PeakReview,
)
from python_analyzer.analysis.session_bundle import (
    SESSION_SCHEMA_VERSION,
    SessionFormatError,
    build_analysis_session_payload,
    read_analysis_session,
    session_output_path,
    write_analysis_session,
)


def sample_settings():
    return AnalysisSettings(
        sample_rate=2000.0,
        filter_type="none",
        filter_params={},
        baseline_enabled=True,
        baseline_method="improved",
        peak_threshold=0.04,
        peak_prominence=0.2,
        peak_distance=4,
        normalize_area=True,
        peak_min_snr=5.0,
        window_type="hann",
        spectrum_smoothing_enabled=True,
        spectrum_smoothing_method="median",
        spectrum_smoothing_window=9,
        peak_frequency_tolerance=2.5,
        data_type="raman",
    )


def sample_peak():
    return SimpleNamespace(
        frequency=125.5,
        position=251.0,
        intensity=0.84,
        prominence=0.22,
        baseline_level=0.02,
        left_base=240.0,
        right_base=260.0,
        width=3.2,
        width_hz=1.6,
        area=2.4,
        noise=0.03,
        snr=18.0,
        is_global_max=False,
        source="manual",
    )


def sample_payload():
    return build_analysis_session_payload(
        source_file_name="/Users/scientist/private/raw/sample.csv",
        data_points_count=512,
        settings=sample_settings(),
        method_name="Raman QC",
        result={
            "spectrum": [0.0, 1.0, 0.25],
            "frequency_axis": [0.0, 50.0, 100.0],
            "sample_rate": 2000.0,
            "normalized": True,
            "processing_warnings": ["/Users/scientist/private/raw/sample.csv"],
        },
        frequency_axis=[0.0, 50.0, 100.0],
        spectrum=[0.0, 1.0, 0.25],
        peaks=[sample_peak()],
        peak_reviews=[
            PeakReview(
                PEAK_REVIEW_REJECTED,
                "rejected by user",
                ("manual_override",),
                user_modified=True,
            )
        ],
        matches=[
            SimpleNamespace(
                substance_name="Reference",
                formula="R",
                score=0.91,
                compared_points=1,
            )
        ],
        app_version="0.2.0",
        rust_core_version="0.1.0",
        processing_passport_rows=[
            ("Source file", "/Users/scientist/private/raw/sample.csv"),
            ("Analysis method", "Raman QC"),
        ],
    )


def test_session_roundtrip_preserves_analysis_state_without_private_paths(tmp_path):
    output_path = tmp_path / "analysis.chromatsvet-session.json"
    payload = sample_payload()

    write_analysis_session(output_path, payload)
    raw_json = output_path.read_text(encoding="utf-8")
    restored = read_analysis_session(output_path)

    assert "/Users/scientist/private" not in raw_json
    assert restored["schema_version"] == SESSION_SCHEMA_VERSION
    assert restored["source_file_name"] == "sample.csv"
    assert restored["settings"].data_type == "raman"
    assert restored["settings"].spectrum_smoothing_window == 9
    assert restored["result"]["peaks"][0].frequency == pytest.approx(125.5)
    assert restored["result"]["peak_reviews"][0].status == PEAK_REVIEW_REJECTED
    assert restored["result"]["peak_reviews"][0].user_modified is True
    assert restored["result"]["matches"][0].substance_name == "Reference"


def test_session_rejects_non_finite_spectrum_values(tmp_path):
    output_path = tmp_path / "bad.chromatsvet-session.json"
    payload = sample_payload()
    payload["result"]["spectrum"][1] = float("nan")
    output_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SessionFormatError, match="non-finite"):
        read_analysis_session(output_path)


def test_session_rejects_review_count_mismatch(tmp_path):
    output_path = tmp_path / "bad.chromatsvet-session.json"
    payload = sample_payload()
    payload["result"]["peak_reviews"] = []
    output_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SessionFormatError, match="review count"):
        read_analysis_session(output_path)


def test_session_clamps_unknown_review_status_to_suspicious(tmp_path):
    output_path = tmp_path / "future.chromatsvet-session.json"
    payload = sample_payload()
    payload["result"]["peak_reviews"][0]["status"] = "future-state"
    output_path.write_text(json.dumps(payload), encoding="utf-8")

    restored = read_analysis_session(output_path)

    assert restored["result"]["peak_reviews"][0].status == PEAK_REVIEW_SUSPICIOUS


def test_session_output_path_adds_chromatsvet_suffix_when_missing():
    assert session_output_path(Path("analysis")).endswith(".chromatsvet-session.json")
    assert session_output_path(Path("analysis.json")).endswith("analysis.json")


def test_session_roundtrip_preserves_peak_match_diagnostics(tmp_path):
    payload = build_analysis_session_payload(
        source_file_name="sample.csv",
        data_points_count=3,
        settings=sample_settings(),
        method_name="Raman QC",
        result={"spectrum": [0.0, 1.0, 0.0], "frequency_axis": [0.0, 1.0, 2.0]},
        frequency_axis=[0.0, 1.0, 2.0],
        spectrum=[0.0, 1.0, 0.0],
        peaks=[sample_peak()],
        peak_reviews=[PeakReview("accepted", "test")],
        matches=[
            PeakBasedMatchResult(
                substance_name="Candidate",
                formula="C",
                score=0.8,
                matched_peaks=[PeakMatch(100.0, 101.0, 1.0, 0.9, 0.8)],
                unmatched_unknown=[ReferencePeak(200.0, 0.4)],
                unmatched_reference=[ReferencePeak(300.0, 0.3)],
                num_matched=1,
                unknown_peak_count=2,
                reference_peak_count=2,
                sample_coverage=0.5,
                reference_coverage=0.5,
                mean_frequency_error=1.0,
                max_frequency_error=1.0,
                evidence_level="weak",
            )
        ],
        app_version="0.3.0",
        rust_core_version="0.1.0",
    )
    output_path = tmp_path / "diagnostics.chromatsvet-session.json"

    write_analysis_session(output_path, payload)
    restored = read_analysis_session(output_path)["result"]["matches"][0]

    assert restored.method == "peak"
    assert restored.evidence_level == "weak"
    assert restored.num_matched == 1
    assert restored.sample_coverage == pytest.approx(0.5)
    assert restored.matched_peaks[0].frequency_diff == pytest.approx(1.0)
    assert restored.unmatched_unknown[0].frequency == pytest.approx(200.0)
    assert restored.unmatched_reference[0].frequency == pytest.approx(300.0)


def test_session_rejects_non_finite_peak_match_diagnostics(tmp_path):
    payload = sample_payload()
    payload["result"]["matches"][0].update(
        {
            "method": "peak",
            "matched_peaks": [
                {
                    "unknown_frequency": 100.0,
                    "reference_frequency": 100.0,
                    "frequency_diff": float("nan"),
                    "intensity_ratio": 1.0,
                    "score": 1.0,
                }
            ],
            "unmatched_unknown": [],
            "unmatched_reference": [],
        }
    )
    output_path = tmp_path / "bad-match.chromatsvet-session.json"
    output_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SessionFormatError, match="non-finite"):
        read_analysis_session(output_path)


def test_session_rejects_match_diagnostics_above_aggregate_budget(
    tmp_path,
    monkeypatch,
):
    payload = sample_payload()
    payload["result"]["matches"][0].update(
        {
            "method": "peak",
            "matched_peaks": [],
            "unmatched_unknown": [
                {"frequency": 100.0, "intensity": 1.0},
            ],
            "unmatched_reference": [],
        }
    )
    output_path = tmp_path / "oversized-details.chromatsvet-session.json"
    output_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(session_bundle, "MAX_SESSION_TOTAL_MATCH_DETAIL_PEAKS", 0)

    with pytest.raises(SessionFormatError, match="diagnostics are too large"):
        read_analysis_session(output_path)


def test_session_rejects_file_above_size_limit_without_parsing(tmp_path, monkeypatch):
    output_path = tmp_path / "oversized.chromatsvet-session.json"
    output_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(session_bundle, "MAX_SESSION_FILE_BYTES", 1)

    with pytest.raises(SessionFormatError, match="file is too large"):
        read_analysis_session(output_path)
