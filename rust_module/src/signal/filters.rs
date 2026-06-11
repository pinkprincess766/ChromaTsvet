//! High-performance signal filters (Carmack/Torvalds style)
//! Median filter + Savitzky-Golay placeholder

use medians::Medianf64;
use ndarray::prelude::*;

/// Медианный фильтр — отлично убирает импульсные помехи, сохраняя края сигнала
pub fn median_filter(signal: &Array1<f64>, window_size: usize) -> Array1<f64> {
    if window_size < 3 || window_size % 2 == 0 {
        return signal.to_owned();
    }

    let n = signal.len();
    let mut filtered = Array1::<f64>::zeros(n);
    let half = window_size / 2;

    for i in 0..n {
        let start = i.saturating_sub(half);
        let end = (i + half + 1).min(n);
        let window = signal.slice(s![start..end]);
        let mut w: Vec<f64> = window.to_vec();
        w.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let mid = w.len() / 2;
        filtered[i] = w[mid];
    }
    filtered
}

/// Estimates a slowly varying baseline while remaining resistant to sharp peaks.
pub fn estimate_baseline(signal: &Array1<f64>, window_size: usize) -> Array1<f64> {
    let n = signal.len();
    if n == 0 {
        return Array1::zeros(0);
    }
    if n < 3 {
        return signal.mapv(|value| if value.is_finite() { value } else { 0.0 });
    }

    let window_size = normalized_window_size(window_size, n);
    let smooth_window = normalized_window_size(5, n);

    let first_baseline = estimate_baseline_simple(signal, window_size);

    // A residual pass compensates for slow local bias left by the first
    // rolling minimum. On a well-estimated background this correction is near zero.
    let residual = Array1::from_iter(signal.iter().zip(first_baseline.iter()).map(
        |(&value, &baseline)| {
            if value.is_finite() && baseline.is_finite() {
                value - baseline
            } else {
                0.0
            }
        },
    ));
    let residual_floor = rolling_minimum(&residual, window_size);
    let correction = median_smooth(&residual_floor, smooth_window);

    let mut baseline = &first_baseline + &correction;
    for i in 0..n {
        if signal[i].is_finite() {
            baseline[i] = baseline[i].min(signal[i]);
        } else {
            baseline[i] = 0.0;
        }
    }

    baseline
}

/// Estimates the baseline using a single lower-envelope smoothing pass.
pub fn estimate_baseline_simple(signal: &Array1<f64>, window_size: usize) -> Array1<f64> {
    let n = signal.len();
    if n == 0 {
        return Array1::zeros(0);
    }
    if n < 3 {
        return signal.mapv(|value| if value.is_finite() { value } else { 0.0 });
    }

    let window_size = normalized_window_size(window_size, n);
    let smooth_window = normalized_window_size(5, n);

    // The rolling minimum follows the lower envelope; median smoothing
    // removes its staircase pattern without pulling it toward sharp peaks.
    let lower_envelope = rolling_minimum(signal, window_size);
    median_smooth(&lower_envelope, smooth_window)
}

fn normalized_window_size(requested: usize, signal_len: usize) -> usize {
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
    let n = signal.len();
    let half = window_size / 2;
    let mut result = Array1::<f64>::zeros(n);

    for i in 0..n {
        let start = i.saturating_sub(half);
        let end = (i + half + 1).min(n);
        result[i] = signal
            .slice(s![start..end])
            .iter()
            .copied()
            .filter(|value| value.is_finite())
            .min_by(|a, b| a.total_cmp(b))
            .unwrap_or(0.0);
    }

    result
}

fn median_smooth(signal: &Array1<f64>, window_size: usize) -> Array1<f64> {
    let n = signal.len();
    let half = window_size / 2;
    let mut result = Array1::<f64>::zeros(n);

    for i in 0..n {
        let start = i.saturating_sub(half);
        let end = (i + half + 1).min(n);
        let values: Vec<f64> = signal
            .slice(s![start..end])
            .iter()
            .copied()
            .filter(|value| value.is_finite())
            .collect();

        result[i] = values.as_slice().medf_checked().unwrap_or(0.0);
    }

    result
}

/// Savitzky-Golay (заглушка на время)
/// TODO: позже сделаем полноценную реализацию через savgol-rs или ndarray
pub fn savgol_filter(signal: &Array1<f64>, _window_size: usize, _poly_order: usize) -> Array1<f64> {
    signal.to_owned() // пока возвращаем как есть
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
}
