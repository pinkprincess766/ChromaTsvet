"""Sequential, headless batch analysis for spectrum files."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

from python_analyzer.analysis import filters
from python_analyzer.analysis.models import AnalysisSettings
from python_analyzer.analysis.peak_review import (
    PEAK_REVIEW_ACCEPTED,
    PEAK_REVIEW_STATUSES,
)
from python_analyzer.analysis.runner import SignalProcessor
from python_analyzer.analysis.workflow import run_analysis_workflow
from python_analyzer.readers import SpectrumFileFormatError, read_spectrum_file


MAX_BATCH_FILES = 100
MAX_BATCH_FILE_SIZE_BYTES = 128 * 1024 * 1024
MAX_SOURCE_NAME_CHARACTERS = 255
MAX_BATCH_PEAK_RECORDS_PER_FILE = 10_000
MAX_BATCH_PEAK_RECORDS_TOTAL = 100_000
MAX_BATCH_PUBLIC_TEXT_CHARACTERS = 255
SUPPORTED_SPECTRUM_SUFFIXES = frozenset({".csv", ".txt"})
PUBLIC_FILTER_PARAMETER_KEYS = frozenset(
    {"window_size", "polyorder", "kernel_size"}
)

BATCH_STATUS_SUCCESS = "success"
BATCH_STATUS_FAILED = "failed"


class BatchSelectionError(ValueError):
    """Raised when the selected batch cannot be processed safely."""


@dataclass(frozen=True)
class BatchPeakRecord:
    """Finite, path-free peak snapshot retained for later batch export."""

    frequency: float | None = None
    position: float | None = None
    intensity: float | None = None
    prominence: float | None = None
    baseline_level: float | None = None
    left_base: float | None = None
    right_base: float | None = None
    width: float | None = None
    width_hz: float | None = None
    area: float | None = None
    noise: float | None = None
    snr: float | None = None
    is_global_max: bool = False
    review_status: str = ""
    review_reason: str = ""


@dataclass(frozen=True)
class BatchAnalysisItem:
    """Result for one input file, without raw signal or private path data."""

    source_name: str
    status: str
    point_count: int = 0
    peak_count: int = 0
    warning_count: int = 0
    skipped_row_count: int = 0
    error_message: str = ""
    peak_records: tuple[BatchPeakRecord, ...] = ()
    peak_details_available: bool = False
    peak_details_message: str = ""
    analysis_metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class BatchAnalysisSummary:
    """Aggregate result of a sequential batch operation."""

    items: tuple[BatchAnalysisItem, ...]
    requested_count: int
    cancelled: bool = False

    @property
    def successful_count(self) -> int:
        return sum(item.status == BATCH_STATUS_SUCCESS for item in self.items)

    @property
    def failed_count(self) -> int:
        return sum(item.status == BATCH_STATUS_FAILED for item in self.items)


BatchProgressCallback = Callable[[int, int, str], None]
BatchItemCallback = Callable[[BatchAnalysisItem], None]
CancelCallback = Callable[[], bool]


def analyze_spectrum_files(
    file_paths: Iterable[str | Path],
    settings: AnalysisSettings,
    *,
    processor: SignalProcessor | None = None,
    should_cancel: CancelCallback | None = None,
    on_progress: BatchProgressCallback | None = None,
    on_item_finished: BatchItemCallback | None = None,
    max_files: int = MAX_BATCH_FILES,
    max_file_size_bytes: int = MAX_BATCH_FILE_SIZE_BYTES,
) -> BatchAnalysisSummary:
    """Analyze selected files sequentially and isolate per-file failures.

    Sequential execution is deliberate: the thread-safety of the native DSP
    module has not yet been established for concurrent calls.
    """

    paths = _validated_selection(file_paths, max_files=max_files)
    _validate_file_size_limit(max_file_size_bytes)
    items: list[BatchAnalysisItem] = []
    cancelled = False
    retained_peak_record_count = 0

    for index, path in enumerate(paths, start=1):
        if should_cancel is not None and should_cancel():
            cancelled = True
            break

        if on_progress is not None:
            on_progress(index, len(paths), _safe_source_name(path))

        item = _analyze_one_file(
            path,
            settings,
            processor=processor,
            max_file_size_bytes=max_file_size_bytes,
            available_peak_record_slots=max(
                0,
                MAX_BATCH_PEAK_RECORDS_TOTAL - retained_peak_record_count,
            ),
        )
        items.append(item)
        retained_peak_record_count += len(item.peak_records)
        if on_item_finished is not None:
            on_item_finished(item)

    return BatchAnalysisSummary(
        items=tuple(items),
        requested_count=len(paths),
        cancelled=cancelled,
    )


def _validated_selection(
    file_paths: Iterable[str | Path],
    *,
    max_files: int,
) -> tuple[Path, ...]:
    if isinstance(file_paths, (str, bytes, bytearray, Path)):
        raise BatchSelectionError("Select spectrum files as a collection.")
    if not isinstance(max_files, int) or isinstance(max_files, bool) or max_files <= 0:
        raise BatchSelectionError("The batch file limit must be a positive integer.")

    paths: list[Path] = []
    try:
        for file_path in file_paths:
            if len(paths) >= max_files:
                raise BatchSelectionError(
                    f"Select no more than {max_files} spectrum files at once."
                )
            paths.append(Path(file_path))
    except BatchSelectionError:
        raise
    except (TypeError, ValueError) as exc:
        raise BatchSelectionError("The batch contains an invalid file selection.") from exc

    if not paths:
        raise BatchSelectionError("Select at least one spectrum file.")
    return tuple(paths)


def _analyze_one_file(
    path: Path,
    settings: AnalysisSettings,
    *,
    processor: SignalProcessor | None,
    max_file_size_bytes: int,
    available_peak_record_slots: int,
) -> BatchAnalysisItem:
    source_name = _safe_source_name(path)
    try:
        _validate_input_file(path, max_file_size_bytes=max_file_size_bytes)
        signal, skipped_rows = read_spectrum_file(path)
        if not signal:
            raise SpectrumFileFormatError("No numeric spectrum values were found.")
        outcome = run_analysis_workflow(signal, settings, processor=processor)
        peak_records, peak_details_available, peak_details_message = (
            _snapshot_peak_records(
                outcome.peaks,
                outcome.peak_reviews,
                available_peak_record_slots=available_peak_record_slots,
            )
        )
        return BatchAnalysisItem(
            source_name=source_name,
            status=BATCH_STATUS_SUCCESS,
            point_count=len(signal),
            peak_count=len(outcome.peaks),
            warning_count=_warning_count(outcome.result, outcome.peak_reviews),
            skipped_row_count=len(skipped_rows),
            peak_records=peak_records,
            peak_details_available=peak_details_available,
            peak_details_message=peak_details_message,
            analysis_metadata=_analysis_metadata(settings, outcome.result),
        )
    except Exception as exc:
        # A single malformed or unreadable file must not discard valid results
        # from the rest of the user's batch.
        return BatchAnalysisItem(
            source_name=source_name,
            status=BATCH_STATUS_FAILED,
            error_message=_safe_failure_message(exc),
        )


def _validate_input_file(path: Path, *, max_file_size_bytes: int) -> None:
    if path.suffix.casefold() not in SUPPORTED_SPECTRUM_SUFFIXES:
        raise SpectrumFileFormatError("Only CSV and TXT spectrum files are supported.")

    file_stat = path.stat()
    if not path.is_file():
        raise OSError("The selected item is not a regular file.")
    if file_stat.st_size == 0:
        raise SpectrumFileFormatError("The selected spectrum file is empty.")
    if file_stat.st_size > max_file_size_bytes:
        raise SpectrumFileFormatError(
            "The selected spectrum file exceeds the batch size limit."
        )


def _validate_file_size_limit(max_file_size_bytes: int) -> None:
    if not isinstance(max_file_size_bytes, int) or isinstance(
        max_file_size_bytes, bool
    ) or max_file_size_bytes <= 0:
        raise BatchSelectionError("The batch file-size limit must be positive.")


def _warning_count(result: dict[str, Any], reviews: Sequence[Any]) -> int:
    raw_warnings = result.get("processing_warnings", result.get("warnings", ()))
    if isinstance(raw_warnings, str):
        processing_warning_count = int(bool(raw_warnings.strip()))
    elif isinstance(raw_warnings, Sequence) and not isinstance(
        raw_warnings, (bytes, bytearray)
    ):
        processing_warning_count = len(raw_warnings)
    else:
        processing_warning_count = 0

    review_warning_count = sum(
        getattr(review, "status", None) != PEAK_REVIEW_ACCEPTED
        for review in reviews
    )
    return processing_warning_count + review_warning_count


def _safe_failure_message(exception: Exception) -> str:
    """Return controlled text without echoing paths or parser payloads."""

    if isinstance(exception, SpectrumFileFormatError):
        return "Unsupported or malformed spectrum data."
    if isinstance(exception, filters.FilterError):
        return "The configured signal filter could not be applied."
    if isinstance(exception, (OSError, UnicodeError)):
        return "The spectrum file could not be read."
    if isinstance(exception, BatchSelectionError):
        return str(exception)
    return f"Analysis failed ({type(exception).__name__})."


def _safe_source_name(path: Path) -> str:
    """Make an untrusted filename safe for compact plain-text UI output."""

    source_name = path.name or "<unnamed>"
    printable_name = "".join(
        character if character.isprintable() else "?"
        for character in source_name
    )
    return printable_name[:MAX_SOURCE_NAME_CHARACTERS] or "<unnamed>"


def _snapshot_peak_records(
    peaks: Sequence[Any],
    reviews: Sequence[Any],
    *,
    available_peak_record_slots: int,
) -> tuple[tuple[BatchPeakRecord, ...], bool, str]:
    peak_count = len(peaks)
    allowed_count = min(
        MAX_BATCH_PEAK_RECORDS_PER_FILE,
        available_peak_record_slots,
    )
    if peak_count > allowed_count:
        return (
            (),
            False,
            "Peak details were omitted because the safe batch export limit was exceeded.",
        )

    records = tuple(
        _peak_record(peak, reviews[index] if index < len(reviews) else None)
        for index, peak in enumerate(peaks)
    )
    return records, True, ""


def _peak_record(peak: Any, review: Any | None) -> BatchPeakRecord:
    status = str(getattr(review, "status", "") or "").strip().lower()
    if status not in PEAK_REVIEW_STATUSES:
        status = ""
    return BatchPeakRecord(
        frequency=_finite_peak_value(peak, "frequency"),
        position=_finite_peak_value(peak, "position"),
        intensity=_finite_peak_value(peak, "intensity"),
        prominence=_finite_peak_value(peak, "prominence"),
        baseline_level=_finite_peak_value(peak, "baseline_level"),
        left_base=_finite_peak_value(peak, "left_base"),
        right_base=_finite_peak_value(peak, "right_base"),
        width=_finite_peak_value(peak, "width"),
        width_hz=_finite_peak_value(peak, "width_hz"),
        area=_finite_peak_value(peak, "area"),
        noise=_finite_peak_value(peak, "noise"),
        snr=_finite_peak_value(peak, "snr"),
        is_global_max=bool(getattr(peak, "is_global_max", False)),
        review_status=status,
        review_reason=_safe_public_text(getattr(review, "reason", "")),
    )


def _finite_peak_value(peak: Any, attribute: str) -> float | None:
    try:
        value = float(getattr(peak, attribute, None))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _analysis_metadata(
    settings: AnalysisSettings,
    result: dict[str, Any],
) -> tuple[tuple[str, str], ...]:
    sample_rate = _positive_finite_value(
        result.get("sample_rate", settings.sample_rate),
        fallback=settings.sample_rate,
    )
    baseline = result.get(
        "baseline_method",
        settings.baseline_method if settings.baseline_enabled else "none",
    )
    normalization = result.get(
        "normalization",
        "area" if settings.normalize_area else "none",
    )
    smoothing_enabled = bool(
        result.get("spectrum_smoothed", settings.spectrum_smoothing_enabled)
    )
    smoothing_method = (
        result.get("spectrum_smoothing_method", settings.spectrum_smoothing_method)
        if smoothing_enabled
        else "none"
    )
    smoothing_window = (
        _positive_int_setting(settings.spectrum_smoothing_window)
        if smoothing_enabled
        else 0
    )
    return (
        ("sample_rate_hz", f"{sample_rate:g}"),
        ("filter_type", _safe_public_text(settings.filter_type)),
        ("filter_params", _safe_filter_parameters(settings.filter_params)),
        ("fft_window", _safe_public_text(settings.window_type)),
        ("baseline", _safe_public_text(baseline)),
        ("normalization", _safe_public_text(normalization)),
        ("spectrum_smoothing", "yes" if smoothing_enabled else "no"),
        ("spectrum_smoothing_method", _safe_public_text(smoothing_method)),
        ("spectrum_smoothing_window", str(smoothing_window)),
        ("peak_threshold", f"{_finite_setting(settings.peak_threshold):g}"),
        ("peak_prominence", f"{_finite_setting(settings.peak_prominence):g}"),
        ("peak_distance", str(_positive_int_setting(settings.peak_distance))),
        ("peak_min_snr", f"{_finite_setting(settings.peak_min_snr):g}"),
        ("data_type", _safe_public_text(settings.data_type)),
        (
            "peak_frequency_tolerance_hz",
            f"{_finite_setting(settings.peak_frequency_tolerance):g}",
        ),
    )


def _positive_finite_value(value: Any, *, fallback: Any) -> float:
    numeric_value = _finite_number(value)
    if numeric_value is not None and numeric_value > 0.0:
        return numeric_value
    fallback_value = _finite_number(fallback)
    if fallback_value is not None and fallback_value > 0.0:
        return fallback_value
    return 1.0


def _finite_setting(value: Any) -> float:
    numeric_value = _finite_number(value)
    return numeric_value if numeric_value is not None else 0.0


def _positive_int_setting(value: Any) -> int:
    try:
        numeric_value = int(value)
    except (TypeError, ValueError, OverflowError):
        return 1
    return max(1, numeric_value)


def _finite_number(value: Any) -> float | None:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    return numeric_value if math.isfinite(numeric_value) else None


def _safe_filter_parameters(value: Any) -> str:
    if not isinstance(value, dict):
        return "{}"
    public_parameters: dict[str, int | float | str | bool | None] = {}
    for key in sorted(PUBLIC_FILTER_PARAMETER_KEYS):
        if key not in value:
            continue
        parameter = value[key]
        if isinstance(parameter, int) and not isinstance(parameter, bool):
            public_parameters[key] = parameter
        elif isinstance(parameter, float):
            public_parameters[key] = parameter if math.isfinite(parameter) else None
    return json.dumps(public_parameters, sort_keys=True, separators=(",", ":"))


def _safe_public_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if "/" in text or "\\" in text:
        return "[redacted]"
    return text[:MAX_BATCH_PUBLIC_TEXT_CHARACTERS]
