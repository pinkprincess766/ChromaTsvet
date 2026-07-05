"""Shared pytest fixtures for ChromaTsvet tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication


@pytest.fixture
def sample_spectrum_data() -> np.ndarray:
    """Small finite spectrum with one obvious local maximum."""
    return np.asarray([0.1, 0.3, 0.8, 0.2], dtype=float)


@pytest.fixture
def temp_spectrum_file(tmp_path: Path) -> Callable[..., Path]:
    """Create a temporary spectrum CSV/TXT file for reader tests."""

    def write_file(
        content: str | bytes = "intensity\n0.1\n0.3\n0.8\n0.2\n",
        *,
        name: str = "sample.csv",
        encoding: str = "utf-8",
    ) -> Path:
        path = tmp_path / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding=encoding)
        return path

    return write_file


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return a QApplication for GUI tests without starting the event loop."""
    return QApplication.instance() or QApplication([])
