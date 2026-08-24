"""Sequential, headless batch analysis for spectrum files."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from python_analyzer.analysis import filters
from python_analyzer.analysis.models import AnalysisSettings
from python_analyzer.analysis.peak_review import PEAK_REVIEW_ACCEPTED
from python_analyzer.analysis.runner import SignalProcessor
from python_analyzer.analysis.workflow import run_analysis_workflow
from python_analyzer.readers import SpectrumFileFormatError, read_spectrum_file


MAX_BATCH_FILES = 100
MAX_BATCH_FILE_SIZE_BYTES = 128 * 1024 * 1024
MAX_SOURCE_NAME_CHARACTERS = 255
SUPPORTED_SPECTRUM_SUFFIXES = frozenset({".csv", ".txt"})

BATCH_STATUS_SUCCESS = "success"
BATCH_STATUS_FAILED = "failed"


class BatchSelectionError(ValueError):
    """Raised when the selected batch cannot be processed safely."""


@dataclass(frozen=True)
class BatchAnalysisItem:
    """Compact result for one input file, without private path data."""

    source_name: str
    status: str
    point_count: int = 0
    peak_count: int = 0
    warning_count: int = 0
    skipped_row_count: int = 0
    error_message: str = ""


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
        )
        items.append(item)
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
) -> BatchAnalysisItem:
    source_name = _safe_source_name(path)
    try:
        _validate_input_file(path, max_file_size_bytes=max_file_size_bytes)
        signal, skipped_rows = read_spectrum_file(path)
        if not signal:
            raise SpectrumFileFormatError("No numeric spectrum values were found.")
        outcome = run_analysis_workflow(signal, settings, processor=processor)
        return BatchAnalysisItem(
            source_name=source_name,
            status=BATCH_STATUS_SUCCESS,
            point_count=len(signal),
            peak_count=len(outcome.peaks),
            warning_count=_warning_count(outcome.result, outcome.peak_reviews),
            skipped_row_count=len(skipped_rows),
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
