import unittest

import numpy as np

from python_analyzer.viz.spectrum_plot import SpectrumPlot


class SpectrumPlotFrequencyAxisTest(unittest.TestCase):
    def setUp(self):
        self.plot_helper = SpectrumPlot.__new__(SpectrumPlot)

    def test_uses_valid_frequency_axis_from_result(self):
        axis = self.plot_helper.frequency_axis(
            {"frequency_axis": [0.0, 10.0, 20.0]},
            3,
            sample_rate=400.0,
            source_signal_len=4,
        )

        np.testing.assert_allclose(axis, [0.0, 10.0, 20.0])

    def test_rebuilds_missing_frequency_axis_from_sample_rate(self):
        axis = self.plot_helper.frequency_axis(
            {"sample_rate": 400.0},
            3,
            source_signal_len=4,
        )

        np.testing.assert_allclose(axis, [0.0, 100.0, 200.0])

    def test_rebuilds_invalid_frequency_axis_from_explicit_sample_rate(self):
        axis = self.plot_helper.frequency_axis(
            {"frequency_axis": [0.0, float("nan"), 2.0]},
            3,
            sample_rate=800.0,
            source_signal_len=8,
        )

        np.testing.assert_allclose(axis, [0.0, 100.0, 200.0])

    def test_rejects_unphysical_fallback_metadata(self):
        with self.assertRaises(ValueError):
            self.plot_helper.frequency_axis(
                {"frequency_axis": []},
                3,
                sample_rate=float("nan"),
                source_signal_len=4,
            )

        with self.assertRaises(ValueError):
            self.plot_helper.frequency_axis(
                {"frequency_axis": []},
                5,
                sample_rate=400.0,
                source_signal_len=4,
            )


if __name__ == "__main__":
    unittest.main()
