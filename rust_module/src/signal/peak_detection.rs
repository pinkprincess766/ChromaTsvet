use crate::types::Peak;
use ndarray::prelude::*;

const GAUSSIAN_AREA_FACTOR: f64 = 1.0645;
const FALLBACK_HALF_WINDOW: usize = 3;

struct PeakCandidate {
    index: usize,
    intensity: f64,
    prominence: f64,
    is_global_max: bool,
}

pub fn detect_peaks_adaptive(signal: &Array1<f64>, threshold_factor: f64) -> Vec<Peak> {
    detect_peaks_with_settings(signal, threshold_factor, 0.0, 0)
}

pub fn detect_peaks_with_settings(
    signal: &Array1<f64>,
    threshold_factor: f64,
    requested_prominence: f64,
    requested_distance: usize,
) -> Vec<Peak> {
    if signal.len() < 3 {
        return vec![];
    }

    // Peak math assumes an ordered finite signal; repair invalid samples first.
    let cleaned = super::filters::sanitize_signal(signal);
    let signal = &cleaned;
    let finite_values: Vec<f64> = signal.iter().copied().filter(|v| v.is_finite()).collect();
    if finite_values.len() < 3 {
        return vec![];
    }

    let min_value = finite_values
        .iter()
        .copied()
        .min_by(|a, b| a.total_cmp(b))
        .unwrap_or(0.0);
    let max_value = finite_values
        .iter()
        .copied()
        .max_by(|a, b| a.total_cmp(b))
        .unwrap_or(0.0);
    let dynamic_range = (max_value - min_value).max(0.0);
    if dynamic_range <= f64::EPSILON {
        return vec![];
    }

    let (global_idx, global_value) = signal
        .iter()
        .enumerate()
        .filter(|(_, value)| value.is_finite())
        .max_by(|(_, a), (_, b)| a.total_cmp(b))
        .map(|(i, value)| (i, *value))
        .unwrap();

    let mean = finite_values.iter().sum::<f64>() / finite_values.len() as f64;
    let noise = estimate_noise(&finite_values, mean);
    let threshold_factor = if threshold_factor.is_finite() {
        threshold_factor.max(0.0)
    } else {
        0.0
    };
    let requested_prominence = if requested_prominence.is_finite() {
        requested_prominence.max(0.0)
    } else {
        0.0
    };
    // `threshold_factor` is a sensitivity coefficient for the noise estimate:
    // smaller values admit more peaks, while larger values require more prominence.
    // An explicitly requested prominence replaces this automatic threshold.
    let min_prominence = if requested_prominence > 0.0 {
        requested_prominence
    } else {
        noise * threshold_factor
    };
    let min_distance = if requested_distance == 0 {
        (signal.len() / 500).max(1)
    } else {
        requested_distance
    };

    let mut candidates = Vec::new();
    for i in 1..signal.len() - 1 {
        let prev = signal[i - 1];
        let current = signal[i];
        let next = signal[i + 1];

        if !(prev.is_finite() && current.is_finite() && next.is_finite()) {
            continue;
        }

        if current <= prev || current <= next {
            continue;
        }

        let prominence = estimate_prominence(signal, i);
        if prominence >= min_prominence {
            candidates.push(PeakCandidate {
                index: i,
                intensity: current,
                prominence,
                is_global_max: i == global_idx,
            });
        }
    }

    if !candidates.iter().any(|peak| peak.index == global_idx) {
        candidates.push(PeakCandidate {
            index: global_idx,
            intensity: global_value,
            prominence: estimate_prominence(signal, global_idx).max(dynamic_range),
            is_global_max: true,
        });
    }

    candidates.sort_by(|a, b| {
        b.is_global_max
            .cmp(&a.is_global_max)
            .then_with(|| b.intensity.total_cmp(&a.intensity))
    });

    let mut selected: Vec<PeakCandidate> = Vec::new();
    for candidate in candidates {
        let too_close = selected.iter().any(|peak| {
            peak.index.abs_diff(candidate.index) < min_distance && !candidate.is_global_max
        });

        if !too_close {
            selected.push(candidate);
        }
    }

    if selected.is_empty() {
        selected.push(PeakCandidate {
            index: global_idx,
            intensity: global_value,
            prominence: estimate_prominence(signal, global_idx).max(dynamic_range),
            is_global_max: true,
        });
    }

    selected.sort_by_key(|peak| peak.index);
    selected
        .into_iter()
        .map(|candidate| build_peak(signal, candidate, noise))
        .collect()
}

