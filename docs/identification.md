# Peak-Based Identification Plan

ChromaTsvet v0.1 uses `SpectrumIdentifier` as a baseline matcher: it compares
stored reference intensities with the analyzed spectrum using cosine similarity.
This is useful for smoke testing the workflow, but it is not a strong scientific
identification method.

The next identification implementation should move from raw array comparison to
peak-feature matching.

## Required Peak Features

Each analyzed and reference spectrum should expose:

- `frequency_hz`
- `intensity`
- `width_hz`
- `area`
- `snr`

Reference records also need the analysis settings used to generate those
features, especially `sample_rate_hz`, baseline mode, normalization mode, and
peak-detection parameters.

## Matching Model

A first peak-based matcher should:

1. Match peaks by nearest frequency within a configurable tolerance.
2. Score matched peaks by frequency error, relative intensity/area agreement,
   and optional width agreement.
3. Penalize unmatched strong peaks in either the unknown sample or the reference.
4. Return transparent diagnostics: matched peaks, unmatched sample peaks,
   unmatched reference peaks, and the final score components.

This keeps the algorithm inspectable and avoids presenting raw cosine similarity
as chemical identification.

## Data Model Work

Before replacing the current matcher, the SQLite library needs a schema that can
store reference peak features and the settings used to compute them. A migration
should keep existing v0.1 reference spectra readable, but mark them as legacy
raw-spectrum references until they are recalculated.

## Suggested Implementation Order

1. Add `ReferencePeak` and `PeakMatch` dataclasses in Python.
2. Add a reference-peak table or JSON field with an explicit schema version.
3. Implement a pure Python peak matcher with deterministic synthetic tests.
4. Add GUI diagnostics for matched and unmatched peaks.
5. Keep cosine similarity as a fallback for legacy references.
