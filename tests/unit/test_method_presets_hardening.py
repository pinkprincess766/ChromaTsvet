import json

from python_analyzer.analysis.method_presets import (
    MAX_PRESET_NAME_LENGTH,
    METHOD_PRESETS_KEY,
    METHOD_PRESETS_VERSION,
    delete_method_preset,
    list_method_preset_names,
    load_method_preset,
    save_method_preset,
    sanitize_preset_name,
)
from tests.unit.test_method_presets import FakeSettings, make_settings


class StableStringObject:
    def __str__(self):
        return "stable-object-value"


def stored_payload(store):
    return json.loads(store.value(METHOD_PRESETS_KEY))


def test_wrong_store_version_is_ignored():
    store = FakeSettings()
    store.setValue(
        METHOD_PRESETS_KEY,
        json.dumps({"version": METHOD_PRESETS_VERSION + 1, "presets": {}}),
    )

    assert list_method_preset_names(store) == []
    assert load_method_preset(store, "Anything") is None


def test_non_mapping_preset_container_is_ignored():
    store = FakeSettings()
    store.setValue(
        METHOD_PRESETS_KEY,
        json.dumps({"version": METHOD_PRESETS_VERSION, "presets": ["not", "a", "map"]}),
    )

    assert list_method_preset_names(store) == []


def test_long_preset_names_are_truncated_to_public_display_limit():
    raw_name = "A" * (MAX_PRESET_NAME_LENGTH + 20)

    preset_name = sanitize_preset_name(raw_name)

    assert len(preset_name) == MAX_PRESET_NAME_LENGTH
    assert preset_name == "A" * MAX_PRESET_NAME_LENGTH


def test_sanitized_duplicate_names_overwrite_the_same_preset_slot():
    store = FakeSettings()
    save_method_preset(store, "Raman   QC", make_settings(sample_rate=1000.0))
    save_method_preset(store, " Raman QC ", make_settings(sample_rate=2500.0))

    assert list_method_preset_names(store) == ["Raman QC"]
    assert load_method_preset(store, "Raman QC").sample_rate == 2500.0


def test_nested_sensitive_filter_params_are_removed_before_persistence():
    store = FakeSettings()
    save_method_preset(
        store,
        "Sensitive nested values",
        make_settings(
            filter_params={
                "window_size": 7,
                "nested": {
                    "safe_value": 42,
                    "api_key": "do-not-store",
                    "secret_note": "do-not-store-either",
                },
                "source_file": "private.csv",
                "token_hint": "private-token",
            }
        ),
    )

    serialized = json.dumps(stored_payload(store), sort_keys=True)
    loaded = load_method_preset(store, "Sensitive nested values")

    assert loaded.filter_params["window_size"] == 7
    assert loaded.filter_params["nested"] == {"safe_value": 42}
    assert "do-not-store" not in serialized
    assert "private.csv" not in serialized
    assert "private-token" not in serialized


def test_non_json_filter_param_values_are_stored_as_stable_strings():
    store = FakeSettings()
    save_method_preset(
        store,
        "Object params",
        make_settings(filter_params={"custom": StableStringObject()}),
    )

    loaded = load_method_preset(store, "Object params")

    assert loaded.filter_params == {"custom": "stable-object-value"}


def test_delete_missing_preset_returns_false_without_rewriting_store():
    store = FakeSettings()
    save_method_preset(store, "Existing", make_settings())
    before = store.value(METHOD_PRESETS_KEY)

    removed = delete_method_preset(store, "Missing")

    assert removed is False
    assert store.value(METHOD_PRESETS_KEY) == before
