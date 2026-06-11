[日本語版はこちら](README.ja.md)

# ChromaTsvet

**ChromaTsvet** is a desktop application for loading, processing, visualizing, and identifying spectral data and chromatograms.

The project combines a Python desktop interface with a Rust/PyO3 signal-processing core, making it a practical foundation for a fast and reliable scientific analysis tool.

The name **ChromaTsvet** honors **Mikhail Semyonovich Tsvet**, the botanist who invented chromatography.

## Features

- Load spectral data and chromatograms from CSV/TXT files
- Process numeric signals with the Rust backend
- Apply windowing and FFT-based spectrum calculation
- Detect peaks in processed spectra
- Compare spectra against a local SQLite reference library
- Add and restore reference substances
- Visualize spectra and detected peaks in a PyQt desktop UI
- Export analysis results to PDF reports

## Installation

### Windows

1. Install Python 3.9 or newer.
2. Install the Python dependencies:

   ```bat
   py -m pip install numpy scipy PyQt5 pyqtgraph reportlab Pillow
   ```

3. Make sure the compiled Rust extension module is available in the project root:

   ```text
   spectrometer_rust.pyd
   ```

4. Run the application:

   ```bat
   py python_analyzer\main.py
   ```

### macOS / Linux

1. Install Python 3.9 or newer.
2. Install the Python dependencies:

   ```bash
   python3 -m pip install numpy scipy PyQt5 pyqtgraph reportlab Pillow
   ```

3. Build or place the platform-specific Rust/PyO3 extension module in the project root.
4. Run the application:

   ```bash
   python3 python_analyzer/main.py
   ```

## Building from Source

The Rust signal-processing module lives in `rust_module/` and is exposed to Python through PyO3.

To check and test the Rust module:

```bash
cd rust_module
cargo test
```

To build the extension module manually, build the Rust crate as a `cdylib` and place the resulting platform-specific Python extension in the project root:

- Windows: `spectrometer_rust.pyd`
- macOS / Linux: platform-specific shared extension module

Packaging with tools such as `maturin` is a planned improvement, but the current project keeps the build flow intentionally simple.

## Usage

1. Start ChromaTsvet.
2. Click **Open file** and select a CSV or TXT file with numeric signal values.
3. The application loads the data, processes the signal, and displays the resulting spectrum.
4. Detected peaks are marked on the plot.
5. Candidate substance matches are shown in the results table.
6. Use **Add** to add a reference substance to the local library.
7. Use **PDF Report** to export the current analysis results.

For best results, use clean numeric input files with one signal value per row.

## Project Structure

```text
.
├── python_analyzer/
│   ├── main.py                  # PyQt GUI, file loading, plotting, PDF export
│   └── core/
│       └── identification.py    # SQLite-backed spectrum identification
├── rust_module/
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs               # PyO3 module exports
│       ├── types.rs             # Python-visible Rust data types
│       └── signal/
│           ├── filters.rs       # Signal filters
│           ├── fft.rs           # FFT magnitude spectrum
│           ├── peak_detection.rs
│           └── window.rs        # Window functions
├── library.db                   # Reference substance database
├── spectrometer_rust.pyd        # Compiled Windows extension module
├── test_rust.py                 # Manual Rust module smoke test
└── README.md
```

## Technologies Used

- **Python** — application orchestration and desktop UI
- **PyQt5** — native desktop interface
- **pyqtgraph** — interactive plotting
- **NumPy** — numeric array handling
- **SQLite** — local reference library
- **reportlab** — PDF report generation
- **Rust** — performance-sensitive signal processing
- **PyO3** — Python bindings for the Rust module
- **rustfft / ndarray** — FFT and array operations in Rust

## Roadmap

- Improve scientific peak matching and scoring
- Add clearer analysis parameters in the UI
- Include plots and processing metadata in PDF reports
- Add a reproducible cross-platform build flow
- Expand automated tests for file loading, identification, and Rust DSP edge cases
- Improve reference-library management and validation

## License

This project is licensed under the **MIT License**.

See the [LICENSE](LICENSE) file for the full text.
