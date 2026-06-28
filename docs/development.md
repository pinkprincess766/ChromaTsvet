# ChromaTsvet Development Notes

These notes capture the current engineering workflow for the source-based
v0.1 line. They intentionally separate correctness, build reproducibility, and
performance work.

## Build Model

ChromaTsvet currently has two build layers:

1. The Python application package, installed from the repository root.
2. The Rust/PyO3 extension, built from `rust_module/Cargo.toml` with maturin.

Development setup:

```bash
python -m pip install -e .
cd rust_module
maturin develop
cd ..
```

Release/CI wheel build:

```bash
maturin build --manifest-path rust_module/Cargo.toml --release --out dist
python -m pip install --no-deps dist/*.whl
```

The root `pyproject.toml` is deliberately owned by the Python package. The Rust
extension remains owned by `rust_module/Cargo.toml`; commands that build Rust
should pass `--manifest-path rust_module/Cargo.toml` explicitly.

## Scientific Correctness Checks

The FFT output is a single-sided magnitude spectrum for real input:

- the spectrum contains `n / 2 + 1` bins for even-length input;
- DC and Nyquist bins are not doubled;
- interior positive-frequency bins are doubled to preserve amplitude;
- frequency bins use `bin_width = sample_rate / input_signal_len`.

Peak positions and FWHM widths are measured in FFT-bin units inside the peak
detector. `process_signal` converts them at the API boundary:
`frequency = position * bin_width` and `width_hz = width * bin_width`.

When changing FFT, windows, normalization, or peak detection, update Rust unit
tests and Python smoke tests together.

## Performance Work

Performance changes should start with measurement, not Rayon.

Use the public API profiler:

```bash
python tools/profile_rust_pipeline.py
python tools/profile_rust_pipeline.py --sizes 2048 16384 131072 1048576 --repetitions 5
```

The profiler measures `spectrometer_rust.process_signal` with `filter_type="none"`,
matching the GUI architecture where Python applies the selected filter before
calling Rust. If a bottleneck is found, prefer algorithmic improvements before
parallelism. Rayon should be introduced only when profiling shows an independent
per-element or per-window workload large enough to overcome scheduling overhead.
