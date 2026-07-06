import unittest

from python_analyzer.gui.error_messages import (
    safe_exception_details,
    spectrum_read_error_text,
)


class ErrorMessagesTest(unittest.TestCase):
    def test_file_not_found_details_do_not_leak_path(self):
        path = "private/run42/spectrum.csv"
        exception = FileNotFoundError(2, "No such file or directory", path)

        details = safe_exception_details(exception)
        error_text = spectrum_read_error_text(exception)

        self.assertEqual(details, "No such file or directory")
        self.assertNotIn(path, details)
        self.assertIn("moved, renamed, or deleted", error_text.message)
        self.assertNotIn(path, error_text.message)

    def test_unicode_error_message_is_actionable(self):
        exception = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

        details = safe_exception_details(exception)
        error_text = spectrum_read_error_text(exception)

        self.assertIn("utf-8 decode error near byte 0", details)
        self.assertEqual(error_text.title, "Unsupported text encoding")
        self.assertIn("UTF-8 CSV/TXT", error_text.message)
