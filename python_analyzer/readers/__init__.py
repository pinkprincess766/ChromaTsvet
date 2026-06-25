"""Readers package.

Provides clean access to spectrum file readers.
"""

from __future__ import annotations

from .spectrum_reader import (
    SpectrumFileFormatError,
    read_spectrum_file,
)

__all__ = [
    "SpectrumFileFormatError",
    "read_spectrum_file",
]
