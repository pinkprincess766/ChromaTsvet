//! High-performance signal filters (Carmack/Torvalds style)
//! Median and Savitzky-Golay filters

use medians::Medianf64;
use ndarray::prelude::*;

pub const DEFAULT_SPECTRUM_SMOOTHING_METHOD: &str = "savgol";
pub const DEFAULT_SPECTRUM_SMOOTHING_WINDOW: usize = 7;
const SPECTRUM_SAVGOL_POLY_ORDER: usize = 3;

/// Replaces non-finite samples so downstream FFT and filter code stays finite.
pub(crate) fn sanitize_signal(signal: &Array1<f64>) -> Array1<f64> {
    let mut cleaned = signal.to_owned();
    let mut previous_finite = None;

    for value in cleaned.iter_mut() {
        // Beware of bugs in the above code; I have only proved it correct, not tried it.
        if value.is_finite() {
            previous_finite = Some(*value);
        } else if let Some(previous) = previous_finite {
            *value = previous;
        }
    }

    let mut next_finite = None;
    for value in cleaned.iter_mut().rev() {
        if value.is_finite() {
            next_finite = Some(*value);
        } else {
            *value = next_finite.unwrap_or(0.0);
        }
    }

    cleaned
}

/// Медианный фильтр — отлично убирает импульсные помехи, сохраняя края сигнала
pub fn median_filter(signal: &Array1<f64>, window_size: usize) -> Array1<f64> {
    let cleaned = sanitize_signal(signal);
    let n = cleaned.len();
    if n < 3 {
        return cleaned;
    }
    if window_size < 3 || window_size % 2 == 0 {
        return cleaned;
    }

    let window_size = normalized_window_size(window_size, n);
    let mut filtered = Array1::<f64>::zeros(n);
    let half = window_size / 2;

    for i in 0..n {
        let start = i.saturating_sub(half);
        let end = (i + half + 1).min(n);
        let window = cleaned.slice(s![start..end]);
        let mut w: Vec<f64> = window.to_vec();
        w.sort_by(|a, b| a.total_cmp(b));
        let mid = w.len() / 2;
        filtered[i] = w[mid];
    }
    filtered
}

/// Estimates a slowly varying baseline while remaining resistant to sharp peaks.
pub fn estimate_baseline(signal: &Array1<f64>, window_size: usize) -> Array1<f64> {
    let cleaned = sanitize_signal(signal);
    let n = cleaned.len();
    if n == 0 {
        return Array1::zeros(0);
    }
    if n < 3 {
        return cleaned;
    }
    if n < 5 {
        return estimate_baseline_simple(&cleaned, window_size);
    }

    let window_size = normalized_window_size(window_size, n);
    let smooth_window = normalized_window_size(5, n);

    let first_baseline = estimate_baseline_simple(&cleaned, window_size);

    // A residual pass compensates for slow local bias left by the first
    // rolling minimum. On a well-estimated background this correction is near zero.
    let residual = Array1::from_iter(
        cleaned
            .iter()
            .zip(first_baseline.iter())
            .map(|(&value, &baseline)| value - baseline),
    );
    let residual_floor = rolling_minimum(&residual, window_size);
    let correction = median_smooth(&residual_floor, smooth_window);

    let mut baseline = &first_baseline + &correction;
    for i in 0..n {
        baseline[i] = baseline[i].min(cleaned[i]);
    }

    baseline
}

/// Estimates the baseline using a single lower-envelope smoothing pass.
pub fn estimate_baseline_simple(signal: &Array1<f64>, window_size: usize) -> Array1<f64> {
    let cleaned = sanitize_signal(signal);
    let n = cleaned.len();
    if n == 0 {
        return Array1::zeros(0);
    }
    if n < 3 {
        return cleaned;
    }

    let window_size = normalized_window_size(window_size, n);
    let smooth_window = normalized_window_size(5, n);

    // The rolling minimum follows the lower envelope; median smoothing
    // removes its staircase pattern without pulling it toward sharp peaks.
    let lower_envelope = rolling_minimum(&cleaned, window_size);
    median_smooth(&lower_envelope, smooth_window)
}

fn normalized_window_size(requested: usize, signal_len: usize) -> usize {
    if signal_len < 3 {
        return signal_len;
    }

    let automatic = (signal_len / 15).max(5);
    let requested = if requested < 3 { automatic } else { requested };
    let max_odd = if signal_len % 2 == 0 {
        signal_len.saturating_sub(1)
    } else {
        signal_len
    };

    let mut window = requested.max(3).min(max_odd.max(3));
    if window % 2 == 0 {
        window -= 1;
    }
    window.max(3)
}

