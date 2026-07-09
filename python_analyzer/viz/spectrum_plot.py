"""Visualization helpers for the spectrum plot.

Extracted from the monolithic MainWindow for better separation.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtGui import QFont


class SpectrumPlot:
    """Manages the pyqtgraph plot widget for spectrum visualization."""

    def __init__(self, plot_widget: pg.PlotWidget) -> None:
        self.plot = plot_widget
        self.theme = "dark"
        self.font_family = "Inter"
        self.font_size = 12
        self.legend = None

    def configure(self, theme: str, font_family: str, font_size: int) -> None:
        self.theme = theme
        self.font_family = font_family
        self.font_size = font_size
        self._apply_configuration()

    def _apply_configuration(self) -> None:
        colors = self.colors()
        self.plot.setBackground(colors["background"])
        self.set_title("Spectrum")
        self.plot.setLabel("bottom", "Frequency (Hz)", color=colors["muted"], size="10pt")
        self.plot.setLabel("left", "Intensity", color=colors["muted"], size="10pt")
        self.plot.showGrid(x=True, y=True, alpha=0.28 if self.theme == "dark" else 0.22)

        plot_item = self.plot.getPlotItem()
        plot_item.getViewBox().setBackgroundColor(colors["background"])
        plot_item.getViewBox().setBorder(pg.mkPen(colors["border"], width=1))
        plot_item.getViewBox().setMouseEnabled(x=True, y=True)
        plot_item.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.setToolTip(
            "Mouse wheel zooms the spectrum; drag to zoom into a selected area."
        )

        for axis_name in ("bottom", "left"):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen(colors["axis"], width=1))
            axis.setTextPen(pg.mkPen(colors["ticks"]))
            axis.setStyle(tickFont=QFont(self.font_family, max(8, self.font_size - 3)))

    def set_title(self, title: str) -> None:
        colors = self.colors()
        self.plot.setTitle(title, color=colors["text"], size="15pt")

    def colors(self) -> dict:
        if self.theme == "light":
            return {
                "background": "#FFFFFF",
                "border": "#D8DEE8",
                "axis": "#8A94A3",
                "ticks": "#3A4350",
                "muted": "#5A6472",
                "text": "#1F232B",
                "spectrum": "#0A84FF",
                "overlay": "#B26400",
                "peak": "#D43F3A",
                "peak_border": "#8E1F1C",
            }
        return {
            "background": "#111318",
            "border": "#2A303A",
            "axis": "#6E7786",
            "ticks": "#AEB8C5",
            "muted": "#B8C0CC",
            "text": "#E8EAED",
            "spectrum": "#4DA3FF",
            "overlay": "#FFD166",
            "peak": "#FF6B6B",
            "peak_border": "#C0392B",
        }

    def plot_spectrum(
        self,
        frequency_axis: np.ndarray,
        spectrum: np.ndarray,
        *,
        name: str | None = None,
        color_key: str = "spectrum",
        width: float = 2.6,
    ) -> None:
        colors = self.colors()
        color = colors.get(color_key, colors["spectrum"])
        if name:
            self._ensure_legend()
        self.plot.plot(
            frequency_axis,
            spectrum,
            pen=pg.mkPen(color, width=width),
            name=name,
        )

    def plot_overlay_spectrum(
        self,
        frequency_axis: np.ndarray,
        spectrum: np.ndarray,
        label: str,
    ) -> None:
        self.plot_spectrum(
            frequency_axis,
            spectrum,
            name=label,
            color_key="overlay",
            width=2.0,
        )

    def add_peak_markers(self, peaks: list) -> None:
        visible_peaks = []
        colors = self.colors()
        for peak in peaks:
            position = self._peak_frequency(peak)
            intensity = getattr(peak, "intensity", None)
            try:
                position = float(position)
                intensity = float(intensity)
            except (TypeError, ValueError):
                continue
            if np.isfinite(position) and np.isfinite(intensity):
                visible_peaks.append((position, intensity))

        if not visible_peaks:
            return

        positions, intensities = zip(*visible_peaks)
        self.plot.plot(
            positions,
            intensities,
            pen=None,
            symbol="o",
            symbolSize=12,
            symbolBrush=pg.mkBrush(colors["peak"]),
            symbolPen=pg.mkPen(colors["peak_border"], width=1.6),
        )

        for position, intensity in sorted(visible_peaks, key=lambda p: p[1], reverse=True)[:12]:
            label = pg.TextItem(
                self.format_value(position, precision=5),
                color=colors["peak_border"],
                anchor=(0.5, 1.4),
            )
            label.setPos(position, intensity)
            self.plot.addItem(label)

    def clear(self) -> None:
        self.plot.clear()
        if self.legend is not None:
            self.legend.clear()

    def _ensure_legend(self) -> None:
        if self.legend is None:
            self.legend = self.plot.addLegend(offset=(12, 12))

    def _peak_frequency(self, peak) -> float | None:
        frequency = getattr(peak, "frequency", None)
        try:
            frequency = float(frequency)
        except (TypeError, ValueError):
            frequency = None

        if frequency is not None and np.isfinite(frequency):
            return frequency
        return getattr(peak, "position", None)

    def format_value(self, value, precision: int = 6) -> str:
        if value is None:
            return ""
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return str(value)
        if not np.isfinite(numeric_value):
            return ""
        return f"{numeric_value:.{precision}g}"

    def frequency_axis(
        self,
        result: dict,
        spectrum_len: int,
        *,
        sample_rate=None,
        source_signal_len=None,
    ) -> np.ndarray:
        try:
            frequency_axis = np.asarray(result.get("frequency_axis", []), dtype=float)
        except (TypeError, ValueError):
            frequency_axis = np.asarray([], dtype=float)

        if (
            len(frequency_axis) != spectrum_len
            or not np.all(np.isfinite(frequency_axis))
        ):
            fallback_sample_rate = result.get("sample_rate", sample_rate)
            if fallback_sample_rate is None:
                fallback_sample_rate = sample_rate
            return self._fallback_frequency_axis(
                spectrum_len,
                fallback_sample_rate,
                source_signal_len,
            )
        return frequency_axis

    def _fallback_frequency_axis(
        self,
        spectrum_len: int,
        sample_rate,
        source_signal_len,
    ) -> np.ndarray:
        if spectrum_len == 0:
            return np.asarray([], dtype=float)

        try:
            sample_rate = float(sample_rate)
            source_signal_len = int(source_signal_len)
        except (TypeError, ValueError):
            raise ValueError(
                "Frequency axis is missing or invalid and cannot be rebuilt "
                "without sample_rate and source_signal_len."
            )

        if (
            not np.isfinite(sample_rate)
            or sample_rate <= 0.0
            or source_signal_len <= 0
            or spectrum_len > source_signal_len
        ):
            raise ValueError(
                "Frequency axis is missing or invalid and fallback metadata is invalid."
            )

        bin_width = sample_rate / source_signal_len
        return np.arange(spectrum_len, dtype=float) * bin_width
