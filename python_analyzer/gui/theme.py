"""Application-wide Qt theme helpers."""

from __future__ import annotations

from PyQt5.QtGui import QColor, QFont, QPalette


FONT_CANDIDATES = [
    "Inter",
    "Roboto",
    "IBM Plex Sans",
    ".AppleSystemUIFont",
    "Segoe UI",
]


def apply_app_theme(app, theme: str, font_family: str, font_size: int) -> None:
    """Apply the ChromaTsvet light or dark Qt theme."""
    app.setStyle("Fusion")
    app.setFont(QFont(font_family, font_size))

    is_dark = theme == "dark"
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#181A20" if is_dark else "#F4F6FA"))
    palette.setColor(QPalette.WindowText, QColor("#E8EAED" if is_dark else "#1F232B"))
    palette.setColor(QPalette.Base, QColor("#111318" if is_dark else "#FFFFFF"))
    palette.setColor(QPalette.AlternateBase, QColor("#1F232B" if is_dark else "#EEF2F7"))
    palette.setColor(QPalette.ToolTipBase, QColor("#242934" if is_dark else "#FFFFFF"))
    palette.setColor(QPalette.ToolTipText, QColor("#F4F6FA" if is_dark else "#1F232B"))
    palette.setColor(QPalette.Text, QColor("#E8EAED" if is_dark else "#1F232B"))
    palette.setColor(QPalette.Button, QColor("#242934" if is_dark else "#FFFFFF"))
    palette.setColor(QPalette.ButtonText, QColor("#F4F6FA" if is_dark else "#1F232B"))
    palette.setColor(QPalette.BrightText, QColor("#FF6B6B"))
    palette.setColor(QPalette.Highlight, QColor("#4DA3FF"))
    palette.setColor(QPalette.HighlightedText, QColor("#0B0D12" if is_dark else "#FFFFFF"))
    app.setPalette(palette)

    colors = {
        "window": "#181A20" if is_dark else "#F4F6FA",
        "panel": "#111318" if is_dark else "#FFFFFF",
        "panel_alt": "#181C23" if is_dark else "#F8FAFD",
        "button": "#2B313C" if is_dark else "#FFFFFF",
        "button_hover": "#343B49" if is_dark else "#EEF5FF",
        "button_pressed": "#202630" if is_dark else "#DDEBFF",
        "border": "#2A303A" if is_dark else "#D8DEE8",
        "border_hover": "#4DA3FF",
        "text": "#E8EAED" if is_dark else "#1F232B",
        "muted": "#B8C0CC" if is_dark else "#5A6472",
        "header": "#20242C" if is_dark else "#EEF2F7",
        "terminal_bg": "#0F1217" if is_dark else "#FFFFFF",
        "terminal_text": "#87E3B2" if is_dark else "#236A45",
        "selection": "#2F6FAF" if is_dark else "#4DA3FF",
        "selection_text": "#FFFFFF",
    }

    qss = f"""
        QWidget {{
            font-family: "{font_family}", "Inter", "Roboto", "IBM Plex Sans", ".AppleSystemUIFont", "Segoe UI", sans-serif;
            font-size: {font_size}pt;
            color: {colors["text"]};
        }}
        QMainWindow, QDialog {{
            background-color: {colors["window"]};
        }}
        QPushButton {{
            background-color: {colors["button"]};
            border: 1px solid {colors["border"]};
            border-radius: 6px;
            padding: 6px 10px;
            min-height: 24px;
        }}
        QPushButton:hover {{
            background-color: {colors["button_hover"]};
            border-color: {colors["border_hover"]};
        }}
        QPushButton:pressed {{
            background-color: {colors["button_pressed"]};
        }}
        QComboBox, QSpinBox, QDoubleSpinBox {{
            background-color: {colors["panel"]};
            border: 1px solid {colors["border"]};
            border-radius: 6px;
            padding: 5px 8px;
        }}
        QGroupBox {{
            border: 1px solid {colors["border"]};
            border-radius: 7px;
            margin-top: 10px;
            padding: 12px 10px 10px 10px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
            color: {colors["text"]};
        }}
        QTabWidget::pane {{
            border: 1px solid {colors["border"]};
            border-radius: 7px;
            top: -1px;
        }}
        QTabBar::tab {{
            background-color: {colors["panel_alt"]};
            border: 1px solid {colors["border"]};
            border-bottom: 0;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            padding: 6px 12px;
            margin-right: 2px;
            color: {colors["muted"]};
            font-weight: 600;
        }}
        QTabBar::tab:selected {{
            background-color: {colors["panel"]};
            color: {colors["text"]};
        }}
        QTableWidget {{
            background-color: {colors["panel"]};
            alternate-background-color: {colors["panel_alt"]};
            border: 1px solid {colors["border"]};
            gridline-color: {colors["border"]};
            selection-background-color: {colors["selection"]};
            selection-color: {colors["selection_text"]};
        }}
        QHeaderView::section {{
            background-color: {colors["header"]};
            color: {colors["text"]};
            border: 0;
            border-right: 1px solid {colors["border"]};
            border-bottom: 1px solid {colors["border"]};
            padding: 5px 8px;
            font-weight: 600;
        }}
        QTextEdit {{
            background-color: {colors["terminal_bg"]};
            border: 1px solid {colors["border"]};
            border-radius: 6px;
            padding: 7px;
            color: {colors["terminal_text"]};
        }}
        QWidget#embeddedLogPanel {{
            background-color: {colors["panel_alt"]};
            border: 1px solid {colors["border"]};
            border-radius: 7px;
        }}
        QWidget#embeddedLogPanel QPushButton {{
            min-height: 20px;
            padding: 3px 9px;
        }}
        QWidget#embeddedLogPanel QTextEdit {{
            background-color: {colors["terminal_bg"]};
        }}
        QStatusBar {{
            background-color: {colors["panel"]};
            border-top: 1px solid {colors["border"]};
            color: {colors["muted"]};
        }}
        QStatusBar::item {{
            border: 0;
        }}
        QLabel {{
            color: {colors["muted"]};
        }}
        QLabel#fileLabel {{
            background-color: {colors["panel"]};
            border: 1px solid {colors["border"]};
            border-radius: 6px;
            padding: 6px 10px;
            color: {colors["text"]};
            font-weight: 600;
        }}
        QLabel#statusSourceLabel {{
            color: {colors["text"]};
            padding: 0 6px;
        }}
        QLabel#appLogo {{
            background-color: transparent;
            padding-left: 4px;
        }}
    """
    app.setStyleSheet(qss)
