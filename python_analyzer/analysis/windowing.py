"""FFT window configuration shared by UI and analysis settings."""

from __future__ import annotations


FFT_WINDOW_CHOICES = (
    ("Hann", "hann"),
    ("Hamming", "hamming"),
    ("Rectangular", "rectangular"),
)

SUPPORTED_FFT_WINDOWS = {value for _, value in FFT_WINDOW_CHOICES}
DEFAULT_FFT_WINDOW = "hann"


def normalize_fft_window_type(window_type: object) -> str:
    """Return a supported FFT window type, preserving the historical default."""
    normalized = str(window_type or "").strip().lower()
    return normalized if normalized in SUPPORTED_FFT_WINDOWS else DEFAULT_FFT_WINDOW


def fft_window_label(window_type: object) -> str:
    """Return a display label for a normalized FFT window type."""
    normalized = normalize_fft_window_type(window_type)
    for label, value in FFT_WINDOW_CHOICES:
        if value == normalized:
            return label
    return "Hann"