fn estimate_noise(values: &[f64], mean: f64) -> f64 {
    if values.len() < 2 {
        return 1e-8;
    }

    let variance = values
        .iter()
        .map(|value| {
            let delta = value - mean;
            delta * delta
        })
        .sum::<f64>()
        / values.len() as f64;

    variance.sqrt().max(1e-8)
}

fn estimate_prominence(signal: &Array1<f64>, peak_idx: usize) -> f64 {
    let peak_value = signal[peak_idx];
    let left_min = scan_min_until_higher(signal, peak_idx, true, peak_value);
    let right_min = scan_min_until_higher(signal, peak_idx, false, peak_value);
    peak_value - left_min.max(right_min)
}

fn scan_min_until_higher(
    signal: &Array1<f64>,
    peak_idx: usize,
    scan_left: bool,
    peak_value: f64,
) -> f64 {
    let mut min_value = peak_value;

    if scan_left {
        for i in (0..peak_idx).rev() {
            let value = signal[i];
            if !value.is_finite() {
                break;
            }
            if value > peak_value {
                break;
            }
            min_value = min_value.min(value);
        }
    } else {
        for i in peak_idx + 1..signal.len() {
            let value = signal[i];
            if !value.is_finite() {
                break;
            }
            if value > peak_value {
                break;
            }
            min_value = min_value.min(value);
        }
    }

    min_value
}

fn build_peak(signal: &Array1<f64>, candidate: PeakCandidate, noise: f64) -> Peak {
    let baseline_level = candidate.intensity - candidate.prominence;
    let peak_height = candidate.intensity - baseline_level;
    let half_height = baseline_level + candidate.prominence * 0.5;
    let left = half_height_crossing(signal, candidate.index, half_height, true);
    let right = half_height_crossing(signal, candidate.index, half_height, false);
    let width = match (left, right) {
        (Some(left), Some(right)) if right > left => right - left,
        _ => 0.0,
    };

    let (integration_left, integration_right) =
        integration_bounds(signal.len(), candidate.index, left, right);
    let numeric_area =
        integrate_peak_trapezoidal(signal, integration_left, integration_right, baseline_level);
    let area = gaussian_peak_area(peak_height, width).unwrap_or(numeric_area);

    Peak {
        position: candidate.index as f64,
        frequency: 0.0,
        intensity: candidate.intensity,
        width,
        width_hz: 0.0,
        area,
        snr: candidate.prominence / noise,
    }
}

fn half_height_crossing(
    signal: &Array1<f64>,
    peak_idx: usize,
    half_height: f64,
    scan_left: bool,
) -> Option<f64> {
    if scan_left {
        for i in (1..=peak_idx).rev() {
            let left = signal[i - 1];
            let right = signal[i];
            if !(left.is_finite() && right.is_finite()) {
                return None;
            }
            if left <= half_height && right >= half_height {
                return interpolate_crossing(i - 1, left, i, right, half_height);
            }
        }
        (signal[0] <= half_height).then_some(0.0)
    } else {
        for i in peak_idx..signal.len().saturating_sub(1) {
            let left = signal[i];
            let right = signal[i + 1];
            if !(left.is_finite() && right.is_finite()) {
                return None;
            }
            if left >= half_height && right <= half_height {
                return interpolate_crossing(i, left, i + 1, right, half_height);
            }
        }
        let last_index = signal.len().saturating_sub(1);
        (signal[last_index] <= half_height).then_some(last_index as f64)
    }
}