fn rolling_minimum(signal: &Array1<f64>, window_size: usize) -> Array1<f64> {
    let cleaned = sanitize_signal(signal);
    let n = cleaned.len();
    if n == 0 {
        return Array1::zeros(0);
    }
    if n < 3 {
        return cleaned;
    }

    let window_size = normalized_window_size(window_size, n);
    let half = window_size / 2;
    let mut result = Array1::<f64>::zeros(n);

    for i in 0..n {
        let start = i.saturating_sub(half);
        let end = (i + half + 1).min(n);
        result[i] = cleaned
            .slice(s![start..end])
            .iter()
            .copied()
            .min_by(|a, b| a.total_cmp(b))
            .unwrap_or(0.0);
    }

    result
}

fn median_smooth(signal: &Array1<f64>, window_size: usize) -> Array1<f64> {
    let cleaned = sanitize_signal(signal);
    let n = cleaned.len();
    if n == 0 {
        return Array1::zeros(0);
    }
    if n < 3 {
        return cleaned;
    }

    let window_size = normalized_window_size(window_size, n);
    let half = window_size / 2;
    let mut result = Array1::<f64>::zeros(n);

    for i in 0..n {
        let start = i.saturating_sub(half);
        let end = (i + half + 1).min(n);
        let values: Vec<f64> = cleaned.slice(s![start..end]).iter().copied().collect();

        result[i] = values.as_slice().medf_checked().unwrap_or(0.0);
    }

    result
}

/// Smooth a processed spectrum before normalization and peak detection.
pub fn smooth_spectrum(
    signal: &Array1<f64>,
    method: &str,
    window_size: usize,
) -> (Array1<f64>, bool, &'static str, usize) {
    let cleaned = sanitize_signal(signal);
    let n = cleaned.len();
    if n < 5 {
        return (cleaned, false, "none", 0);
    }

    let method = method.trim().to_lowercase();
    if method == "none" {
        return (cleaned, false, "none", 0);
    }

    let normalized_window = normalized_window_size(
        if window_size == 0 {
            DEFAULT_SPECTRUM_SMOOTHING_WINDOW
        } else {
            window_size
        },
        n,
    );

    match method.as_str() {
        DEFAULT_SPECTRUM_SMOOTHING_METHOD | "savitzky-golay" | "savitzky_golay" => {
            let poly_order = SPECTRUM_SAVGOL_POLY_ORDER.min(normalized_window - 1);
            let smoothed = savgol_filter(&cleaned, normalized_window, poly_order);
            (
                smoothed,
                true,
                DEFAULT_SPECTRUM_SMOOTHING_METHOD,
                normalized_window,
            )
        }
        "median" => (
            median_filter(&cleaned, normalized_window),
            true,
            "median",
            normalized_window,
        ),
        _ => (cleaned, false, "none", 0),
    }
}

/// Smooths a signal by fitting a local polynomial in each window.
pub fn savgol_filter(signal: &Array1<f64>, window_size: usize, poly_order: usize) -> Array1<f64> {
    let cleaned = sanitize_signal(signal);
    let n = cleaned.len();

    let Some(window_size) = normalize_savgol_window(window_size, n) else {
        return cleaned;
    };
    if poly_order >= window_size {
        return cleaned;
    }

    let mut weights_by_position = Vec::with_capacity(window_size);
    for evaluation_index in 0..window_size {
        let Some(weights) = savgol_weights(window_size, poly_order, evaluation_index) else {
            return cleaned;
        };
        weights_by_position.push(weights);
    }

    let half = window_size / 2;
    let last_start = n - window_size;
    let mut filtered = Array1::<f64>::zeros(n);

    for i in 0..n {
        let start = i.saturating_sub(half).min(last_start);
        let evaluation_index = i - start;
        filtered[i] = weights_by_position[evaluation_index]
            .iter()
            .zip(cleaned.slice(s![start..start + window_size]).iter())
            .map(|(weight, value)| weight * value)
            .sum();

        if !filtered[i].is_finite() {
            return cleaned;
        }
    }

    filtered
}

fn normalize_savgol_window(requested: usize, signal_len: usize) -> Option<usize> {
    if requested < 3 || requested > signal_len {
        return None;
    }

    if requested % 2 == 1 {
        return Some(requested);
    }

    if requested < signal_len {
        requested.checked_add(1)
    } else {
        requested.checked_sub(1).filter(|window| *window >= 3)
    }
}

