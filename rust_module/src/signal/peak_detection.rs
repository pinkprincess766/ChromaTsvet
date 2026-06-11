use crate::types::Peak;
use ndarray::prelude::*;

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
    let min_prominence = if threshold_factor <= 1.0 {
        // Treat small thresholds as a soft fraction of the range. The 0.5
        // factor keeps the detector usable on short or baseline-corrected
        // spectra where prominence can be compressed.
        dynamic_range * threshold_factor.max(0.0) * 0.5
    } else {
        noise * threshold_factor * 0.5
    };
    let automatic_prominence = min_prominence
        .max(dynamic_range * 0.01)
        .min(dynamic_range * 0.25);
    let requested_prominence = if requested_prominence.is_finite() {
        requested_prominence.max(0.0)
    } else {
        0.0
    };
    let min_prominence = automatic_prominence.max(requested_prominence);
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
    let half_height = baseline_level + candidate.prominence * 0.5;
    let left = half_height_crossing(signal, candidate.index, half_height, true);
    let right = half_height_crossing(signal, candidate.index, half_height, false);
    let area = integrate_peak(signal, left, right, baseline_level);

    Peak {
        position: candidate.index as f64,
        intensity: candidate.intensity,
        width: (right as f64 - left as f64).max(1.0),
        area,
        snr: candidate.prominence / noise,
    }
}

fn half_height_crossing(
    signal: &Array1<f64>,
    peak_idx: usize,
    half_height: f64,
    scan_left: bool,
) -> usize {
    if scan_left {
        for i in (0..peak_idx).rev() {
            if !signal[i].is_finite() || signal[i] <= half_height {
                return i;
            }
        }
        0
    } else {
        for i in peak_idx + 1..signal.len() {
            if !signal[i].is_finite() || signal[i] <= half_height {
                return i;
            }
        }
        signal.len() - 1
    }
}

fn integrate_peak(signal: &Array1<f64>, left: usize, right: usize, baseline_level: f64) -> f64 {
    if right <= left {
        return 0.0;
    }

    let mut area = 0.0;
    for i in left..=right {
        let value = signal[i];
        if value.is_finite() {
            area += (value - baseline_level).max(0.0);
        }
    }

    area
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
    fn test_requested_distance_suppresses_nearby_peaks() {
        let data = array![0.0, 3.0, 0.0, 2.5, 0.0];
        let peaks = detect_peaks_with_settings(&data, 0.05, 0.0, 4);

        assert_eq!(peaks.len(), 1);
        assert_eq!(peaks[0].position, 1.0);
    }
}
