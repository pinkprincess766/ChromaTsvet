"""HTML report export for analysis results."""

from __future__ import annotations

import base64
import errno
import math
from html import escape
from pathlib import Path
from typing import Any, Optional, Union

from .pdf_report import PDFReportData


PathLike = Union[str, Path]


class HTMLReportExporter:
    """Generate a self-contained HTML report from prepared analysis data."""

    def export(
        self,
        output_path: PathLike,
        report_data: PDFReportData,
        plot_image_path: Optional[PathLike] = None,
    ) -> None:
        """Write a UTF-8 HTML report to ``output_path``."""
        output_path = Path(output_path)
        plot_image_path = self._optional_existing_path(plot_image_path, "Plot image")

        output_path.write_text(
            self._render_document(report_data, plot_image_path),
            encoding="utf-8",
        )

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

    def _render_document(
        self,
        report_data: PDFReportData,
        plot_image_path: Optional[Path],
    ) -> str:
        plot_html = self._render_plot(plot_image_path)
        summary_rows = self._render_key_value_rows(report_data.summary_rows)
        parameter_rows = self._render_key_value_rows(report_data.parameter_rows)
        passport_rows = self._render_key_value_rows(
            report_data.processing_passport_rows
        )
        peak_rows = self._render_peak_rows(report_data.peaks)
        match_rows = self._render_match_rows(report_data.matches)
        passport_section = (
            f"""
    <section>
      <h2>Processing Passport</h2>
      <table><tbody>{passport_rows}</tbody></table>
    </section>"""
            if report_data.processing_passport_rows
            else ""
        )

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(report_data.title)}</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f7f8;
      color: #1f2933;
    }}
    body {{
      margin: 0;
      padding: 32px;
    }}
    main {{
      max-width: 1040px;
      margin: 0 auto;
      background: #ffffff;
      border: 1px solid #d7dde5;
      border-radius: 8px;
      padding: 28px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 28px;
    }}
    .subtitle {{
      margin: 0 0 24px;
      color: #5d6878;
    }}
    section {{
      margin-top: 28px;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 18px;
      border-bottom: 1px solid #e0e5ec;
      padding-bottom: 6px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid #e6ebf1;
      padding: 8px 9px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #f0f3f6;
      font-weight: 650;
    }}
    .plot {{
      max-width: 100%;
      border: 1px solid #d7dde5;
      border-radius: 6px;
    }}
    .muted {{
      color: #697586;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(report_data.title)}</h1>
    <p class="subtitle">{escape(report_data.subtitle)}</p>
    <section>
      <h2>Summary</h2>
      <table><tbody>{summary_rows}</tbody></table>
    </section>
    <section>
      <h2>Analysis Parameters</h2>
      <table><tbody>{parameter_rows}</tbody></table>
    </section>
    {passport_section}
    <section>
      <h2>Spectrum</h2>
      {plot_html}
    </section>
    <section>
      <h2>Detected Peaks</h2>
      <table>
        <thead>
          <tr>
            <th>Freq Hz</th><th>Bin</th><th>Intensity</th><th>Width bin</th>
            <th>Width Hz</th><th>Area</th><th>SNR</th>
          </tr>
        </thead>
        <tbody>{peak_rows}</tbody>
      </table>
    </section>
    <section>
      <h2>Identification Results</h2>
      <table>
        <thead>
          <tr>
            <th>Candidate</th><th>Formula</th><th>Method</th><th>Score</th>
            <th>Matched</th><th>Sample coverage</th><th>Reference coverage</th>
            <th>Mean frequency error</th><th>Evidence</th>
          </tr>
        </thead>
        <tbody>{match_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""

    def _render_key_value_rows(self, rows: list[tuple[str, str]]) -> str:
        return "".join(
            f"<tr><th>{escape(str(label))}</th><td>{escape(str(value))}</td></tr>"
            for label, value in rows
        )

    def _render_plot(self, plot_image_path: Optional[Path]) -> str:
        if plot_image_path is None:
            return '<p class="muted">Spectrum image is not available.</p>'

        image_bytes = plot_image_path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f'<img class="plot" alt="Spectrum plot" src="data:image/png;base64,{encoded}">'

    def _render_peak_rows(self, peaks: Any) -> str:
        if not peaks:
            return '<tr><td colspan="7" class="muted">No peaks detected.</td></tr>'

        return "".join(
            "<tr>"
            f"<td>{escape(self._format_peak_value(self._peak_frequency(peak)))}</td>"
            f"<td>{escape(self._format_peak_value(getattr(peak, 'position', None)))}</td>"
            f"<td>{escape(self._format_peak_value(getattr(peak, 'intensity', None)))}</td>"
            f"<td>{escape(self._format_peak_value(getattr(peak, 'width', None)))}</td>"
            f"<td>{escape(self._format_peak_value(getattr(peak, 'width_hz', None)))}</td>"
            f"<td>{escape(self._format_peak_value(getattr(peak, 'area', None)))}</td>"
            f"<td>{escape(self._format_peak_value(getattr(peak, 'snr', None)))}</td>"
            "</tr>"
            for peak in peaks
        )

    def _render_match_rows(self, matches: Any) -> str:
        if not matches:
            return '<tr><td colspan="9" class="muted">No matches found.</td></tr>'

        return "".join(
            "<tr>"
            f"<td>{escape(str(match.substance_name))}</td>"
            f"<td>{escape(str(match.formula))}</td>"
            f"<td>{escape(str(match.method))}</td>"
            f"<td>{escape(str(match.score))}</td>"
            f"<td>{escape(str(match.compared_points))}</td>"
            f"<td>{escape(str(match.sample_coverage))}</td>"
            f"<td>{escape(str(match.reference_coverage))}</td>"
            f"<td>{escape(str(match.mean_frequency_error))}</td>"
            f"<td>{escape(str(match.evidence_level))}</td>"
            "</tr>"
            for match in matches
        )

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
            numeric_frequency = float(frequency)
        except (TypeError, ValueError):
            numeric_frequency = None

        if numeric_frequency is not None and math.isfinite(numeric_frequency):
            return numeric_frequency
        return getattr(peak, "position", None)
