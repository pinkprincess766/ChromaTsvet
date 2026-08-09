from python_analyzer.analysis.peak_review import (
    PEAK_REVIEW_REJECTED,
    PEAK_REVIEW_SUSPICIOUS,
    PeakReview,
)
from python_analyzer.gui.diagnostics import (
    peak_review_messages,
    processing_warning_messages,
    sanitize_diagnostic_text,
    skipped_rows_message,
)


def test_sanitize_diagnostic_text_redacts_absolute_paths():
    message = sanitize_diagnostic_text(
        "Failed near /home/scientist/private/sample.csv and C:\\Data\\lab\\secret\\raw.txt"
    )

    assert "/home/scientist/private" not in message
    assert "C:\\Data\\lab\\secret" not in message
    assert ".../sample.csv" in message
    assert "...\\raw.txt" in message


def test_processing_warning_messages_are_human_readable_and_safe():
    messages = processing_warning_messages(
        {
            "processing_warnings": [
                "area_normalization_skipped",
                "/home/scientist/private/source.csv",
            ]
        }
    )

    assert messages[0] == (
        "Processing warning: area normalization was skipped because the integral "
        "was too small"
    )
    assert "Rust reported '.../source.csv'" in messages[1]
    assert "/home/scientist/private" not in messages[1]


def test_peak_review_messages_summarize_attention_reasons():
    messages = peak_review_messages(
        [
            PeakReview(PEAK_REVIEW_SUSPICIOUS, "low SNR", ("low SNR",)),
            PeakReview(
                PEAK_REVIEW_REJECTED,
                "missing finite peak position",
                ("invalid_position",),
            ),
        ]
    )

    assert len(messages) == 1
    assert "2 peaks require attention" in messages[0]
    assert "1 suspicious" in messages[0]
    assert "1 rejected" in messages[0]
    assert "low SNR" in messages[0]
    assert "invalid_position" in messages[0]


def test_skipped_rows_message_omits_cell_values():
    message = skipped_rows_message(
        "/home/scientist/private/messy.csv",
        valid_points=12,
        skipped_rows=[
            (2, "private-sample-id"),
            (5, "confidential"),
        ],
    )

    assert "messy.csv" in message
    assert "12 valid points" in message
    assert "2 skipped rows" in message
    assert "first skipped lines: 2, 5" in message
    assert "private-sample-id" not in message
    assert "confidential" not in message
    assert "/home/scientist/private" not in message
