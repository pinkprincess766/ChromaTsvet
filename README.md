<p align="right"><a href="README.ru.md">Русский</a> | <a href="README.ja.md">日本語</a></p>

<p align="center">
  <img src="assets/chromatsvet_readme_logo.png" alt="ChromaTsvet logo" width="430">
</p>

<h1 align="center">ChromaTsvet</h1>

<p align="center">
  A desktop application for loading, processing, visualizing, and identifying
  spectral data and chromatograms.
</p>

<p align="center">
  <a href="https://github.com/pinkprincess766/ChromaTsvet/actions/workflows/ci.yml"><img src="https://github.com/pinkprincess766/ChromaTsvet/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/release-v0.3.0-2f855a" alt="Release v0.3.0">
  <img src="https://img.shields.io/badge/Python-3.9%2B-3776ab" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/Rust-PyO3-b7410e" alt="Rust and PyO3">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-4c566a" alt="MIT license"></a>
</p>

![ChromaTsvet spectrum analysis](docs/screenshots/01-main-spectrum.png)

## Quick Demo

![ChromaTsvet workflow demo](docs/demo/chromatsvet-workflow.gif)

The demo uses only the synthetic sample data from `examples/alpha/`. It shows
the basic tester path: open a sample file, run analysis, inspect detected peaks
on the graph and table, then export a report.

ChromaTsvet combines a PyQt desktop interface with a Rust/PyO3 signal-processing
core. It is designed as a practical, inspectable foundation for scientific
signal analysis rather than a black-box workflow. The name honors Mikhail
Semyonovich Tsvet, the botanist who invented chromatography.

## Project Status

ChromaTsvet v0.3.0 is an alpha release focused on scientific traceability,
reference-library portability, and easier tester onboarding. It can be run from
source, and macOS/Windows release builds can now be produced as downloadable app
archives for GitHub Releases. It is ready for local experiments, demonstrations, and
iterative scientific tooling work, but it is not yet a validated laboratory
instrument.

For guided closed-alpha testing, see the [Alpha Testing Guide](docs/testing_guide.md).
The guide includes safe synthetic sample files, a manual verification checklist,
and reporting instructions for testers.

Continuous integration runs the Python and Rust test suites. The Python tests
now use pytest, and the project includes deterministic synthetic spectra for
regression checks around peak detection. Peak-based identification is available
as an inspectable baseline with legacy cosine matching kept as a compatibility
fallback.

## What's New in v0.3

v0.3 focuses on making analysis results easier to inspect, reproduce, share,
and test.

**Analysis traceability:**

- Processing Passport data is included in report exports.
- Analysis session bundles preserve the file-independent analysis snapshot.
- Method presets make repeated peak-detection workflows easier to reuse.

**Peak review and reference libraries:**

- Peak Review helps inspect accepted, rejected, manual, and warning-heavy peaks.
- Manual peak add/edit/remove is available for reviewer-controlled corrections.
- Reference libraries can be imported and exported as portable JSON/CSV data with duplicate handling.

**Distribution and testing:**

- macOS and Windows desktop archives can be built for GitHub Releases.
- README workflow GIF and tester onboarding documentation are included.
- Architecture boundaries were tightened to keep UI, exports, analysis state, and reference persistence more explicit.

## Highlights

- Load numeric spectral or chromatographic data from CSV and TXT files.
- Apply median or Savitzky-Golay signal filtering, optional spectrum smoothing, and baseline correction.
- Calculate an FFT spectrum using a configurable sample rate and frequency axis.
- Normalize a spectrum by integral area when comparable intensity scaling is needed.
- Detect peaks with threshold, prominence, distance, and SNR controls; calculate frequency, intensity, FWHM width in bins/Hz, Gaussian area, and SNR.
- Inspect detected peaks in the plot and in a detailed analysis table.
- Zoom into the spectrum with the mouse.
- Overlay a second analyzed spectrum on the current graph for visual comparison.
- Reopen recent files, reuse the last working directory, and use workflow keyboard shortcuts.
- Save and reload analysis session bundles without embedding private source-file paths.
- Use method presets for repeatable analysis settings.
- Review peaks, add manual peaks, edit peak metadata, and exclude rejected peaks from exports.
- Compare spectra against a local SQLite reference library and manage stored references.
- Import or export reference-library records as portable JSON or CSV.
- Export detected peaks with analysis metadata to CSV and complete analysis results to PDF, HTML, or Excel.
- Export the current spectrum graph as PNG or SVG.
- Use light and dark application themes.

## Screenshots

