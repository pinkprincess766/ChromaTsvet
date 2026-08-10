import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from python_analyzer.analysis.models import AnalysisSettings
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
        matches=[SimpleNamespace(substance_name="Reference", formula="R", score=0.91, compared_points=1)],
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
