use ndarray::prelude::*;
use rustfft::{num_complex::Complex, FftPlanner};

pub fn compute_magnitude_spectrum(
    signal: &Array1<f64>,
    window_type: &str,
    _sample_rate: f64,
) -> Array1<f64> {
    let windowed = super::window::apply_window(signal, window_type);

    let n = windowed.len();
    if n == 0 {
        return Array1::zeros(0);
    }

    let mut planner = FftPlanner::new();
    let fft = planner.plan_fft_forward(n);

    let mut buffer: Vec<Complex<f64>> = windowed
        .iter()
        .map(|&x| Complex { re: x, im: 0.0 })
        .collect();
    fft.process(&mut buffer);

    let mut magnitude = Array1::<f64>::zeros(n / 2);
    let scale = 2.0 / n as f64;

    for i in 0..(n / 2) {
        magnitude[i] = buffer[i].norm() * scale;
    }

    magnitude
}

pub fn compute_frequency_axis(
    spectrum_len: usize,
    signal_len: usize,
    sample_rate: f64,
) -> Vec<f64> {
    if spectrum_len == 0 || signal_len == 0 {
        return Vec::new();
    }

    let sample_rate = if sample_rate.is_finite() && sample_rate > 0.0 {
        sample_rate
    } else {
        1.0
    };
    let bin_width = sample_rate / signal_len as f64;

    (0..spectrum_len)
        .map(|bin| bin as f64 * bin_width)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frequency_axis_uses_sample_rate_and_source_length() {
        let axis = compute_frequency_axis(4, 8, 800.0);

        assert_eq!(axis, vec![0.0, 100.0, 200.0, 300.0]);
    }

    #[test]
    fn frequency_axis_falls_back_for_invalid_sample_rate() {
        let axis = compute_frequency_axis(3, 4, f64::NAN);

        assert_eq!(axis, vec![0.0, 0.25, 0.5]);
    }
}
