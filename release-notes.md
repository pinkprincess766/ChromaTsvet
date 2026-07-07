# ChromaTsvet v0.2.0

ChromaTsvet v0.2.0 is an alpha source release focused on everyday usability,
clearer analysis state, richer exports, and stronger regression testing.

## Highlights

- Added Recent Files and remembered last directory for faster repeated work.
- Improved the status bar with source file, point count, peak count, and analysis state.
- Added keyboard shortcuts for common workflow actions.
- Added FFT window selection to the analysis settings UI.
- Improved CSV/TXT import behavior and user-facing error messages.
- Added HTML report export and Excel workbook export.
- Added pytest configuration and a structured `tests/` layout.
- Added a deterministic synthetic spectrum harness for peak-detection regression tests.
- Updated English, Russian, and Japanese README documentation for v0.2.

## Existing Analysis Capabilities

- Rust/PyO3 signal-processing core with FFT, Savitzky-Golay filtering, baseline correction, area normalization, spectrum smoothing, and peak detection.
- Peak metrics including frequency, intensity, FWHM width, Gaussian area, and SNR.
- Peak markers, peak table, mouse zoom, CSV peak export, PDF reports, HTML reports, and Excel workbooks.
- Local SQLite reference library with peak-based identification and legacy cosine fallback.

## Status

This is still alpha scientific software. ChromaTsvet is useful for local
experiments, inspection, demonstrations, and development, but it is not a
validated laboratory instrument.

## Next Planned

- Richer peak-match diagnostics.
- Stronger reference-library management workflow.
- Cross-platform packaged builds.
- Broader synthetic and real-world regression datasets.
