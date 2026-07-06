import unittest

from python_analyzer.analysis.windowing import (
    DEFAULT_FFT_WINDOW,
    fft_window_label,
    normalize_fft_window_type,
)


class WindowingTest(unittest.TestCase):
    def test_normalizes_supported_fft_window_names(self):
        self.assertEqual(normalize_fft_window_type("HANN"), "hann")
        self.assertEqual(normalize_fft_window_type(" hamming "), "hamming")
        self.assertEqual(normalize_fft_window_type("rectangular"), "rectangular")

    def test_invalid_fft_window_falls_back_to_default(self):
        self.assertEqual(normalize_fft_window_type("blackman"), DEFAULT_FFT_WINDOW)
        self.assertEqual(normalize_fft_window_type(None), DEFAULT_FFT_WINDOW)

    def test_fft_window_label_uses_normalized_value(self):
        self.assertEqual(fft_window_label("hamming"), "Hamming")
        self.assertEqual(fft_window_label("bad-value"), "Hann")
