# ChromaTsvet Alpha Testing Guide

ChromaTsvet is currently alpha scientific software. This guide is intended for
small, controlled testing with technically patient users who can manually verify
important numerical results.

ChromaTsvet is not a certified laboratory instrument. Do not use alpha results
as the only basis for publication, medical, safety-critical, regulatory, or
production laboratory decisions.

## What to Test

Please focus on everyday workflows:

1. Install and run the application from source.
2. Open CSV or TXT files.
3. Configure analysis settings.
4. Run analysis and inspect the spectrum plot.
5. Review detected peaks in the peak table.
6. Export PDF, HTML, Excel, graph images, and peak CSV files.
7. Try recent files and remembered directories.
8. Add or edit local reference-library entries.
9. Manually add, edit, or remove peaks when the automatic result needs review.

## Quick Setup

From the project root:

```bash
make setup
make doctor
make run
```

If `make` is not available:

```bash
python scripts/dev.py setup
python scripts/dev.py doctor
python scripts/dev.py run
```

## 15-Minute Tester Onboarding

Use this path for a first smoke test before trying private or instrument-specific
files.

1. Start ChromaTsvet from the project root:

   ```bash
   make run
   ```

   If `make` is unavailable, use `python scripts/dev.py run`.

2. Open `examples/alpha/clean_three_peaks.csv`.
3. Keep the default analysis settings for the first run, or set sample rate to
   `1000` if the field is empty.
4. Confirm that the application shows:
   - the loaded filename in the window/status area;
   - a populated spectrum graph;
   - peak markers on the graph;
   - rows in the detected peak table.
5. Export one report:
   - PDF or HTML is best for visual review;
   - Excel is useful for checking tabular values;
   - peak CSV is useful for checking downstream data handling.
6. Compare the exported report with the application:
   - filename should match;
   - sample rate and analysis settings should match;
   - peak count should match;
   - the most visible peaks should have plausible frequency/intensity values.
7. Repeat with `examples/alpha/noisy_overlap.csv` and inspect warnings, SNR,
   prominence, and manual peak review behavior.

Stop after the first unexpected result and report it. A small reproducible bug
report is more useful than a long session where the original failure is hard to
reconstruct.

## Safe Sample Data

The `examples/alpha/` directory contains synthetic data only. These files are
for smoke testing import, analysis, plotting, and export behavior. They are not
chemical references.

- `clean_three_peaks.csv` - clean chromatogram-like signal.
- `decimal_comma_semicolon.txt` - semicolon-delimited data using decimal comma.
- `noisy_overlap.csv` - noisy signal with partially overlapping peaks.

Suggested first test:

1. Open `examples/alpha/clean_three_peaks.csv`.
2. Set a reasonable sample rate, for example `1000`.
3. Run analysis.
4. Check that the plot, peak table, and exports are populated.
5. Export PDF, HTML, Excel, PNG/SVG graph, and peak CSV.

## Manual Verification Checklist

Please verify manually when possible:

- peak positions are plausible for the loaded signal and selected sample rate;
- weak peaks are not blindly trusted without inspecting SNR and prominence;
- overlapping peaks are reviewed on the plot;
- exported reports contain the same filename, settings, peak count, and peak
  values shown in the application;
- manual peak edits are intentional and visible in exported results;
- reference-library matches are treated as candidates, not final proof.

## What to Report

Good reports include:

- operating system and Python version;
- how the app was started;
- input file shape and format, without sharing private sample names if sensitive;
- exact steps that produced the issue;
- expected behavior;
- actual behavior;
- screenshot or exported report when useful;
- whether the issue reproduces with files from `examples/alpha/`.

Please do not paste private local paths, access tokens, patient data, unpublished
sample names, or confidential laboratory identifiers into public GitHub issues.

## Known Alpha Risks

- Peak detection is still evolving, especially for low-SNR and overlapping peaks.
- Reference-library workflows are useful for inspection but not authoritative
  identification.
- Import logic supports common CSV/TXT variants, but real instrument exports can
  still contain unusual headers, encodings, or metadata blocks.
- Reports are designed for review and development, not formal regulated output.
