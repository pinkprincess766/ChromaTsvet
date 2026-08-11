#!/usr/bin/env python3
"""Capture a compact README workflow GIF from the real Qt application."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, ImageFont
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = PROJECT_ROOT / "docs" / "demo"
DEMO_GIF_PATH = DEMO_DIR / "chromatsvet-workflow.gif"
SAMPLE_PATH = PROJECT_ROOT / "examples" / "alpha" / "clean_three_peaks.csv"
REPORT_PATH = PROJECT_ROOT / "output" / "demo" / "chromatsvet-readme-demo.pdf"

sys.path.insert(0, str(PROJECT_ROOT))

from python_analyzer import main  # noqa: E402
from python_analyzer.analysis.models import LoadedSpectrum  # noqa: E402
from python_analyzer.readers.spectrum_reader import read_spectrum_file  # noqa: E402


FRAME_SIZE = (1120, 720)
CAPTION_PADDING = 18
FRAME_DURATION_MS = 1350


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


TITLE_FONT = _font(28, bold=True)
BODY_FONT = _font(18)


def _load_sample_without_running_analysis(window: main.MainWindow) -> None:
    data, _ = read_spectrum_file(SAMPLE_PATH)
    sample_display_path = str(Path("examples") / "alpha" / SAMPLE_PATH.name)
    window.current_data = data
    window.current_file_name = SAMPLE_PATH.name
    window.current_file_path = sample_display_path
    window.current_data_points_count = len(data)
    window.current_result = None
    window.current_peaks = []
    window.current_peak_reviews = []
    window.current_matches = []
    window.current_frequency_axis = None
    window.current_spectrum_values = None
    window._reset_overlay_state()
    window.analysis_status = "loaded"
    window.current_spectrum = LoadedSpectrum(
        data=data,
        file_path=sample_display_path,
        file_name=SAMPLE_PATH.name,
    )
    window._update_file_display()
    window._update_status_summary()
    window._update_export_actions()
    window.log(
        f"Loaded file: {SAMPLE_PATH.name} ({len(data)} points)",
        status_message=f"Loaded: {SAMPLE_PATH.name}",
    )


def _capture_frame(window: main.MainWindow, title: str, body: str) -> Image.Image:
    QApplication.processEvents()
    pixmap = window.grab()
    if pixmap.isNull():
        raise RuntimeError("Could not capture ChromaTsvet window")

    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        if not pixmap.save(tmp.name, "PNG"):
            raise RuntimeError("Could not save temporary screenshot")
        screenshot = Image.open(tmp.name).convert("RGB")

    screenshot.thumbnail(
        (FRAME_SIZE[0] - 32, FRAME_SIZE[1] - 32),
        Image.Resampling.LANCZOS,
    )
    frame = Image.new("RGB", FRAME_SIZE, "#eef2f5")
    left = (FRAME_SIZE[0] - screenshot.width) // 2
    top = (FRAME_SIZE[1] - screenshot.height) // 2
    frame.paste(screenshot, (left, top))

    overlay = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    caption_box = (
        CAPTION_PADDING,
        CAPTION_PADDING,
        FRAME_SIZE[0] - CAPTION_PADDING,
        132,
    )
    draw.rounded_rectangle(caption_box, radius=14, fill=(31, 41, 51, 224))
    draw.text((38, 34), title, font=TITLE_FONT, fill="#ffffff")
    draw.text((38, 76), body, font=BODY_FONT, fill="#dbe7f3")

    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert(
        "P",
        palette=Image.ADAPTIVE,
    )


def capture_demo_gif() -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    settings_dir = Path(tempfile.mkdtemp(prefix="chromatsvet-demo-settings-"))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(settings_dir))

    QApplication.setAttribute(Qt.AA_Use96Dpi, True)
    app = QApplication.instance() or QApplication(sys.argv[:1])

    window = main.MainWindow()
    window.theme = "light"
    window.font_size = 11
    main.apply_app_theme(app, window.theme, window.font_family, window.font_size)
    window.resize(1420, 820)
    window.show()

    frames: list[Image.Image] = [
        _capture_frame(
            window,
            "1. Open a sample file",
            "Start from a safe synthetic CSV in examples/alpha/.",
        )
    ]

    window.sample_rate = 1000.0
    window.baseline_enabled = True
    window.baseline_method = "improved"
    window.filter_type = "none"
    window.filter_params = {}
    window.peak_threshold = 0.02
    window.peak_prominence = 0.02
    window.peak_distance = 8
    _load_sample_without_running_analysis(window)
    frames.append(
        _capture_frame(
            window,
            "2. Run analysis",
            "The status bar shows the loaded file and point count before processing.",
        )
    )

    with (
        patch.object(main.QMessageBox, "warning", return_value=main.QMessageBox.Ok),
        patch.object(main.QMessageBox, "critical", return_value=main.QMessageBox.Ok),
    ):
        window.run_analysis()
    if not window.current_result:
        raise RuntimeError("Demo analysis did not produce results")
    window.results_tabs.setCurrentIndex(0)
    frames.append(
        _capture_frame(
            window,
            "3. Review detected peaks",
            "Peaks are marked on the graph and listed in the analysis table.",
        )
    )

    with (
        patch.object(
            main.QFileDialog,
            "getSaveFileName",
            return_value=(str(REPORT_PATH), "PDF (*.pdf)"),
        ),
        patch.object(main.QMessageBox, "warning", return_value=main.QMessageBox.Ok),
        patch.object(main.QMessageBox, "critical", return_value=main.QMessageBox.Ok),
        patch.object(main.QMessageBox, "information", return_value=main.QMessageBox.Ok),
    ):
        window.export_pdf()
    frames.append(
        _capture_frame(
            window,
            "4. Export the report",
            "PDF, HTML, Excel, graph images, and peak CSV exports are available.",
        )
    )

    frames[0].save(
        DEMO_GIF_PATH,
        save_all=True,
        append_images=frames[1:],
        duration=[FRAME_DURATION_MS] * len(frames),
        loop=0,
        optimize=True,
    )
    window.close()
    app.processEvents()
    print(f"Saved {DEMO_GIF_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    capture_demo_gif()
