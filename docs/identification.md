# Peak-Based Identification

ChromaTsvet keeps the original cosine-similarity matcher as a legacy fallback
for old reference records. Newer reference records can store peak features and
use peak-based matching through `SpectrumIdentifier.find_peak_matches()`.

The peak matcher is still an inspectable baseline, not a validated laboratory
identification method.

## Required Peak Features

Each analyzed and reference spectrum should expose:

- `frequency_hz`
- `intensity`
- `width_hz`
- `area`
- `snr`

Reference records also need the analysis settings used to generate those
features, especially `sample_rate_hz`, baseline mode, normalization mode, and
peak-detection parameters. Optional spectrum smoothing, prominence, distance,
and minimum SNR settings are part of the peak-list definition and should match
when comparing reference and unknown spectra.

The detector keeps the strongest peak as a compatibility fallback even when a
strict SNR threshold removes other candidates. That prevents empty peak lists
from a single aggressive setting while still allowing SNR to suppress weaker
noise peaks.

## Current Matching Model

The current matcher:

1. Filters references by `data_type`, with `generic` as a fallback.
2. Builds candidate pairs within a configurable frequency tolerance.
3. Scores pairs by frequency agreement and symmetric log-ratio agreement for
   intensity and area.
4. Selects one-to-one matches greedily by score.
5. Penalizes unmatched peaks in the final score.
6. Returns transparent diagnostics: matched peaks, unmatched sample peaks,
   unmatched reference peaks, and the final score components.
7. Ranks all compatible references deterministically by score, reference
   coverage, mean frequency error, and candidate name.

The GUI keeps those diagnostics intact. The result table reports matched peak
count, coverage of both the sample and reference, mean absolute frequency
error, and a conservative evidence band. Double-clicking a candidate opens the
matched and unmatched peak lists used to reach that result.

Evidence bands are deliberately cautious:

- one matched peak can be at most `weak` evidence;
- `moderate` requires at least two matches and 40% coverage on both sides;
- `strong` requires at least three matches, a score of at least 0.85, and 60%
  coverage on both sides;
- non-finite or incomplete diagnostics become `insufficient`.

These labels describe computational candidate evidence. They are not a
validated chemical identification and should be reviewed alongside the raw
spectrum, analysis method, and reference provenance.

The current band thresholds are explicit conservative UI heuristics, not
empirically calibrated decision limits. They must not be used as acceptance
criteria for laboratory work until validated against representative reference
and unknown datasets. Evidence summarization adds one `O(M)` pass over the
selected peak pairs and uses constant auxiliary space.

Candidate generation sorts both peak lists and scans a frequency window:

```text
O(U log U + R log R + K log K)
```

where `U` is the number of unknown peaks, `R` is the number of reference peaks,
and `K` is the number of candidate peak pairs inside the tolerance window.

## Data Model

SQLite references support:

- legacy `spectrum` JSON values for cosine matching;
- `peaks_json` for peak features;
- `schema_version`;
- `data_type`;
- scientific metadata: description, CAS Registry Number, standard
  manufacturer, and bounded category labels;
- acquisition metadata: sample identifier, instrument, operator name, and an
  ISO `YYYY-MM-DD` measurement date.

Older records remain readable. Peak-only records store an empty legacy spectrum
when needed for compatibility with older SQLite schemas.

Portable reference-library documents use export schema v3. The JSON and CSV
readers still accept schema v1 and v2 documents; metadata introduced by newer
schemas is initialized to empty values. CAS numbers are validated by structure
and check digit, and measurement dates must use the exact ISO `YYYY-MM-DD`
form. Exported documents contain only reference data and never include database
paths, source file paths, or recent-file state.

## Next Steps

1. Store full analysis settings alongside reference peaks.
2. Surface reference provenance and acquisition metadata in candidate details.
3. Consider replacing greedy selection with an optimal assignment algorithm if
   dense or ambiguous peak sets become common.
4. Rebuild the default reference library with real peak features.