fn savgol_weights(
    window_size: usize,
    poly_order: usize,
    evaluation_index: usize,
) -> Option<Vec<f64>> {
    let matrix_size = poly_order.checked_add(1)?;
    let powers_len = poly_order.checked_mul(2)?.checked_add(1)?;
    let scale = evaluation_index
        .max(window_size - 1 - evaluation_index)
        .max(1) as f64;
    let mut normal_matrix = vec![vec![0.0; matrix_size]; matrix_size];

    for sample_index in 0..window_size {
        let x = (sample_index as f64 - evaluation_index as f64) / scale;
        let mut powers = vec![1.0; powers_len];
        for power in 1..powers_len {
            powers[power] = powers[power - 1] * x;
        }

        for row in 0..matrix_size {
            for column in 0..matrix_size {
                normal_matrix[row][column] += powers[row + column];
            }
        }
    }

    let mut evaluation = vec![0.0; matrix_size];
    evaluation[0] = 1.0;
    let polynomial_coefficients = solve_linear_system(normal_matrix, evaluation)?;

    let mut weights = Vec::with_capacity(window_size);
    for sample_index in 0..window_size {
        let x = (sample_index as f64 - evaluation_index as f64) / scale;
        let mut power = 1.0;
        let mut weight = 0.0;
        for coefficient in &polynomial_coefficients {
            weight += coefficient * power;
            power *= x;
        }
        weights.push(weight);
    }

    weights
        .iter()
        .all(|weight| weight.is_finite())
        .then_some(weights)
}

