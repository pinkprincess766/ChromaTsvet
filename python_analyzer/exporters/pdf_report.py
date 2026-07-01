"""PDF report export for analysis results.

The exporter is intentionally UI-free: Qt owns dialogs and screenshots, while
this module owns only ReportLab drawing.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import math
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, Sequence, Union

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


PathLike = Union[str, Path]


class PeakLike(Protocol):
    """Structural peak shape consumed by the PDF renderer."""

    position: Any
    intensity: Any
    width: Any
    width_hz: Any
    area: Any
    snr: Any


@dataclass(frozen=True)
class PDFMatchRow:
    """One prepared identification row for the PDF report."""

    substance_name: str
    formula: str
    score: str
    compared_points: str


@dataclass(frozen=True)
class ColumnSpec:
    """Fixed-width ReportLab column description."""

    label: str
    offset: int
    value_name: str
    max_chars: Optional[int] = None


@dataclass
class PDFReportData:
    """Prepared snapshot used to render a ChromaTsvet PDF report."""

    title: str
    subtitle: str
    summary_rows: list[tuple[str, str]]
    parameter_rows: list[tuple[str, str]]
    peaks: Sequence[PeakLike]
    matches: Sequence[PDFMatchRow]
    source_file_name: str
    data_points_count: int
    peaks_count: int


class PDFReportExporter:
    """Generate a PDF report from already prepared analysis data."""

    page_size = A4
    margin = 50
    peak_columns = (
        ColumnSpec("Freq Hz", 0, "frequency"),
        ColumnSpec("Bin", 75, "position"),
        ColumnSpec("Intensity", 118, "intensity"),
        ColumnSpec("Width bin", 178, "width"),
        ColumnSpec("Width Hz", 245, "width_hz"),
        ColumnSpec("Area", 312, "area"),
        ColumnSpec("SNR", 390, "snr"),
    )
    match_columns = (
        ColumnSpec("Substance", 0, "substance_name", 28),
        ColumnSpec("Formula", 170, "formula", 14),
        ColumnSpec("Score", 270, "score"),
        ColumnSpec("Compared points", 340, "compared_points"),
    )

    def export(
        self,
        output_path: PathLike,
        report_data: PDFReportData,
        plot_image_path: Optional[PathLike] = None,
        logo_path: Optional[PathLike] = None,
    ) -> None:
        """Write a PDF report to ``output_path``.

        ``plot_image_path`` may be omitted, but if a path is provided it must
        exist. This keeps report-generation failures visible to the UI layer
        instead of silently producing a report with a missing spectrum image.
        """
        output_path = Path(output_path)
        plot_image_path = self._optional_existing_path(plot_image_path, "Plot image")
        logo_path = self._optional_existing_path(logo_path, "Logo image")

        pdf = canvas.Canvas(str(output_path), pagesize=self.page_size)
        y = self._start_report(pdf, report_data, logo_path)
        y = self._draw_summary_section(pdf, y, report_data)
        y = self._draw_parameters_section(pdf, y, report_data)
        y = self._ensure_space(pdf, y, 340)
        y = self._draw_spectrum_section(pdf, y, plot_image_path)
        y = self._draw_peaks_section(pdf, y, report_data.peaks)
        y = self._draw_matches_section(pdf, y, report_data.matches)

        pdf.save()

    def _optional_existing_path(
        self,
        path: Optional[PathLike],
        label: str,
    ) -> Optional[Path]:
        if path is None:
            return None

        resolved = Path(path)
        if not resolved.is_file():
            safe_name = resolved.name or "selected file"
            raise FileNotFoundError(errno.ENOENT, f"{label} not found", safe_name)
        return resolved

    def _start_report(
        self,
        pdf: canvas.Canvas,
        report_data: PDFReportData,
        logo_path: Optional[Path],
    ) -> float:
        width, height = self.page_size
        self._draw_logo(pdf, width, height, logo_path)
        return self._draw_title(pdf, height - 55, report_data)

    def _draw_summary_section(
        self,
        pdf: canvas.Canvas,
        y: float,
        report_data: PDFReportData,
    ) -> float:
        y = self._draw_section_title(pdf, y, "Summary")
        y = self._draw_key_value_rows(pdf, y, report_data.summary_rows)
        return y - 14

    def _draw_parameters_section(
        self,
        pdf: canvas.Canvas,
        y: float,
        report_data: PDFReportData,
    ) -> float:
        y = self._draw_section_title(pdf, y, "Analysis Parameters")
        y = self._draw_key_value_rows(pdf, y, report_data.parameter_rows)
        return y - 12

    def _draw_logo(
        self,
        pdf: canvas.Canvas,
        width: float,
        height: float,
        logo_path: Optional[Path],
    ) -> None:
        if logo_path is None:
            return

        pdf.drawImage(
            str(logo_path),
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
        plot_image_path: Optional[Path],
    ) -> float:
        y = self._draw_section_title(pdf, y, "Spectrum")
        if plot_image_path is None:
            pdf.setFont("Helvetica", 9)
            pdf.drawString(self.margin, y, "Spectrum image is not available.")
            return y - 25

        y -= 200
        width, _ = self.page_size
        pdf.drawImage(
            str(plot_image_path),
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
        peaks: Sequence[PeakLike],
    ) -> float:
        y = self._draw_section_title(pdf, y, "Detected Peaks")
        y = self._draw_peak_header(pdf, y)
        pdf.setFont("Helvetica", 9)

        if not peaks:
            pdf.drawString(self.margin, y, "No peaks detected.")
            return y - 26

        for peak in peaks:
            y = self._ensure_row_space(pdf, y, 90, self._draw_peak_header)
            self._draw_peak_row(pdf, y, peak)
            y -= 14

        return y - 10

    def _draw_peak_header(self, pdf: canvas.Canvas, y: float) -> float:
        pdf.setFont("Helvetica-Bold", 9)
        for column in self.peak_columns:
            pdf.drawString(self.margin + column.offset, y, column.label)
        y -= 13

        width, _ = self.page_size
        pdf.line(self.margin, y, width - self.margin, y)
        return y - 12

    def _draw_peak_row(self, pdf: canvas.Canvas, y: float, peak: PeakLike) -> None:
        for column in self.peak_columns:
            pdf.drawString(
                self.margin + column.offset,
                y,
                self._format_peak_value(self._peak_column_value(peak, column)),
            )

    def _draw_matches_section(
        self,
        pdf: canvas.Canvas,
        y: float,
        matches: Sequence[PDFMatchRow],
    ) -> float:
        y = self._ensure_space(pdf, y, 150)
        y = self._draw_section_title(pdf, y, "Identification Results")
        y = self._draw_match_header(pdf, y)

        pdf.setFont("Helvetica", 9)
        for match in matches:
            y = self._ensure_row_space(pdf, y, 80)
            for column in self.match_columns:
                pdf.drawString(
                    self.margin + column.offset,
                    y,
                    self._truncate(getattr(match, column.value_name), column.max_chars),
                )
            y -= 14
        return y

    def _draw_match_header(self, pdf: canvas.Canvas, y: float) -> float:
        pdf.setFont("Helvetica-Bold", 9)
        for column in self.match_columns:
            pdf.drawString(self.margin + column.offset, y, column.label)
        y -= 13

        width, _ = self.page_size
        pdf.line(self.margin, y, width - self.margin, y)
        return y - 12

    def _ensure_space(self, pdf: canvas.Canvas, y: float, minimum: float) -> float:
        if y < minimum:
            return self._new_page(pdf)
        return y

    def _ensure_row_space(
        self,
        pdf: canvas.Canvas,
        y: float,
        threshold: float,
        header: Optional[Callable[[canvas.Canvas, float], float]] = None,
    ) -> float:
        if y >= threshold:
            return y

        y = self._new_page(pdf)
        if header is not None:
            y = header(pdf, y)
        pdf.setFont("Helvetica", 9)
        return y

    def _new_page(self, pdf: canvas.Canvas) -> float:
        pdf.showPage()
        _, height = self.page_size
        return height - self.margin

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

    def _truncate(self, value: Any, max_chars: Optional[int]) -> str:
        text = str(value)
        if max_chars is None:
            return text
        return text[:max_chars]

    def _peak_column_value(self, peak: PeakLike, column: ColumnSpec) -> Any:
        if column.value_name == "frequency":
            return self._peak_frequency(peak)
        return getattr(peak, column.value_name, None)

    def _peak_frequency(self, peak: Any) -> Any:
        frequency = getattr(peak, "frequency", None)
        try:
            frequency = float(frequency)
        except (TypeError, ValueError):
            frequency = None

        if frequency is not None and math.isfinite(frequency):
            return frequency
        return getattr(peak, "position", None)
