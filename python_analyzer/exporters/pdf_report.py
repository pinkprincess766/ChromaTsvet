"""PDF report export for analysis results.

The exporter is intentionally UI-free: Qt owns dialogs and screenshots, while
this module owns only ReportLab drawing.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Optional, Sequence, Union

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


PathLike = Union[str, Path]


@dataclass
class PDFReportData:
    """Prepared snapshot used to render a ChromaTsvet PDF report."""

    title: str
    subtitle: str
    summary_rows: list[tuple[str, str]]
    parameter_rows: list[tuple[str, str]]
    peaks: Sequence[Any]
    matches: list[tuple[str, str, str, str]]
    source_file_name: str
    data_points_count: int
    peaks_count: int


class PDFReportExporter:
    """Generate a PDF report from already prepared analysis data."""

    page_size = A4
    margin = 50

    def export(
        self,
        output_path: PathLike,
        report_data: PDFReportData,
        plot_image_path: Optional[PathLike] = None,
        logo_path: Optional[PathLike] = None,
    ) -> None:
        output_path = Path(output_path)
        pdf = canvas.Canvas(str(output_path), pagesize=self.page_size)
        width, height = self.page_size
        y = height - 55

        self._draw_logo(pdf, width, height, logo_path)
        y = self._draw_title(pdf, y, report_data)
        y = self._draw_section_title(pdf, y, "Summary")
        y = self._draw_key_value_rows(pdf, y, report_data.summary_rows)
        y -= 14

        y = self._draw_section_title(pdf, y, "Analysis Parameters")
        y = self._draw_key_value_rows(pdf, y, report_data.parameter_rows)
        y -= 12

        y = self._ensure_space(pdf, y, 340)
        y = self._draw_spectrum_section(pdf, y, plot_image_path)
        y = self._draw_peaks_section(pdf, y, report_data.peaks)
        y = self._draw_matches_section(pdf, y, report_data.matches)

        pdf.save()

    def _draw_logo(
        self,
        pdf: canvas.Canvas,
        width: float,
        height: float,
        logo_path: Optional[PathLike],
    ) -> None:
        if logo_path is None:
            return

        path = Path(logo_path)
        if not path.is_file():
            return

        pdf.drawImage(
            str(path),
            width - self.margin - 78,
            height - 72,
            width=78,
            height=58,
            preserveAspectRatio=True,
            mask="auto",
        )

    def _draw_title(
        self,
        pdf: canvas.Canvas,
        y: float,
        report_data: PDFReportData,
    ) -> float:
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(self.margin, y, report_data.title)
        y -= 22

        pdf.setFont("Helvetica", 9)
        pdf.setFillColorRGB(0.35, 0.38, 0.43)
        pdf.drawString(self.margin, y, report_data.subtitle)
        pdf.setFillColorRGB(0, 0, 0)
        return y - 30

    def _draw_section_title(self, pdf: canvas.Canvas, y: float, title: str) -> float:
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(self.margin, y, title)
        return y - 18

    def _draw_key_value_rows(
        self,
        pdf: canvas.Canvas,
        y: float,
        rows: Sequence[tuple[str, str]],
    ) -> float:
        pdf.setFont("Helvetica", 10)
        for label, value in rows:
            pdf.drawString(self.margin, y, f"{label}:")
            pdf.drawString(self.margin + 95, y, str(value)[:78])
            y -= 15
        return y

    def _draw_spectrum_section(
        self,
        pdf: canvas.Canvas,
        y: float,
        plot_image_path: Optional[PathLike],
    ) -> float:
        y = self._draw_section_title(pdf, y, "Spectrum")
        if plot_image_path is None:
            pdf.setFont("Helvetica", 9)
            pdf.drawString(self.margin, y, "Spectrum image is not available.")
            return y - 25

        path = Path(plot_image_path)
        if not path.is_file():
            pdf.setFont("Helvetica", 9)
            pdf.drawString(self.margin, y, "Spectrum image is not available.")
            return y - 25

        y -= 200
        width, _ = self.page_size
        pdf.drawImage(
            str(path),
            self.margin,
            y,
            width=width - self.margin * 2,
            height=200,
            preserveAspectRatio=True,
            anchor="c",
        )
        return y - 25

    def _draw_peaks_section(
        self,
        pdf: canvas.Canvas,
        y: float,
        peaks: Sequence[Any],
    ) -> float:
        y = self._draw_section_title(pdf, y, "Detected Peaks")
        y = self._draw_peak_header(pdf, y)
        pdf.setFont("Helvetica", 9)

        if not peaks:
            pdf.drawString(self.margin, y, "No peaks detected.")
            return y - 26

        for peak in peaks:
            if y < 90:
                y = self._new_page_with_peak_header(pdf)
            self._draw_peak_row(pdf, y, peak)
            y -= 14

        return y - 10

    def _draw_peak_header(self, pdf: canvas.Canvas, y: float) -> float:
        peak_columns = [
            ("Freq Hz", 0),
            ("Bin", 75),
            ("Intensity", 118),
            ("Width bin", 178),
            ("Width Hz", 245),
            ("Area", 312),
            ("SNR", 390),
        ]

        pdf.setFont("Helvetica-Bold", 9)
        for label, offset in peak_columns:
            pdf.drawString(self.margin + offset, y, label)
        y -= 13

        width, _ = self.page_size
        pdf.line(self.margin, y, width - self.margin, y)
        return y - 12

    def _draw_peak_row(self, pdf: canvas.Canvas, y: float, peak: Any) -> None:
        pdf.drawString(self.margin, y, self._format_peak_value(self._peak_frequency(peak)))
        pdf.drawString(self.margin + 75, y, self._format_peak_value(getattr(peak, "position", None)))
        pdf.drawString(self.margin + 118, y, self._format_peak_value(getattr(peak, "intensity", None)))
        pdf.drawString(self.margin + 178, y, self._format_peak_value(getattr(peak, "width", None)))
        pdf.drawString(self.margin + 245, y, self._format_peak_value(getattr(peak, "width_hz", None)))
        pdf.drawString(self.margin + 312, y, self._format_peak_value(getattr(peak, "area", None)))
        pdf.drawString(self.margin + 390, y, self._format_peak_value(getattr(peak, "snr", None)))

    def _draw_matches_section(
        self,
        pdf: canvas.Canvas,
        y: float,
        matches: Sequence[tuple[str, str, str, str]],
    ) -> float:
        y = self._ensure_space(pdf, y, 150)
        y = self._draw_section_title(pdf, y, "Identification Results")
        y = self._draw_match_header(pdf, y)

        pdf.setFont("Helvetica", 9)
        for name, formula, score, compared_points in matches:
            if y < 80:
                y = self._new_page(pdf)
                pdf.setFont("Helvetica", 9)
            pdf.drawString(self.margin, y, str(name)[:28])
            pdf.drawString(self.margin + 170, y, str(formula)[:14])
            pdf.drawString(self.margin + 270, y, str(score))
            pdf.drawString(self.margin + 340, y, str(compared_points))
            y -= 14
        return y

    def _draw_match_header(self, pdf: canvas.Canvas, y: float) -> float:
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(self.margin, y, "Substance")
        pdf.drawString(self.margin + 170, y, "Formula")
        pdf.drawString(self.margin + 270, y, "Score")
        pdf.drawString(self.margin + 340, y, "Compared points")
        y -= 13

        width, _ = self.page_size
        pdf.line(self.margin, y, width - self.margin, y)
        return y - 12

    def _ensure_space(self, pdf: canvas.Canvas, y: float, minimum: float) -> float:
        if y < minimum:
            return self._new_page(pdf)
        return y

    def _new_page(self, pdf: canvas.Canvas) -> float:
        pdf.showPage()
        _, height = self.page_size
        return height - self.margin

    def _new_page_with_peak_header(self, pdf: canvas.Canvas) -> float:
        y = self._new_page(pdf)
        return self._draw_peak_header(pdf, y)

    def _format_peak_value(self, value: Any, precision: int = 6) -> str:
        if value is None:
            return ""
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return str(value)
        if not math.isfinite(numeric_value):
            return ""
        return f"{numeric_value:.{precision}g}"

    def _peak_frequency(self, peak: Any) -> Any:
        frequency = getattr(peak, "frequency", None)
        try:
            frequency = float(frequency)
        except (TypeError, ValueError):
            frequency = None

        if frequency is not None and math.isfinite(frequency):
            return frequency
        return getattr(peak, "position", None)
