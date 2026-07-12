import json

import pytest

from python_analyzer.analysis.method_presets import (
    METHOD_PRESETS_KEY,
    analysis_settings_from_dict,
    delete_method_preset,
    list_method_preset_names,
    load_method_preset,
    save_method_preset,
    sanitize_preset_name,
)
from python_analyzer.analysis.models import AnalysisSettings


class FakeSettings:
    def __init__(self):
        self.values = {}
        self.synced = False

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        self.synced = True


def make_settings(**overrides):
    values = {
        "sample_rate": 2500.0,
        "filter_type": "median",
        "filter_params": {"window_size": 7},
        "baseline_enabled": True,
        "baseline_method": "improved",
        "peak_threshold": 0.04,
        "peak_prominence": 0.2,
        "peak_distance": 5,
        "normalize_area": True,
        "peak_min_snr": 8.0,
        "window_type": "hamming",
        "spectrum_smoothing_enabled": True,
        "spectrum_smoothing_method": "savgol",
        "spectrum_smoothing_window": 9,
        "peak_frequency_tolerance": 2.5,
        "data_type": "raman",
    }
    values.update(overrides)
    return AnalysisSettings(**values)


def test_save_list_load_and_delete_method_preset():
    store = FakeSettings()
    settings = make_settings()

    saved_name = save_method_preset(store, "  Raman   screening  ", settings)

    assert saved_name == "Raman screening"
    assert store.synced is True
    assert list_method_preset_names(store) == ["Raman screening"]

    loaded = load_method_preset(store, "Raman screening")
    assert loaded == settings

    assert delete_method_preset(store, "Raman screening") is True
    assert list_method_preset_names(store) == []


def test_empty_method_preset_name_is_rejected():
    with pytest.raises(ValueError):
        sanitize_preset_name("   ")


def test_invalid_preset_store_is_ignored():
    store = FakeSettings()
    store.setValue(METHOD_PRESETS_KEY, "{not json")

    assert list_method_preset_names(store) == []
    assert load_method_preset(store, "Missing") is None


def test_deserialization_clamps_non_finite_and_out_of_range_values():
    settings = analysis_settings_from_dict(
        {
            "sample_rate": float("nan"),
            "peak_threshold": 99,
            "peak_distance": -10,
            "spectrum_smoothing_window": 8,
            "window_type": "unsupported",
            "data_type": "unknown",
        }
    )

    assert settings.sample_rate == 1000.0
    assert settings.peak_threshold == 1.0
    assert settings.peak_distance == 1
    assert settings.spectrum_smoothing_window == 9
    assert settings.window_type == "hann"
    assert settings.data_type == "generic"


def test_preset_json_contains_only_analysis_settings():
    store = FakeSettings()
    save_method_preset(
        store,
        "Method",
        make_settings(
            filter_params={
                "window_size": 7,
                "file_path": "private/sample.csv",
                "api_key": "not-for-presets",
            }
        ),
    )

    payload = json.loads(store.value(METHOD_PRESETS_KEY))

    assert set(payload) == {"version", "presets"}
    assert "Method" in payload["presets"]
    assert "file_path" not in json.dumps(payload)
    assert "api_key" not in json.dumps(payload)
    assert "private/sample.csv" not in json.dumps(payload)