fn solve_linear_system(mut matrix: Vec<Vec<f64>>, mut rhs: Vec<f64>) -> Option<Vec<f64>> {
    let size = rhs.len();

    for column in 0..size {
        let pivot_row = (column..size)
            .max_by(|&a, &b| matrix[a][column].abs().total_cmp(&matrix[b][column].abs()))?;
        let pivot = matrix[pivot_row][column];
        if !pivot.is_finite() || pivot.abs() <= 1e-12 {
            return None;
        }

        matrix.swap(column, pivot_row);
        rhs.swap(column, pivot_row);

        let pivot = matrix[column][column];
        for value in &mut matrix[column][column..] {
            *value /= pivot;
        }
        rhs[column] /= pivot;

        for row in 0..size {
            if row == column {
                continue;
            }

            let factor = matrix[row][column];
            for current_column in column..size {
                matrix[row][current_column] -= factor * matrix[column][current_column];
            }
            rhs[row] -= factor * rhs[column];
        }
    }

    rhs.iter().all(|value| value.is_finite()).then_some(rhs)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_median_filter() {
        let data = array![1.0, 2.0, 100.0, 3.0, 4.0];
        let filtered = median_filter(&data, 3);
        assert!(filtered[2] < 10.0); // выброс 100 должен быть сглажен
        println!("Median filter test passed: {:?}", filtered);
    }

    #[test]
    fn test_estimate_baseline_tracks_background() {
        let mut data = Array1::from_iter((0..31).map(|i| 1.0 + i as f64 * 0.05));
        data[8] += 5.0;
        data[9] += 2.0;
        data[21] += 7.0;

        let baseline = estimate_baseline(&data, 7);
        assert_eq!(baseline.len(), data.len());
        assert!(baseline.iter().all(|v| v.is_finite()));
        assert!(baseline[8] < data[8] - 3.0);
        assert!(baseline[21] < data[21] - 5.0);
        assert!((baseline[15] - 1.75).abs() < 0.35);
        assert!(baseline
            .iter()
            .zip(data.iter())
            .all(|(baseline, signal)| baseline <= signal));
    }

    #[test]
    fn test_simple_baseline_ignores_sharp_peaks() {
        let data = array![1.0, 1.1, 1.2, 8.0, 1.4, 1.5, 1.6];
        let baseline = estimate_baseline_simple(&data, 5);

        assert_eq!(baseline.len(), data.len());
        assert!(baseline[3] < 2.0);
        assert!(baseline.iter().all(|value| value.is_finite()));
    }

    #[test]
    fn test_filters_sanitize_non_finite_values() {
        let data = array![f64::NAN, 1.0, f64::INFINITY, 3.0, f64::NEG_INFINITY];

        let median = median_filter(&data, 9);
        let baseline = estimate_baseline(&data, 9);

        assert_eq!(median.len(), data.len());
        assert_eq!(baseline.len(), data.len());
        assert!(median.iter().all(|value| value.is_finite()));
        assert!(baseline.iter().all(|value| value.is_finite()));
    }

    #[test]
    fn test_filters_handle_empty_and_short_signals() {
        let empty = Array1::<f64>::zeros(0);
        let short = array![f64::NAN, 2.0];

        assert!(median_filter(&empty, 5).is_empty());
        assert!(estimate_baseline(&empty, 5).is_empty());
        assert_eq!(median_filter(&short, 5).to_vec(), vec![2.0, 2.0]);
        assert_eq!(estimate_baseline_simple(&short, 5).to_vec(), vec![2.0, 2.0]);
    }

    #[test]
    fn test_savgol_returns_sanitized_short_signal() {
        let data = array![f64::NAN, 2.0, 3.0];

        let filtered = savgol_filter(&data, 5, 2);

        assert_eq!(filtered.to_vec(), vec![2.0, 2.0, 3.0]);
    }

    #[test]
    fn test_savgol_sanitizes_non_finite_values() {
        let data = array![
            f64::NAN,
            1.0,
            2.0,
            f64::INFINITY,
            4.0,
            5.0,
            f64::NEG_INFINITY,
            7.0,
            8.0
        ];

        let filtered = savgol_filter(&data, 5, 2);

        assert_eq!(filtered.len(), data.len());
        assert!(filtered.iter().all(|value| value.is_finite()));
    }

    #[test]
    fn test_savgol_smooths_noisy_signal() {
        let data = Array1::from_iter((0..21).map(|i| 10.0 + if i % 2 == 0 { 1.0 } else { -1.0 }));

        let filtered = savgol_filter(&data, 11, 3);
        let input_error = data.iter().map(|value| (value - 10.0).powi(2)).sum::<f64>();
        let filtered_error = filtered
            .iter()
            .map(|value| (value - 10.0).powi(2))
            .sum::<f64>();

        assert_eq!(filtered.len(), data.len());
        assert!(filtered_error < input_error);
        assert!((filtered[10] - 10.0).abs() < (data[10] - 10.0).abs());
    }

    #[test]
    fn test_spectrum_smoothing_reduces_alternating_noise() {
        let data = Array1::from_iter((0..31).map(|i| 4.0 + if i % 2 == 0 { 0.4 } else { -0.4 }));

        let (smoothed, applied, method, window) = smooth_spectrum(&data, "savgol", 9);
        let input_error = data.iter().map(|value| (value - 4.0).powi(2)).sum::<f64>();
        let smoothed_error = smoothed
            .iter()
            .map(|value| (value - 4.0).powi(2))
            .sum::<f64>();

        assert!(applied);
        assert_eq!(method, DEFAULT_SPECTRUM_SMOOTHING_METHOD);
        assert_eq!(window, 9);
        assert_eq!(smoothed.len(), data.len());
        assert!(smoothed.iter().all(|value| value.is_finite()));
        assert!(smoothed_error < input_error);
    }

    #[test]
    fn test_spectrum_smoothing_can_be_disabled_or_rejected() {
        let data = array![0.0, f64::NAN, 2.0, 3.0, 4.0];

        let (disabled, disabled_applied, disabled_method, disabled_window) =
            smooth_spectrum(&data, "none", 7);
        let (unknown, unknown_applied, unknown_method, unknown_window) =
            smooth_spectrum(&data, "unknown", 7);

        assert!(!disabled_applied);
        assert_eq!(disabled_method, "none");
        assert_eq!(disabled_window, 0);
        assert!(disabled.iter().all(|value| value.is_finite()));
        assert!(!unknown_applied);
        assert_eq!(unknown_method, "none");
        assert_eq!(unknown_window, 0);
        assert!(unknown.iter().all(|value| value.is_finite()));
    }

    #[test]
    fn test_median_spectrum_smoothing_suppresses_impulse() {
        let data = array![1.0, 1.0, 1.0, 100.0, 1.0, 1.0, 1.0];

        let (smoothed, applied, method, window) = smooth_spectrum(&data, "median", 5);

        assert!(applied);
        assert_eq!(method, "median");
        assert_eq!(window, 5);
        assert_eq!(smoothed.len(), data.len());
        assert!(smoothed.iter().all(|value| value.is_finite()));
        assert!((smoothed[3] - 1.0).abs() < 1e-12);
    }

    #[test]
    fn test_savgol_adjusts_even_window_and_rejects_invalid_order() {
        let data = array![0.0, 1.0, 4.0, 9.0, 16.0, 25.0, 36.0];

        let adjusted = savgol_filter(&data, 4, 2);
        let invalid = savgol_filter(&data, 5, 5);

        assert!(adjusted
            .iter()
            .zip(data.iter())
            .all(|(actual, expected)| (actual - expected).abs() < 1e-9));
        assert_eq!(invalid, data);
    }
}
