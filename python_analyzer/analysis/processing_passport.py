"""Processing passport helpers for reproducible analysis exports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import PurePath
from typing import Any

from python_analyzer.analysis.models import AnalysisSettings
from python_analyzer.analysis.windowing import normalize_fft_window_type
from python_analyzer.core.identification import normalize_data_type


SENSITIVE_KEY_PARTS = ("path", "file", "token", "secret", "password", "api_key")
MAX_PUBLIC_TEXT_LENGTH = 160


@dataclass(frozen=True)
class ProcessingPassport:
    """Public, sanitized snapshot of the processing context."""

    rows: tuple[tuple[str, str], ...]


def build_processing_passport(
    *,
    settings: AnalysisSettings,
    result: Mapping[str, Any] | None,
    source_file_name: str,
    data_points_count: int,
    peaks_count: int,
    app_version: str,
    rust_core_version: str,
    generated_at: datetime,
    method_name: str = "custom",
    accepted_peaks: int | None = None,
    rejected_peaks: int | None = None,
) -> ProcessingPassport:
    """Build a sanitized processing passport for reports.

    The passport is intentionally export-safe: it stores reproducibility data
    while reducing filesystem-looking values to public labels.
    """

    result = result if isinstance(result, Mapping) else {}
    rows: list[tuple[str, str]] = [
        ("Generated at", generated_at.strftime("%Y-%m-%d %H:%M:%S")),
        ("App version", _safe_text(app_version)),
        ("Rust core", _safe_text(rust_core_version)),
        ("Source file", _safe_file_label(source_file_name)),
        ("Data points", _int_text(data_points_count)),
        ("Peaks found", _int_text(peaks_count)),
    ]
    if accepted_peaks is not None:
        rows.append(("Accepted peaks", _int_text(accepted_peaks)))
    if rejected_peaks is not None:
        rows.append(("Rejected peaks", _int_text(rejected_peaks)))

    rows.extend(
        [
            ("Analysis method", _safe_text(method_name or "custom")),
            ("Sample rate", f"{_sample_rate(result, settings):g} Hz"),
            ("FFT window", normalize_fft_window_type(settings.window_type)),
            ("Signal filter", _safe_text(settings.filter_type or "none")),
            ("Filter params", _public_mapping_text(settings.filter_params)),
            ("Baseline", _baseline_text(result, settings)),
            ("Spectrum smoothing", _smoothing_text(result, settings)),
            ("Normalization", _normalization_text(result, settings)),
            ("Data type", normalize_data_type(settings.data_type)),
            ("Peak tolerance", f"{_finite_float(settings.peak_frequency_tolerance, 5.0):g} Hz"),
            ("Threshold", f"{_finite_float(settings.peak_threshold, 0.05):g}"),
            ("Prominence", _prominence_text(settings.peak_prominence)),
            ("Minimum SNR", _min_snr_text(settings.peak_min_snr)),
            ("Distance", f"{_finite_int(settings.peak_distance, 1)} points"),
            ("Processing warnings", _warnings_text(result)),
        ]
    )
    return ProcessingPassport(tuple(rows))


def _sample_rate(result: Mapping[str, Any], settings: AnalysisSettings) -> float:
    sample_rate = _finite_float(result.get("sample_rate"), settings.sample_rate)
    return sample_rate if sample_rate > 0.0 else 1.0


def _baseline_text(result: Mapping[str, Any], settings: AnalysisSettings) -> str:
    fallback = settings.baseline_method if settings.baseline_enabled else "none"
    return _safe_text(result.get("baseline_method", fallback) or fallback)


def _normalization_text(result: Mapping[str, Any], settings: AnalysisSettings) -> str:
    fallback = "area" if settings.normalize_area else "none"
    return _safe_text(result.get("normalization", fallback) or fallback)


def _smoothing_text(result: Mapping[str, Any], settings: AnalysisSettings) -> str:
    smoothing_enabled = bool(
        result.get("spectrum_smoothed", settings.spectrum_smoothing_enabled)
    )
    if not smoothing_enabled:
        return "disabled"
    method = _safe_text(
        result.get("spectrum_smoothing_method", settings.spectrum_smoothing_method)
    )
    window = _finite_int(
        result.get("spectrum_smoothing_window", settings.spectrum_smoothing_window),
        settings.spectrum_smoothing_window,
    )
    return f"{method}/{window}"


def _prominence_text(value: Any) -> str:
    prominence = _finite_float(value, 0.0)
    return "automatic" if prominence <= 0.0 else f"{prominence:g}"


def _min_snr_text(value: Any) -> str:
    min_snr = _finite_float(value, 0.0)
    return "disabled" if min_snr <= 0.0 else f"{min_snr:g}"


def _warnings_text(result: Mapping[str, Any]) -> str:
    raw_warnings = result.get("processing_warnings", result.get("warnings", ()))
    if isinstance(raw_warnings, str):
        warnings = [raw_warnings]
    elif isinstance(raw_warnings, Sequence):
        warnings = list(raw_warnings)
    else:
        warnings = []

    safe_warnings = [
        _safe_text(warning)
        for warning in warnings
        if _safe_text(warning)
    ]
    return "; ".join(safe_warnings) if safe_warnings else "none"


def _public_mapping_text(value: Any) -> str:
    if not isinstance(value, Mapping) or not value:
        return "{}"
    safe_mapping = {
        str(key): (
            "[redacted]"
            if _looks_sensitive_key(str(key))
            else _public_value(item)
        )
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
    }
    return json.dumps(safe_mapping, sort_keys=True, separators=(",", ":"))


def _public_value(value: Any) -> Any:
    if value is None or isinstance(value, (int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[redacted]"
                if _looks_sensitive_key(str(key))
                else _public_value(item)
            )
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_public_value(item) for item in value]
    return _safe_text(value)


def _safe_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if _looks_like_private_path(text):
        return "[redacted]"
    return text[:MAX_PUBLIC_TEXT_LENGTH]


def _safe_file_label(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return "unknown"
    text = text.replace("\\", "/")
    if "/" in text:
        text = text.rstrip("/").split("/")[-1] or "selected file"
    return PurePath(text).name[:MAX_PUBLIC_TEXT_LENGTH] or "selected file"


def _looks_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _looks_like_private_path(text: str) -> bool:
    normalized = text.strip()
    lowered = normalized.lower()
    return (
        normalized.startswith(("~", "/", "\\"))
        or "\\users\\" in lowered
        or "/users/" in lowered
        or "/home/" in lowered
        or "/private/" in lowered
        or "/var/" in lowered
        or len(normalized) >= 3
        and normalized[1:3] == ":\\"
    )


def _finite_float(value: Any, default: float) -> float:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return default
    return numeric_value if math.isfinite(numeric_value) else default


def _finite_int(value: Any, default: int) -> int:
    try:
        numeric_value = int(value)
    except (TypeError, ValueError):
        return default
    return numeric_value


def _int_text(value: Any) -> str:
    return str(max(0, _finite_int(value, 0)))