<table>
  <tr>
    <td width="50%"><strong>Analysis settings</strong></td>
    <td width="50%"><strong>Detected peaks</strong></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/02-analysis-settings.png" alt="Analysis settings dialog"></td>
    <td><img src="docs/screenshots/03-peaks-table.png" alt="Detected peaks table"></td>
  </tr>
  <tr>
    <td colspan="2"><strong>PDF analysis report</strong></td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="docs/screenshots/04-pdf-report.png" alt="Generated PDF analysis report" width="620"></td>
  </tr>
</table>

The release screenshots use a deterministic demonstration signal containing
components at 95 Hz, 240 Hz, and 410 Hz. They can be regenerated with
`tools/capture_release_screenshots.py`; the PNG files are intended for the
README and GitHub release notes. Regenerating the PDF preview requires either
`pypdfium2` or Poppler's `pdftoppm`.

## Download App

For GitHub Releases, v0.3 can provide ready-to-run desktop archives:

```text
ChromaTsvet-v0.3.0-macos-<architecture>.zip
ChromaTsvet-v0.3.0-windows-<architecture>.zip
SHA256SUMS-<platform>.txt
```

Download the archive for your platform from the release page and unzip it. On
macOS, open `ChromaTsvet.app`. On Windows, open `ChromaTsvet.exe` from the
unzipped `ChromaTsvet` folder. The current macOS build is unsigned and not
notarized, so macOS may show a security warning on first launch. Verify the
archive with the matching `SHA256SUMS` file if you received it outside GitHub
Releases.

Source checkout installation remains available for development and for platforms
without a packaged app yet.

## Getting Started

### Prerequisites

- Python 3.9 or newer
- A current Rust toolchain with Cargo
- Platform build tools required by PyO3

### Build and run from source

```bash
git clone https://github.com/pinkprincess766/ChromaTsvet.git
cd ChromaTsvet

make setup
make doctor
make run
```

`make setup` creates `.venv`, installs the Python development dependencies, and
builds the Rust/PyO3 extension with maturin.

If `make` is not available, use the same workflow through Python:

```bash
python scripts/dev.py setup
python scripts/dev.py doctor
python scripts/dev.py run
```

The installed console entry point is the recommended way to start the
application. The historical direct script invocation is still supported:

```bash
python python_analyzer/main.py
```

On Windows, prefer the Python helper:

```bat
py scripts\dev.py setup
py scripts\dev.py doctor
py scripts\dev.py run
```

The application starts without demo data; use **Open file** to load a CSV or TXT
spectrum.

Synthetic smoke-test inputs are available in `examples/alpha/` for testers who
want to verify import, analysis, plotting, and export without using private data.

### First tester smoke test

For a first pass, use the safe synthetic sample data:

1. Start the app with `make run` or `python scripts/dev.py run`.
2. Open `examples/alpha/clean_three_peaks.csv`.
3. Confirm that analysis runs and detected peaks appear on the graph and in the peak table.
4. Export one report, preferably PDF or HTML, and confirm it contains the same filename, settings, and peak count shown in the app.

For the full closed-alpha checklist, see the [Alpha Testing Guide](docs/testing_guide.md).

## Input Data

The simplest supported file contains one intensity value per line:

```text
intensity
0.12
0.35
1.42
0.48
```

Headerless two-column files are also supported; the second column is interpreted
as intensity. Named table columns such as `intensity`, `amplitude`, `signal`,
`value`, or `absorbance` are detected automatically. CSV files may use comma,
semicolon, or tab delimiters.

After loading a file, set the correct sample rate in **Analysis Settings**. The
sample rate is required to convert FFT bins into physical frequency values.

## Typical Workflow

1. Open a CSV or TXT signal file.
2. Configure sample rate, filtering, spectrum smoothing, baseline correction, and peak-detection parameters.
3. Run the analysis and inspect marked peaks on the frequency plot.
4. Optionally load an overlay spectrum for visual comparison.
5. Review peak frequency, intensity, width in bins/Hz, area, and SNR in the results table.
6. Export the peak list as CSV or generate a PDF, HTML, or Excel analysis report.

## Development

For development and tests, install the optional test dependencies:

```bash
make setup
```

Run the Python test suite from the project root:

```bash
make test
```

Run the Rust unit tests:

```bash
make rust
```

`make check` runs both suites. The raw commands are still available when needed:
`QT_QPA_PLATFORM=offscreen python -m pytest -v` and
`cargo test --manifest-path rust_module/Cargo.toml`.