fn interpolate_crossing(
    left_index: usize,
    left_value: f64,
    right_index: usize,
    right_value: f64,
    target: f64,
) -> Option<f64> {
    let delta = right_value - left_value;
    if !delta.is_finite() || delta.abs() <= f64::EPSILON {
        return Some(left_index as f64);
    }

    let fraction = ((target - left_value) / delta).clamp(0.0, 1.0);
    Some(left_index as f64 + fraction * (right_index - left_index) as f64)
}

fn gaussian_peak_area(height: f64, width: f64) -> Option<f64> {
    if height.is_finite() && width.is_finite() && height > 0.0 && width > 0.0 {
        Some(height * width * GAUSSIAN_AREA_FACTOR)
    } else {
        None
    }
}

fn integration_bounds(
    signal_len: usize,
    peak_idx: usize,
    left: Option<f64>,
    right: Option<f64>,
) -> (usize, usize) {
    if signal_len == 0 {
        return (0, 0);
    }

    if let (Some(left), Some(right)) = (left, right) {
        if right > left {
            let left_index = left.floor().max(0.0) as usize;
            let right_index = right.ceil().min((signal_len - 1) as f64) as usize;
            return (left_index, right_index.max(left_index));
        }
    }

    let half_window = (signal_len / 100)
        .max(FALLBACK_HALF_WINDOW)
        .min(25)
        .min(signal_len.saturating_sub(1));
    let left_index = peak_idx.saturating_sub(half_window);
    let right_index = peak_idx.saturating_add(half_window).min(signal_len - 1);
    (left_index, right_index)
}

fn integrate_peak_trapezoidal(
    signal: &Array1<f64>,
    left: usize,
    right: usize,
    baseline_level: f64,
) -> f64 {
    if right <= left {
        return 0.0;
    }

    let mut area = 0.0;
    for i in left..right {
        let current = baseline_corrected_value(signal[i], baseline_level);
        let next = baseline_corrected_value(signal[i + 1], baseline_level);
        area += (current + next) * 0.5;
    }

    if area.is_finite() {
        area.max(0.0)
    } else {
        0.0
    }
}

