#!/usr/bin/env python3
"""Profile the public Rust/PyO3 signal-processing pipeline.

The goal is to make performance work evidence-based. This script measures the
same public API used by the GUI after Python-side filtering:
``spectrometer_rust.process_signal(..., filter_type="none")``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import statistics
import sys
from time import perf_counter

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import spectrometer_rust  # noqa: E402


def deterministic_signal(sample_rate: float, point_count: int) -> list[float]:
    """Return a reproducible synthetic signal with several frequency components."""
    time = np.arange(point_count, dtype=float) / sample_rate
    rng = np.random.default_rng(42)
    signal = (
        1.00 * np.sin(2.0 * np.pi * 95.0 * time)
        + 0.72 * np.sin(2.0 * np.pi * 240.0 * time + 0.35)
        + 0.46 * np.sin(2.0 * np.pi * 410.0 * time + 0.80)
        + 0.025 * rng.standard_normal(point_count)
    )
    return signal.tolist()


def run_pipeline(signal: list[float], sample_rate: float) -> dict:
    return spectrometer_rust.process_signal(
        data=signal,
        sample_rate=sample_rate,
        filter_type="none",
        window_type="hann",
        threshold=0.025,
        baseline=True,
        baseline_method="improved",
        prominence=0.02,
        distance=30,
        normalize=False,
    )


def measure(point_count: int, sample_rate: float, repetitions: int) -> tuple[float, int, int]:
    signal = deterministic_signal(sample_rate, point_count)
    run_pipeline(signal, sample_rate)

    timings = []
    spectrum_len = 0
    peak_count = 0
    for _ in range(repetitions):
        start = perf_counter()
        result = run_pipeline(signal, sample_rate)
        timings.append(perf_counter() - start)
        spectrum_len = len(result.get("spectrum", []))
        peak_count = len(result.get("peaks", []))

    return statistics.median(timings), spectrum_len, peak_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile ChromaTsvet's public Rust process_signal pipeline."
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=[2_048, 16_384, 131_072],
        help="Signal sizes to measure.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=7,
        help="Timing repetitions per signal size.",
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=2_048.0,
        help="Sampling rate used for the synthetic signal.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("ChromaTsvet Rust pipeline profile")
    print(f"sample_rate={args.sample_rate:g} Hz, repetitions={args.repetitions}")
    print()
    print(f"{'points':>10} {'spectrum':>10} {'peaks':>7} {'median_ms':>12}")
    print("-" * 43)
    for point_count in args.sizes:
        median_seconds, spectrum_len, peak_count = measure(
            point_count,
            args.sample_rate,
            args.repetitions,
        )
        print(
            f"{point_count:10d} {spectrum_len:10d} "
            f"{peak_count:7d} {median_seconds * 1_000.0:12.3f}"
        )


if __name__ == "__main__":
    main()
