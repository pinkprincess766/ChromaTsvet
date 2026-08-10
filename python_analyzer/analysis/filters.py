"""Validated, high-performance filters for one-dimensional signals."""

from __future__ import annotations

from collections.abc import Mapping
from numbers import Integral
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

try:
    from scipy.ndimage import median_filter as scipy_median_filter
except ImportError as exc:  # The GUI reports this when a filter is applied.
    scipy_median_filter = None
    _SCIPY_IMPORT_ERROR = exc
else:
    _SCIPY_IMPORT_ERROR = None


FilterParams = dict[str, Any]

_AVAILABLE_FILTERS: dict[str, str] = {
    "none": "Без фильтра",
    "median": "Медианный фильтр",
}

_DEFAULT_PARAMS: dict[str, FilterParams] = {
    "none": {},
    "median": {"window_size": 5},
}

_MEDIAN_WINDOW_MIN = 3
_MEDIAN_WINDOW_MAX = 51


class FilterError(ValueError):
    """Base exception for invalid filter input or filter execution failures."""


class FilterDependencyError(FilterError):
    """Raised when a filter's required third-party dependency is unavailable."""


def get_available_filters() -> dict[str, str]:
    """Return filter identifiers mapped to user-facing labels."""
    return _AVAILABLE_FILTERS.copy()


def get_default_params(filter_type: str) -> FilterParams:
    """Return an independent copy of the default parameters for a filter."""
    normalized_type = _normalize_filter_type(filter_type)
    return _DEFAULT_PARAMS[normalized_type].copy()


def normalize_filter_settings(
    filter_type: str, params: Mapping[str, Any] | None = None
) -> tuple[str, FilterParams]:
    """Validate and normalize a filter identifier and its parameters."""
    normalized_type = _normalize_filter_type(filter_type)
    return normalized_type, _validate_params(normalized_type, params)


def apply_filter(
    signal: ArrayLike,
    filter_type: str,
    params: Mapping[str, Any] | None = None,
) -> NDArray[np.float64]:
    """Validate and filter a one-dimensional numeric signal.

    The returned array is always a writable, independent ``float64`` array.
    Empty signals are valid and are returned unchanged.

    Raises:
        FilterError: If the signal, filter type, or parameters are invalid.
        FilterDependencyError: If SciPy is unavailable for median filtering.
    """
    normalized_type, normalized_params = normalize_filter_settings(filter_type, params)
    values = _as_signal_array(signal)

    if values.size == 0 or normalized_type == "none":
        return values.copy()

    if scipy_median_filter is None:
        raise FilterDependencyError(
            "Median filtering requires scipy. Install it with 'python -m pip install scipy'."
        ) from _SCIPY_IMPORT_ERROR

    try:
        filtered = scipy_median_filter(
            values,
            size=normalized_params["window_size"],
            mode="nearest",
        )
    except Exception as exc:
        raise FilterError(f"Median filter failed: {exc}") from exc

    return np.asarray(filtered, dtype=np.float64)


def _normalize_filter_type(filter_type: str) -> str:
    if not isinstance(filter_type, str):
        raise FilterError("filter_type must be a string")

    normalized_type = filter_type.strip().lower()
    if normalized_type not in _AVAILABLE_FILTERS:
        available = ", ".join(_AVAILABLE_FILTERS)
        raise FilterError(
            f"Unknown filter type '{filter_type}'. Available filters: {available}"
        )
    return normalized_type


def _validate_params(
    filter_type: str, params: Mapping[str, Any] | None
) -> FilterParams:
    if params is None:
        supplied_params: FilterParams = {}
    elif isinstance(params, Mapping):
        try:
            supplied_params = dict(params)
        except Exception as exc:
            raise FilterError(f"filter params cannot be read: {exc}") from exc
    else:
        raise FilterError("filter params must be a mapping or None")

    allowed_params = set(_DEFAULT_PARAMS[filter_type])
    unknown_params = set(supplied_params) - allowed_params
    if unknown_params:
        names = ", ".join(sorted(map(str, unknown_params)))
        raise FilterError(f"Unsupported parameters for '{filter_type}': {names}")

    validated_params = get_default_params(filter_type)
    validated_params.update(supplied_params)

    if filter_type == "median":
        window_size = validated_params["window_size"]
        if isinstance(window_size, bool) or not isinstance(window_size, Integral):
            raise FilterError("window_size must be an integer")
        window_size = int(window_size)
        if not _MEDIAN_WINDOW_MIN <= window_size <= _MEDIAN_WINDOW_MAX:
            raise FilterError(
                f"window_size must be between {_MEDIAN_WINDOW_MIN} and "
                f"{_MEDIAN_WINDOW_MAX}"
            )
        if window_size % 2 == 0:
            raise FilterError("window_size must be odd")
        validated_params["window_size"] = window_size

    return validated_params


def _as_signal_array(signal: ArrayLike) -> NDArray[np.float64]:
    if signal is None or isinstance(signal, (str, bytes, bytearray)):
        raise FilterError("signal must be a one-dimensional numeric array")

    try:
        raw_values = np.asarray(signal)
    except Exception as exc:
        raise FilterError(f"signal cannot be converted to a NumPy array: {exc}") from exc

    if raw_values.ndim != 1:
        raise FilterError(
            f"signal must be one-dimensional, got {raw_values.ndim} dimensions"
        )
    if raw_values.dtype.kind not in {"i", "u", "f", "O"}:
        raise FilterError("signal must contain real numeric values")

    try:
        values = np.ascontiguousarray(raw_values, dtype=np.float64)
    except Exception as exc:
        raise FilterError("signal must contain only real numeric values") from exc

    if values.size and not np.isfinite(values).all():
        raise FilterError("signal must not contain NaN or infinite values")
    return values
