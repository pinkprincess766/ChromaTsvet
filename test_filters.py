import unittest
from unittest.mock import patch

import numpy as np
from scipy.ndimage import median_filter

import filters


class SignalFiltersTest(unittest.TestCase):
    def test_none_returns_independent_float_array(self):
        source = np.array([1, 2, 3], dtype=np.int32)

        result = filters.apply_filter(source, "none")

        np.testing.assert_array_equal(result, source)
        self.assertEqual(result.dtype, np.float64)
        self.assertFalse(np.shares_memory(result, source))

    def test_median_matches_scipy(self):
        source = np.array([1.0, 2.0, 100.0, 3.0, 4.0])

        result = filters.apply_filter(source, "median", {"window_size": 3})

        expected = median_filter(source, size=3, mode="nearest")
        np.testing.assert_array_equal(result, expected)

    def test_empty_signal_is_supported(self):
        result = filters.apply_filter([], "median")

        self.assertEqual(result.shape, (0,))
        self.assertEqual(result.dtype, np.float64)

    def test_filter_names_and_defaults_are_normalized(self):
        filter_type, params = filters.normalize_filter_settings(" MEDIAN ")

        self.assertEqual(filter_type, "median")
        self.assertEqual(params, {"window_size": 5})

    def test_invalid_signals_are_rejected(self):
        invalid_signals = (
            None,
            "1,2,3",
            np.array([[1.0, 2.0]]),
            np.array([True, False]),
            np.array([1.0, np.nan]),
            np.array([1.0, np.inf]),
        )

        for signal in invalid_signals:
            with self.subTest(signal=signal):
                with self.assertRaises(filters.FilterError):
                    filters.apply_filter(signal, "none")

    def test_invalid_filter_settings_are_rejected(self):
        invalid_settings = (
            ("unknown", {}),
            ("median", {"window_size": 2}),
            ("median", {"window_size": 4}),
            ("median", {"window_size": 53}),
            ("median", {"window_size": 5.0}),
            ("median", {"unexpected": 5}),
            ("none", {"window_size": 5}),
        )

        for filter_type, params in invalid_settings:
            with self.subTest(filter_type=filter_type, params=params):
                with self.assertRaises(filters.FilterError):
                    filters.apply_filter([1.0, 2.0], filter_type, params)

    def test_missing_scipy_is_reported_as_filter_error(self):
        with patch.object(filters, "scipy_median_filter", None):
            with self.assertRaises(filters.FilterDependencyError):
                filters.apply_filter([1.0, 2.0, 3.0], "median")


if __name__ == "__main__":
    unittest.main()
