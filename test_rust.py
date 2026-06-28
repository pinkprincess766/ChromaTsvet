import sys
from pathlib import Path
import unittest

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import spectrometer_rust


TEST_SIGNAL = [
    0.1,
    0.2,
    0.5,
    1.0,
    3.0,
    12.0,
    8.0,
    4.0,
    1.5,
    0.6,
    0.3,
    2.5,
    9.0,
    6.0,
    1.0,
]


def run_rust_pipeline():
    return spectrometer_rust.process_signal(
        data=TEST_SIGNAL,
        sample_rate=1000.0,
        filter_type="median",
        window_type="hann",
        threshold=0.01,
    )


class RustModuleSmokeTest(unittest.TestCase):
    def test_rust_pipeline_returns_spectrum_and_peaks(self):
        result = run_rust_pipeline()

        self.assertIn("spectrum", result)
        self.assertIn("frequency_axis", result)
        self.assertIn("peaks", result)
        self.assertGreater(len(result["spectrum"]), 0)
        self.assertEqual(len(result["frequency_axis"]), len(result["spectrum"]))
        self.assertTrue(np.all(np.isfinite(result["spectrum"])))
        self.assertTrue(np.all(np.isfinite(result["frequency_axis"])))

        for peak in result["peaks"]:
            self.assertTrue(np.isfinite(peak.position))
            self.assertTrue(np.isfinite(peak.frequency))
            self.assertTrue(np.isfinite(peak.intensity))
            self.assertTrue(np.isfinite(peak.width_hz))

    def test_frequency_axis_uses_sample_rate(self):
        result = spectrometer_rust.process_signal(
            data=[0.0, 1.0, 0.0, -1.0],
            sample_rate=400.0,
            filter_type="none",
            window_type="rectangular",
            threshold=0.01,
            baseline=False,
        )

        self.assertEqual(result["frequency_axis"], [0.0, 100.0, 200.0])

    def test_peak_width_hz_uses_frequency_bin_width(self):
        result = run_rust_pipeline()
        self.assertGreater(len(result["peaks"]), 0)

        bin_width = result["sample_rate"] / len(TEST_SIGNAL)
        for peak in result["peaks"]:
            self.assertAlmostEqual(peak.width_hz, peak.width * bin_width)


def plot_smoke_result(result):
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        print("matplotlib is not installed; skipping the optional plot.")
        return

    plt.figure(figsize=(12, 8))
    plt.subplot(2, 1, 1)
    plt.plot(TEST_SIGNAL, label="Input signal", color="gray", alpha=0.7)
    plt.plot(result["spectrum"], label="After FFT", color="blue", linewidth=2)
    plt.title("Spectrum after processing")
    plt.xlabel("Index")
    plt.ylabel("Amplitude")
    plt.grid(True)
    plt.legend()

    plt.subplot(2, 1, 2)
    if result["peaks"]:
        positions = [peak.position for peak in result["peaks"]]
        intensities = [peak.intensity for peak in result["peaks"]]
        plt.stem(positions, intensities, linefmt="r-", markerfmt="ro", basefmt=" ")
        plt.title("Detected peaks")
    else:
        plt.text(
            0.5,
            0.5,
            "No peaks detected",
            ha="center",
            va="center",
            transform=plt.gca().transAxes,
        )
    plt.xlabel("Position")
    plt.ylabel("Intensity")
    plt.grid(True)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    print("Rust module loaded. Version:", spectrometer_rust.get_version())
    smoke_result = run_rust_pipeline()
    print("\n=== Rust pipeline smoke test ===")
    print(f"Spectrum length: {len(smoke_result['spectrum'])}")
    print(f"Detected peaks: {len(smoke_result['peaks'])}")
    for peak in smoke_result["peaks"]:
        print(
            f"  peak -> pos: {peak.position:.2f} | "
            f"int: {peak.intensity:.2f} | SNR: {peak.snr:.2f}"
        )
    plot_smoke_result(smoke_result)