Run the deterministic synthetic spectrum regression tests:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/unit/test_synthetic_peak_detection.py -v
```

Regenerate the v0.3 PNG screenshot set:

```bash
QT_QPA_PLATFORM=offscreen python tools/capture_release_screenshots.py
```

Regenerate the README workflow GIF:

```bash
QT_QPA_PLATFORM=offscreen python tools/capture_readme_demo_gif.py
```

See [Development Notes](docs/development.md) for the current maturin workflow
and performance profiling procedure. See [Peak-Based Identification](docs/identification.md)
for the current peak-based matcher and legacy cosine fallback behavior.

Build the release app archive for the current platform:

```bash
python tools/build_release_app.py
```

The generated zip and checksum are written to `release_artifacts/v0.3.0/`. This
folder is ignored by git and is intended only as a staging area for GitHub
Release uploads. Windows archives must be built on Windows; use the manual
`Release Artifacts` GitHub Actions workflow when building from a macOS machine.

## Architecture

```text
python_analyzer/
  main.py                    Thin bootstrap and compatibility facade
  gui/main_window.py         MainWindow orchestration, state, exports
  gui/dialogs.py             Settings, analysis settings, and log dialogs
  gui/error_messages.py      User-facing error message helpers
  gui/recent_files.py        Recent Files and remembered directory helpers
  gui/reference_library.py   Reference library management dialog
  gui/peak_editor.py         Manual peak add/edit dialog
  gui/theme.py               Qt palette and stylesheet helpers
  gui/log_view.py            Shared log-view formatting
  analysis/models.py         AnalysisSettings and LoadedSpectrum dataclasses
  analysis/runner.py         Filter -> Rust pipeline wrapper
  analysis/method_presets.py Reusable analysis method presets
  analysis/peak_review.py    Peak review status and diagnostics
  analysis/session_bundle.py Portable analysis session snapshots
  analysis/processing_passport.py
                             Processing metadata for report exports
  analysis/windowing.py      FFT window names, labels, and validation
  exporters/excel_report.py  Excel workbook export
  exporters/html_report.py   Self-contained HTML report export
  exporters/pdf_report.py    PDF report generation
  exporters/peak_csv.py      Detected peak CSV export
  readers/spectrum_reader.py CSV/TXT spectrum parsing
  viz/spectrum_plot.py       Spectrum plotting, frequency axis, peak markers
  core/identification.py     SQLite-backed reference matching
  core/reference_library_io.py
                             Portable reference import/export
  core/reference_repository.py
                             SQLite reference persistence

rust_module/src/
  lib.rs                     PyO3 analysis pipeline
  types.rs                   Python-visible result types
  signal/filters.rs          Filters and baseline correction
  signal/fft.rs              FFT and frequency-axis calculation
  signal/normalization.rs    Integral-area normalization
  signal/peak_detection.rs   Peak metrics and detection
  signal/window.rs           FFT window functions

tests/
  conftest.py                Shared pytest fixtures
  support/synthetic_spectra.py
                             Synthetic spectra and peak-matching test helpers
  unit/                      Unit and focused regression tests
```

Python owns file handling, the desktop UI, and reporting. Rust owns the numerical
pipeline and returns the processed spectrum, frequency axis, and peak structures
through PyO3.

## v0.3 Scope and Roadmap

Version 0.3 improves traceability, reviewability, and release readiness around
the existing analysis foundation. The application can load data, tune analysis
settings from the GUI, visualize and export results, preserve user settings,
reopen recent files, save analysis sessions, review/manual-correct peaks, move
reference libraries between machines, and produce PDF, HTML, Excel, PNG, SVG,
and peak CSV outputs. Peak-based reference results retain matched and unmatched
peak diagnostics, report coverage and frequency error, and expose conservative
candidate-evidence bands for review.

The next development priorities are representative reference-validation
datasets, stronger real-world tester feedback loops, cross-platform
signed/notarized builds, and broader synthetic and real-world regression
datasets. The identification model and its evidence limits are outlined in
[Peak-Based Identification](docs/identification.md).

## Known Limitations

ChromaTsvet is still **alpha** scientific software. It is useful for
experiments, inspection, development, and educational purposes, but it is **not a
certified laboratory instrument**.

- Peak-based identification and reference-library workflows are still evolving.
- macOS app archives are unsigned and not notarized; Linux packaged builds are not available yet.
- Japanese documentation ([README.ja.md](README.ja.md)) may temporarily lag behind the English README.

## License

ChromaTsvet is released under the [MIT License](LICENSE).
