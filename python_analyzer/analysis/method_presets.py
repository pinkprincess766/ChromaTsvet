"""Persistent analysis-method presets.

Presets store only analysis parameters. They deliberately do not store source
file paths, export paths, or user-library records.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from typing import Any

from python_analyzer.analysis.models import AnalysisSettings
from python_analyzer.analysis.windowing import DEFAULT_FFT_WINDOW, normalize_fft_window_type
from python_analyzer.core.identification import normalize_data_type


METHOD_PRESETS_KEY = "analysis/method_presets_json"
METHOD_PRESETS_VERSION = 1
MAX_PRESET_NAME_LENGTH = 80
SENSITIVE_KEY_PARTS = ("path", "file", "token", "secret", "password", "api_key")


def list_method_preset_names(settings_store: Any) -> list[str]:
    """Return saved preset names in stable UI order."""

    store = _load_store(settings_store)
    return sorted(store)


def load_method_preset(settings_store: Any, name: str) -> AnalysisSettings | None:
    """Load one preset by name, returning None when it is absent or invalid."""

    preset_name = sanitize_preset_name(name)
    store = _load_store(settings_store)
    payload = store.get(preset_name)
    if not isinstance(payload, Mapping):
        return None
    return analysis_settings_from_dict(payload)


def save_method_preset(
    settings_store: Any,
    name: str,
    analysis_settings: AnalysisSettings,
) -> str:
    """Persist a preset and return its normalized display name."""

    preset_name = sanitize_preset_name(name)
    store = _load_store(settings_store)
    store[preset_name] = analysis_settings_to_dict(analysis_settings)
    _save_store(settings_store, store)
    return preset_name


def delete_method_preset(settings_store: Any, name: str) -> bool:
    """Delete a preset. Returns True when an entry was removed."""

    preset_name = sanitize_preset_name(name)
    store = _load_store(settings_store)
    if preset_name not in store:
        return False
    del store[preset_name]
    _save_store(settings_store, store)
    return True


def sanitize_preset_name(name: str) -> str:
    """Normalize a user-facing preset name without leaking filesystem data."""

    preset_name = " ".join(str(name or "").strip().split())
    if not preset_name:
        raise ValueError("method preset name cannot be empty")
    return preset_name[:MAX_PRESET_NAME_LENGTH]


def analysis_settings_to_dict(settings: AnalysisSettings) -> dict[str, Any]:
    """Serialize analysis settings to a JSON-safe dictionary."""

    return {
        "sample_rate": _finite_float(settings.sample_rate, 1000.0, 0.001, 10_000_000.0),
        "filter_type": str(settings.filter_type or "none"),
        "filter_params": _json_safe_mapping(settings.filter_params),
        "baseline_enabled": bool(settings.baseline_enabled),
        "baseline_method": _choice(settings.baseline_method, {"improved", "simple"}, "improved"),
        "peak_threshold": _finite_float(settings.peak_threshold, 0.05, 0.001, 1.0),
        "peak_prominence": _finite_float(settings.peak_prominence, 0.0, 0.0, 1_000_000.0),
        "peak_distance": _finite_int(settings.peak_distance, 1, 1, 10_000),
        "normalize_area": bool(settings.normalize_area),
        "peak_min_snr": _finite_float(settings.peak_min_snr, 0.0, 0.0, 1_000_000.0),
        "window_type": normalize_fft_window_type(settings.window_type),
        "spectrum_smoothing_enabled": bool(settings.spectrum_smoothing_enabled),
        "spectrum_smoothing_method": _choice(
            settings.spectrum_smoothing_method,
            {"savgol", "median"},
            "savgol",
        ),
        "spectrum_smoothing_window": _odd_int(settings.spectrum_smoothing_window, 7, 3, 501),
        "peak_frequency_tolerance": _finite_float(
            settings.peak_frequency_tolerance,
            5.0,
            0.1,
            1_000_000.0,
        ),
        "data_type": normalize_data_type(settings.data_type),
    }


def analysis_settings_from_dict(payload: Mapping[str, Any]) -> AnalysisSettings:
    """Deserialize one preset, clamping unsafe or non-finite values."""

    return AnalysisSettings(
        sample_rate=_finite_float(payload.get("sample_rate"), 1000.0, 0.001, 10_000_000.0),
        filter_type=str(payload.get("filter_type") or "none"),
        filter_params=_mapping_or_empty(payload.get("filter_params")),
        baseline_enabled=bool(payload.get("baseline_enabled", True)),
        baseline_method=_choice(payload.get("baseline_method"), {"improved", "simple"}, "improved"),
        peak_threshold=_finite_float(payload.get("peak_threshold"), 0.05, 0.001, 1.0),
        peak_prominence=_finite_float(payload.get("peak_prominence"), 0.0, 0.0, 1_000_000.0),
        peak_distance=_finite_int(payload.get("peak_distance"), 1, 1, 10_000),
        normalize_area=bool(payload.get("normalize_area", False)),
        peak_min_snr=_finite_float(payload.get("peak_min_snr"), 0.0, 0.0, 1_000_000.0),
        window_type=normalize_fft_window_type(payload.get("window_type", DEFAULT_FFT_WINDOW)),
        spectrum_smoothing_enabled=bool(payload.get("spectrum_smoothing_enabled", False)),
        spectrum_smoothing_method=_choice(
            payload.get("spectrum_smoothing_method"),
            {"savgol", "median"},
            "savgol",
        ),
        spectrum_smoothing_window=_odd_int(
            payload.get("spectrum_smoothing_window"),
            7,
            3,
            501,
        ),
        peak_frequency_tolerance=_finite_float(
            payload.get("peak_frequency_tolerance"),
            5.0,
            0.1,
            1_000_000.0,
        ),
        data_type=normalize_data_type(payload.get("data_type", "generic")),
    )


def _load_store(settings_store: Any) -> dict[str, dict[str, Any]]:
    raw_value = settings_store.value(METHOD_PRESETS_KEY, "")
    if not raw_value:
        return {}
    try:
        payload = json.loads(str(raw_value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, Mapping) or payload.get("version") != METHOD_PRESETS_VERSION:
        return {}
    presets = payload.get("presets")
    if not isinstance(presets, Mapping):
        return {}

    clean_store: dict[str, dict[str, Any]] = {}
    for name, preset_payload in presets.items():
        try:
            preset_name = sanitize_preset_name(str(name))
        except ValueError:
            continue
        if isinstance(preset_payload, Mapping):
            clean_store[preset_name] = dict(preset_payload)
    return clean_store


def _save_store(settings_store: Any, store: Mapping[str, Mapping[str, Any]]) -> None:
    payload = {
        "version": METHOD_PRESETS_VERSION,
        "presets": {
            sanitize_preset_name(name): dict(settings)
            for name, settings in sorted(store.items())
        },
    }
    settings_store.setValue(
        METHOD_PRESETS_KEY,
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
    )
    sync = getattr(settings_store, "sync", None)
    if callable(sync):
        sync()


def _finite_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric_value):
        return default
    return max(minimum, min(maximum, numeric_value))


def _finite_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        numeric_value = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, numeric_value))


def _odd_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    numeric_value = _finite_int(value, default, minimum, maximum)
    if numeric_value % 2 == 0:
        numeric_value = min(maximum, numeric_value + 1)
    return numeric_value


def _choice(value: Any, allowed: set[str], default: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else default


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return _json_safe_mapping(value)


def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    safe_values = {}
    for key, item in value.items():
        safe_key = str(key)
        if _looks_sensitive_key(safe_key):
            continue
        safe_values[safe_key] = _json_safe_value(item)
    return safe_values


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    return str(value)


def _looks_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)
