from datetime import datetime

from python_analyzer.analysis.models import AnalysisSettings
from python_analyzer.analysis.processing_passport import build_processing_passport


def make_settings(**overrides):
    values = {
        "sample_rate": 1000.0,
        "filter_type": "median",
        "filter_params": {"window_size": 5},
        "baseline_enabled": True,
        "baseline_method": "improved",
        "peak_threshold": 0.05,
        "peak_prominence": 0.0,
        "peak_distance": 1,
        "normalize_area": False,
        "peak_min_snr": 0.0,
        "window_type": "hann",
        "spectrum_smoothing_enabled": False,
        "spectrum_smoothing_method": "savgol",
        "spectrum_smoothing_window": 7,
        "peak_frequency_tolerance": 5.0,
        "data_type": "generic",
    }
    values.update(overrides)
    return AnalysisSettings(**values)


def passport_dict(passport):
    return dict(passport.rows)


def test_processing_passport_records_reproducibility_fields():
    passport = build_processing_passport(
        settings=make_settings(
            sample_rate=2500.0,
            window_type="hamming",
            normalize_area=True,
            peak_min_snr=3.5,
            spectrum_smoothing_enabled=True,
            spectrum_smoothing_method="median",
            spectrum_smoothing_window=9,
            data_type="raman",
        ),
        result={
            "sample_rate": 2500.0,
            "normalization": "area",
            "spectrum_smoothed": True,
            "spectrum_smoothing_method": "median",
            "spectrum_smoothing_window": 9,
        },
        source_file_name="sample.csv",
        data_points_count=128,
        peaks_count=7,
        app_version="0.2.0",
        rust_core_version="0.2.0-rust",
        generated_at=datetime(2026, 7, 24, 12, 30, 0),
        method_name="Raman QC",
        accepted_peaks=6,
        rejected_peaks=1,
    )

    rows = passport_dict(passport)

    assert rows["Generated at"] == "2026-07-24 12:30:00"
    assert rows["Source file"] == "sample.csv"
    assert rows["Sample rate"] == "2500 Hz"
    assert rows["FFT window"] == "hamming"
    assert rows["Spectrum smoothing"] == "median/9"
    assert rows["Normalization"] == "area"
    assert rows["Data type"] == "raman"
    assert rows["Minimum SNR"] == "3.5"
    assert rows["Accepted peaks"] == "6"
    assert rows["Rejected peaks"] == "1"


def test_processing_passport_does_not_export_private_paths_or_sensitive_values():
    passport = build_processing_passport(
        settings=make_settings(
            filter_params={
                "window_size": 7,
                "source_file": "/laboratory/private/input.csv",
                "nested": {
                    "safe_value": 42,
                    "api_key": "abc123",
                    "token_hint": "secret-token",
                },
            }
        ),
        result={
            "processing_warnings": [
                "/laboratory/private/raw.csv could not be reused",
                "fallback peak was used",
            ]
        },
        source_file_name="/laboratory/private/input.csv",
        data_points_count=64,
        peaks_count=1,
        app_version="0.2.0",
        rust_core_version="0.2.0-rust",
        generated_at=datetime(2026, 7, 24, 12, 30, 0),
    )

    serialized = "\n".join(f"{label}: {value}" for label, value in passport.rows)
    rows = passport_dict(passport)

    assert rows["Source file"] == "input.csv"
    assert "/laboratory/private" not in serialized
    assert "private/input.csv" not in serialized
    assert "abc123" not in serialized
    assert "secret-token" not in serialized
    assert "fallback peak was used" in serialized