fn baseline_corrected_value(value: f64, baseline_level: f64) -> f64 {
    if value.is_finite() {
        (value - baseline_level).max(0.0)
    } else {
        0.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_peak_detection_populates_shape_metrics() {
        let data = array![0.0, 0.2, 1.0, 3.0, 1.0, 0.2, 0.0];
        let peaks = detect_peaks_adaptive(&data, 0.1);

        assert_eq!(peaks.len(), 1);
        assert_eq!(peaks[0].position, 3.0);
        assert!(peaks[0].width > 0.0);
        assert!(peaks[0].area > 0.0);
        assert!(peaks[0].snr > 0.0);
    }

    #[test]
    fn test_peak_area_uses_gaussian_fwhm_approximation() {
        let data = array![0.0, 0.5, 1.0, 0.5, 0.0];
        let peaks = detect_peaks_adaptive(&data, 0.1);

        assert_eq!(peaks.len(), 1);
        assert!((peaks[0].width - 2.0).abs() < 1e-12);
        assert!((peaks[0].area - (1.0 * 2.0 * GAUSSIAN_AREA_FACTOR)).abs() < 1e-12);
    }

    #[test]
    fn test_gaussian_peak_area_rejects_non_positive_shape() {
        assert!(gaussian_peak_area(1.0, 0.0).is_none());
        assert!(gaussian_peak_area(1.0, -1.0).is_none());
        assert!(gaussian_peak_area(0.0, 1.0).is_none());
        assert!(gaussian_peak_area(f64::NAN, 1.0).is_none());
    }

    #[test]
    fn test_gaussian_peak_area_handles_tiny_positive_width() {
        let area = gaussian_peak_area(2.0, f64::MIN_POSITIVE).unwrap();

        assert!(area.is_finite());
        assert!(area > 0.0);
    }

    #[test]
    fn test_peak_area_falls_back_to_trapezoid_when_width_is_unknown() {
        let data = array![5.0, 2.0, 1.0, 0.0];
        let peaks = detect_peaks_adaptive(&data, 0.1);

        assert_eq!(peaks.len(), 1);
        assert_eq!(peaks[0].position, 0.0);
        assert_eq!(peaks[0].width, 0.0);
        assert!(peaks[0].area > 0.0);
    }

    #[test]
    fn test_peak_detection_ignores_invalid_signal() {
        let data = array![f64::NAN, f64::INFINITY, f64::NEG_INFINITY];
        let peaks = detect_peaks_adaptive(&data, 0.1);
        assert!(peaks.is_empty());
    }

    #[test]
    fn test_peak_detection_keeps_global_maximum_as_fallback() {
        let data = array![0.1, 0.3, 0.8, 2.5, 9.0, 22.0, 8.5, 3.0, 1.2, 0.4, 0.2];
        let peaks = detect_peaks_adaptive(&data, 10_000.0);

        assert_eq!(peaks.len(), 1);
        assert_eq!(peaks[0].position, 5.0);
        assert!(peaks[0].width > 0.0);
        assert!(peaks[0].area > 0.0);
        assert!(peaks[0].snr > 0.0);
    }

    #[test]
    fn test_requested_prominence_filters_smaller_peaks() {
        let data = array![0.0, 3.0, 0.0, 0.0, 2.0, 0.0];
        let peaks = detect_peaks_with_settings(&data, 0.05, 2.5, 1);

        assert_eq!(peaks.len(), 1);
        assert_eq!(peaks[0].position, 1.0);
    }

    #[test]
    fn test_requested_prominence_replaces_automatic_threshold() {
        let data = array![0.0, 3.0, 0.0, 0.0, 2.0, 0.0];

        let peaks = detect_peaks_with_settings(&data, 100.0, 1.5, 1);

        assert_eq!(peaks.len(), 2);
    }

    #[test]
    fn test_lower_threshold_finds_more_peaks() {
        let data = array![0.0, 1.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.6, 0.0];

        let soft = detect_peaks_with_settings(&data, 0.05, 0.0, 1);
        let strict = detect_peaks_with_settings(&data, 2.0, 0.0, 1);

        assert!(soft.len() > strict.len());
        assert_eq!(strict.len(), 1);
    }

    #[test]
    fn test_requested_distance_suppresses_nearby_peaks() {
        let data = array![0.0, 3.0, 0.0, 2.5, 0.0];
        let peaks = detect_peaks_with_settings(&data, 0.05, 0.0, 4);

        assert_eq!(peaks.len(), 1);
        assert_eq!(peaks[0].position, 1.0);
    }

    #[test]
    fn test_peak_detection_sanitizes_mixed_invalid_values() {
        let data = array![0.0, f64::NAN, 1.0, f64::INFINITY, 0.0];
        let peaks = detect_peaks_adaptive(&data, 0.05);

        assert!(peaks.iter().all(|peak| {
            peak.position.is_finite()
                && peak.intensity.is_finite()
                && peak.width.is_finite()
                && peak.area.is_finite()
                && peak.snr.is_finite()
        }));
    }

    #[test]
    fn test_peak_detection_handles_short_signals() {
        assert!(detect_peaks_adaptive(&Array1::zeros(0), 0.1).is_empty());
        assert!(detect_peaks_adaptive(&array![1.0], 0.1).is_empty());
        assert!(detect_peaks_adaptive(&array![1.0, 2.0], 0.1).is_empty());
    }
}
