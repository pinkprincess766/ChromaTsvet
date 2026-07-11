use crate::signal;
use crate::types::Peak;
use ndarray::Array1;

const DEFAULT_SAMPLE_RATE: f64 = 1.0;
const LEGACY_SAVGOL_WINDOW: usize = 11;
const LEGACY_SAVGOL_POLY_ORDER: usize = 3;
const LEGACY_MEDIAN_WINDOW: usize = 5;
const BASELINE_WINDOW_DIVISOR: usize = 20;
const MIN_BASELINE_WINDOW: usize = 5;

#[derive(Debug, Clone)]
pub(crate) struct ProcessSettings {
    pub sample_rate: f64,
    pub filter: FilterKind,
    pub window: WindowKind,
    pub baseline: BaselineSettings,
    pub normalize_area: bool,
    pub smoothing: SpectrumSmoothingSettings,
    pub peak_detection: signal::peak_detection::PeakDetectionSettings,
    warnings: Vec<ProcessingWarning>,
}

impl ProcessSettings {
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn from_python_args(
        sample_rate: f64,
        filter_type: &str,
        window_type: &str,
        threshold: f64,
        baseline: bool,
        baseline_method: &str,
        prominence: f64,
        distance: usize,
        normalize: bool,
        spectrum_smoothing: bool,
        spectrum_smoothing_method: &str,
        spectrum_smoothing_window: usize,
        min_snr: f64,
    ) -> Self {
        let (sample_rate, sample_rate_warning) = normalized_sample_rate(sample_rate);
        let (filter, filter_warning) = FilterKind::from_name(filter_type);
        let (window, window_warning) = WindowKind::from_name(window_type);
        let (baseline, baseline_warning) =
            BaselineSettings::from_python_args(baseline, baseline_method);
        let (smoothing, smoothing_warning) = SpectrumSmoothingSettings::from_python_args(
            spectrum_smoothing,
            spectrum_smoothing_method,
            spectrum_smoothing_window,
        );
        let mut warnings = Vec::new();
        warnings.extend(sample_rate_warning);
        warnings.extend(filter_warning);
        warnings.extend(window_warning);
        warnings.extend(baseline_warning);
        warnings.extend(smoothing_warning);

        Self {
            sample_rate,
            filter,
            window,
            baseline,
            normalize_area: normalize,
            smoothing,
            peak_detection: signal::peak_detection::PeakDetectionSettings::new(
                threshold, prominence, distance, min_snr,
            ),
            warnings,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ProcessingWarning {
    InvalidSampleRateFallback,
    UnknownFilterFallback,
    UnknownWindowFallback,
    UnknownBaselineFallback,
    UnknownSmoothingDisabled,
    ShortSignal,
    AreaNormalizationSkipped,
    NoPeaksDetected,
}

impl ProcessingWarning {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::InvalidSampleRateFallback => "invalid_sample_rate_fallback",
            Self::UnknownFilterFallback => "unknown_filter_fallback_none",
            Self::UnknownWindowFallback => "unknown_window_fallback_rectangular",
            Self::UnknownBaselineFallback => "unknown_baseline_method_fallback_improved",
            Self::UnknownSmoothingDisabled => "unknown_smoothing_method_disabled",
            Self::ShortSignal => "short_signal_no_peak_detection",
            Self::AreaNormalizationSkipped => "area_normalization_skipped",
            Self::NoPeaksDetected => "no_peaks_detected",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum FilterKind {
    None,
    Savgol,
    Median,
}

impl FilterKind {
    fn from_name(name: &str) -> (Self, Option<ProcessingWarning>) {
        match name.to_ascii_lowercase().as_str() {
            "savgol" => (Self::Savgol, None),
            "median" => (Self::Median, None),
            "none" | "" => (Self::None, None),
            _ => (Self::None, Some(ProcessingWarning::UnknownFilterFallback)),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum WindowKind {
    Rectangular,
    Hann,
    Hamming,
}

impl WindowKind {
    fn from_name(name: &str) -> (Self, Option<ProcessingWarning>) {
        match name.to_ascii_lowercase().as_str() {
            "hann" => (Self::Hann, None),
            "hamming" => (Self::Hamming, None),
            "rectangular" | "none" | "" => (Self::Rectangular, None),
            _ => (
                Self::Rectangular,
                Some(ProcessingWarning::UnknownWindowFallback),
            ),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Rectangular => "rectangular",
            Self::Hann => "hann",
            Self::Hamming => "hamming",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum BaselineMethod {
    None,
    Simple,
    Improved,
}

impl BaselineMethod {
    fn from_name(name: &str) -> (Self, Option<ProcessingWarning>) {
        match name.to_ascii_lowercase().as_str() {
            "none" => (Self::None, None),
            "simple" => (Self::Simple, None),
            "improved" | "" => (Self::Improved, None),
            _ => (
                Self::Improved,
                Some(ProcessingWarning::UnknownBaselineFallback),
            ),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Simple => "simple",
            Self::Improved => "improved",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct BaselineSettings {
    method: BaselineMethod,
}

impl BaselineSettings {
    fn from_python_args(enabled: bool, method_name: &str) -> (Self, Option<ProcessingWarning>) {
        let (method, warning) = if enabled {
            BaselineMethod::from_name(method_name)
        } else {
            (BaselineMethod::None, None)
        };

        (Self { method }, warning)
    }

    fn is_enabled(self) -> bool {
        self.method != BaselineMethod::None
    }

    pub(crate) fn method_name(self) -> &'static str {
        self.method.as_str()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SpectrumSmoothingMethod {
    None,
    Savgol,
    Median,
}

impl SpectrumSmoothingMethod {
    fn from_name(name: &str) -> (Self, Option<ProcessingWarning>) {
        match name.to_ascii_lowercase().as_str() {
            "savgol" => (Self::Savgol, None),
            "median" => (Self::Median, None),
            "none" | "" => (Self::None, None),
            _ => (
                Self::None,
                Some(ProcessingWarning::UnknownSmoothingDisabled),
            ),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Savgol => "savgol",
            Self::Median => "median",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct SpectrumSmoothingSettings {
    method: SpectrumSmoothingMethod,
    requested_window: usize,
}

impl SpectrumSmoothingSettings {
    fn from_python_args(
        enabled: bool,
        method_name: &str,
        requested_window: usize,
    ) -> (Self, Option<ProcessingWarning>) {
        let (method, warning) = if enabled {
            SpectrumSmoothingMethod::from_name(method_name)
        } else {
            (SpectrumSmoothingMethod::None, None)
        };

        (
            Self {
                method,
                requested_window,
            },
            warning,
        )
    }

    fn is_enabled(self) -> bool {
        self.method != SpectrumSmoothingMethod::None
    }

    fn method_name(self) -> &'static str {
        self.method.as_str()
    }
}

#[derive(Debug, Clone)]
pub(crate) struct ProcessOutput {
    pub spectrum: Array1<f64>,
    pub frequency_axis: Vec<f64>,
    pub peaks: Vec<Peak>,
    pub sample_rate: f64,
    pub baseline_corrected: bool,
    pub baseline_method: &'static str,
    pub spectrum_smoothed: bool,
    pub spectrum_smoothing_method: &'static str,
    pub spectrum_smoothing_window: usize,
    pub normalized: bool,
    pub normalization_area: f64,
    pub peak_threshold: f64,
    pub peak_prominence: f64,
    pub peak_distance: usize,
    pub peak_min_snr: f64,
    pub warnings: Vec<ProcessingWarning>,
}

pub(crate) fn process_signal_data(data: Vec<f64>, settings: ProcessSettings) -> ProcessOutput {
    let mut warnings = settings.warnings.clone();
    let signal = prepare_signal(data, settings.filter);
    let signal_len = signal.len();
    if signal_len < 3 {
        warnings.push(ProcessingWarning::ShortSignal);
    }

    let spectrum = compute_spectrum(&signal, settings.window);
    let baseline_output = apply_baseline_correction(&spectrum, settings.baseline);
    let smoothing_output = apply_spectrum_smoothing(&baseline_output.spectrum, settings.smoothing);
    let normalization_output =
        apply_area_normalization(&smoothing_output.spectrum, settings.normalize_area);
    if settings.normalize_area && !normalization_output.normalized {
        warnings.push(ProcessingWarning::AreaNormalizationSkipped);
    }

    let frequency_axis = signal::fft::compute_frequency_axis(
        normalization_output.spectrum.len(),
        signal_len,
        settings.sample_rate,
    );
    let peaks = detect_and_annotate_peaks(
        &normalization_output.spectrum,
        signal_len,
        settings.sample_rate,
        settings.peak_detection,
    );
    if peaks.is_empty() && signal_len >= 3 {
        warnings.push(ProcessingWarning::NoPeaksDetected);
    }

    ProcessOutput {
        spectrum: normalization_output.spectrum,
        frequency_axis,
        peaks,
        sample_rate: settings.sample_rate,
        baseline_corrected: baseline_output.applied,
        baseline_method: baseline_output.method_name,
        spectrum_smoothed: smoothing_output.applied,
        spectrum_smoothing_method: smoothing_output.method_name,
        spectrum_smoothing_window: smoothing_output.window_size,
        normalized: normalization_output.normalized,
        normalization_area: normalization_output.original_area,
        peak_threshold: settings.peak_detection.threshold_factor,
        peak_prominence: settings.peak_detection.min_prominence,
        peak_distance: settings.peak_detection.min_distance,
        peak_min_snr: settings.peak_detection.min_snr,
        warnings,
    }
}

fn prepare_signal(data: Vec<f64>, filter: FilterKind) -> Array1<f64> {
    // Every public boundary starts with sanitization; invalid floats must not
    // enter FFT or peak arithmetic disguised as rare user data.
    let signal = signal::filters::sanitize_signal(&Array1::from_vec(data));

    // The Python GUI applies the selected signal filter before calling Rust and
    // passes `filter_type = "none"`. This legacy branch preserves direct PyO3
    // calls without moving UI-owned filtering policy into Rust.
    match filter {
        FilterKind::Savgol => {
            signal::filters::savgol_filter(&signal, LEGACY_SAVGOL_WINDOW, LEGACY_SAVGOL_POLY_ORDER)
        }
        FilterKind::Median => signal::filters::median_filter(&signal, LEGACY_MEDIAN_WINDOW),
        FilterKind::None => signal,
    }
}

fn compute_spectrum(signal: &Array1<f64>, window: WindowKind) -> Array1<f64> {
    signal::fft::compute_magnitude_spectrum(signal, window.as_str())
}

fn apply_baseline_correction(spectrum: &Array1<f64>, settings: BaselineSettings) -> BaselineOutput {
    if !settings.is_enabled() {
        return BaselineOutput {
            spectrum: spectrum.to_owned(),
            applied: false,
            method_name: "none",
        };
    }

    let window_size = (spectrum.len() / BASELINE_WINDOW_DIVISOR).max(MIN_BASELINE_WINDOW);
    let baseline = match settings.method {
        BaselineMethod::Simple => signal::filters::estimate_baseline_simple(spectrum, window_size),
        BaselineMethod::Improved => signal::filters::estimate_baseline(spectrum, window_size),
        BaselineMethod::None => unreachable!("disabled baseline returned earlier"),
    };

    BaselineOutput {
        spectrum: spectrum - &baseline,
        applied: true,
        method_name: settings.method_name(),
    }
}

#[derive(Debug, Clone)]
struct BaselineOutput {
    spectrum: Array1<f64>,
    applied: bool,
    method_name: &'static str,
}

fn apply_spectrum_smoothing(
    spectrum: &Array1<f64>,
    settings: SpectrumSmoothingSettings,
) -> SpectrumSmoothingOutput {
    if !settings.is_enabled() {
        return SpectrumSmoothingOutput {
            spectrum: spectrum.to_owned(),
            applied: false,
            method_name: "none",
            window_size: 0,
        };
    }

    let (spectrum, applied, method_name, window_size) = signal::filters::smooth_spectrum(
        spectrum,
        settings.method_name(),
        settings.requested_window,
    );

    SpectrumSmoothingOutput {
        spectrum,
        applied,
        method_name,
        window_size,
    }
}

#[derive(Debug, Clone)]
struct SpectrumSmoothingOutput {
    spectrum: Array1<f64>,
    applied: bool,
    method_name: &'static str,
    window_size: usize,
}

fn apply_area_normalization(spectrum: &Array1<f64>, enabled: bool) -> NormalizationOutput {
    if !enabled {
        return NormalizationOutput {
            spectrum: spectrum.to_owned(),
            normalized: false,
            original_area: 0.0,
        };
    }

    // Area normalization is deliberately after baseline/smoothing and before
    // peak detection: comparisons should be driven by shape, not acquisition
    // intensity scale.
    let (spectrum, original_area) = signal::normalization::normalize_area(spectrum);
    NormalizationOutput {
        spectrum,
        normalized: original_area > 0.0,
        original_area,
    }
}

#[derive(Debug, Clone)]
struct NormalizationOutput {
    spectrum: Array1<f64>,
    normalized: bool,
    original_area: f64,
}

fn detect_and_annotate_peaks(
    spectrum: &Array1<f64>,
    signal_len: usize,
    sample_rate: f64,
    settings: signal::peak_detection::PeakDetectionSettings,
) -> Vec<Peak> {
    let mut peaks = signal::peak_detection::detect_peaks_with_criteria(spectrum, settings);
    let bin_width = if signal_len > 0 {
        sample_rate / signal_len as f64
    } else {
        0.0
    };

    for peak in peaks.iter_mut() {
        peak.frequency = peak.position * bin_width;
        peak.width_hz = peak.width * bin_width;
    }

    peaks
}

fn normalized_sample_rate(sample_rate: f64) -> (f64, Option<ProcessingWarning>) {
    if sample_rate.is_finite() && sample_rate > 0.0 {
        (sample_rate, None)
    } else {
        (
            DEFAULT_SAMPLE_RATE,
            Some(ProcessingWarning::InvalidSampleRateFallback),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn settings_normalize_untrusted_python_arguments() {
        let settings = ProcessSettings::from_python_args(
            f64::NAN,
            "unknown",
            "unknown",
            f64::NAN,
            false,
            "improved",
            f64::INFINITY,
            0,
            true,
            true,
            "unknown",
            6,
            f64::NEG_INFINITY,
        );

        assert_eq!(settings.sample_rate, DEFAULT_SAMPLE_RATE);
        assert_eq!(settings.filter, FilterKind::None);
        assert_eq!(settings.window, WindowKind::Rectangular);
        assert_eq!(settings.baseline.method, BaselineMethod::None);
        assert_eq!(settings.smoothing.method, SpectrumSmoothingMethod::None);
        assert!(settings
            .warnings
            .contains(&ProcessingWarning::InvalidSampleRateFallback));
        assert!(settings
            .warnings
            .contains(&ProcessingWarning::UnknownFilterFallback));
        assert!(settings
            .warnings
            .contains(&ProcessingWarning::UnknownWindowFallback));
        assert!(settings
            .warnings
            .contains(&ProcessingWarning::UnknownSmoothingDisabled));
    }

    #[test]
    fn pipeline_preserves_frequency_axis_contract() {
        let settings = ProcessSettings::from_python_args(
            400.0,
            "none",
            "rectangular",
            0.01,
            false,
            "none",
            0.0,
            0,
            false,
            false,
            "none",
            0,
            0.0,
        );

        let output = process_signal_data(vec![0.0, 1.0, 0.0, -1.0], settings);

        assert_eq!(output.frequency_axis, vec![0.0, 100.0, 200.0]);
        assert_eq!(output.frequency_axis.len(), output.spectrum.len());
    }

    #[test]
    fn pipeline_returns_only_finite_numerical_outputs_for_hostile_input() {
        let settings = ProcessSettings::from_python_args(
            f64::INFINITY,
            "median",
            "hann",
            f64::NAN,
            true,
            "improved",
            f64::NAN,
            0,
            true,
            true,
            "median",
            4,
            f64::NAN,
        );

        let output = process_signal_data(
            vec![0.0, f64::NAN, 1.0, f64::INFINITY, f64::NEG_INFINITY, 0.0],
            settings,
        );

        assert!(output.spectrum.iter().all(|value| value.is_finite()));
        assert!(output.frequency_axis.iter().all(|value| value.is_finite()));
        assert!(output.peaks.iter().all(|peak| {
            peak.position.is_finite()
                && peak.frequency.is_finite()
                && peak.intensity.is_finite()
                && peak.width.is_finite()
                && peak.width_hz.is_finite()
                && peak.area.is_finite()
                && peak.snr.is_finite()
        }));
    }

    #[test]
    fn pipeline_reports_area_normalization_and_peak_absence_warnings() {
        let settings = ProcessSettings::from_python_args(
            100.0,
            "none",
            "rectangular",
            0.01,
            false,
            "none",
            0.0,
            0,
            true,
            false,
            "none",
            0,
            0.0,
        );

        let output = process_signal_data(vec![0.0, 0.0, 0.0, 0.0], settings);

        assert!(output
            .warnings
            .contains(&ProcessingWarning::AreaNormalizationSkipped));
        assert!(output
            .warnings
            .contains(&ProcessingWarning::NoPeaksDetected));
    }
}
