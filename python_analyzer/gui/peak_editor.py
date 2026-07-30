"""Small dialog for manual peak add/edit operations."""

from __future__ import annotations

import math
from typing import Any

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
)


class PeakEditDialog(QDialog):
    """Collect finite peak values without touching the analysis pipeline."""

    def __init__(self, parent=None, *, peak: Any | None = None, title: str = "Peak"):
        super().__init__(parent)
        self.setWindowTitle(title)

        layout = QFormLayout(self)
        self.frequency_spin = self._spin_box(0.0, 10_000_000.0, " Hz")
        self.position_spin = self._spin_box(0.0, 10_000_000.0, "")
        self.intensity_spin = self._spin_box(-1_000_000_000.0, 1_000_000_000.0, "")
        self.width_spin = self._spin_box(0.0, 1_000_000.0, "")
        self.width_hz_spin = self._spin_box(0.0, 1_000_000.0, " Hz")
        self.area_spin = self._spin_box(0.0, 1_000_000_000.0, "")
        self.snr_spin = self._spin_box(0.0, 1_000_000.0, "")

        self._load_peak(peak)

        layout.addRow("Frequency", self.frequency_spin)
        layout.addRow("Bin position", self.position_spin)
        layout.addRow("Intensity", self.intensity_spin)
        layout.addRow("Width (bins)", self.width_spin)
        layout.addRow("Width (Hz)", self.width_hz_spin)
        layout.addRow("Area", self.area_spin)
        layout.addRow("SNR", self.snr_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict[str, float]:
        """Return peak values selected by the user."""

        return {
            "frequency": self.frequency_spin.value(),
            "position": self.position_spin.value(),
            "intensity": self.intensity_spin.value(),
            "width": self.width_spin.value(),
            "width_hz": self.width_hz_spin.value(),
            "area": self.area_spin.value(),
            "snr": self.snr_spin.value(),
        }

    def _spin_box(self, minimum: float, maximum: float, suffix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(6)
        spin.setSingleStep(1.0)
        spin.setSuffix(suffix)
        return spin

    def _load_peak(self, peak: Any | None) -> None:
        if peak is None:
            return

        self.frequency_spin.setValue(self._peak_value(peak, "frequency", "position"))
        self.position_spin.setValue(self._peak_value(peak, "position", "frequency"))
        self.intensity_spin.setValue(self._peak_value(peak, "intensity"))
        self.width_spin.setValue(self._peak_value(peak, "width"))
        self.width_hz_spin.setValue(self._peak_value(peak, "width_hz"))
        self.area_spin.setValue(self._peak_value(peak, "area"))
        self.snr_spin.setValue(self._peak_value(peak, "snr"))

    def _peak_value(
        self,
        peak: Any,
        primary_name: str,
        fallback_name: str | None = None,
    ) -> float:
        value = getattr(peak, primary_name, None)
        if value is None and fallback_name is not None:
            value = getattr(peak, fallback_name, None)
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return 0.0
        return numeric_value if math.isfinite(numeric_value) else 0.0
