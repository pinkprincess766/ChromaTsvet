//! High-performance signal filters (Carmack/Torvalds style)
//! Median filter + Savitzky-Golay placeholder

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
}