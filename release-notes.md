# ChromaTsvet v0.1.0

First public source release of ChromaTsvet.

## Highlights

- Clean modular architecture: `gui`, `viz`, `analysis`, and `readers`.
- Rust/PyO3 signal-processing core with FFT, Savitzky-Golay filtering, baseline correction, area normalization, and peak detection.
- PyQt5 desktop interface with light and dark themes.
- Detected peak markers, peak table, mouse zoom, CSV peak export, and PDF report export.
- Local SQLite reference library with first-run default data.
- Release screenshots and deterministic screenshot regeneration script.

## Changes Since Early Development

- Removed automatic demo data on startup.
- Added `pyproject.toml` and the `chromatsvet` entry point.
- Added GitHub Actions CI for Python and Rust tests.
- Added README assets, screenshots, and v0.1 release documentation.
- Removed local SQLite and build artifacts from the tracked repository.
- Refactored the original monolithic GUI into smaller modules.

## Status

This is an alpha release intended for experiments, demonstrations, and further development. ChromaTsvet is not yet a validated laboratory instrument.

## Next Planned

- Stronger peak-based identification.
- Packaged binaries for Windows and macOS.
- Richer reference-library management workflow.
