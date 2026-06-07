use ndarray::prelude::*;
use rustfft::{FftPlanner, num_complex::Complex};

pub fn compute_magnitude_spectrum(signal: &Array1<f64>, window_type: &str, _sample_rate: f64) -> Array1<f64> {
    let windowed = super::window::apply_window(signal, window_type);

    let n = windowed.len();
    if n == 0 {
        return Array1::zeros(0);
    }

    let mut planner = FftPlanner::new();
    let fft = planner.plan_fft_forward(n);

    let mut buffer: Vec<Complex<f64>> = windowed.iter().map(|&x| Complex { re: x, im: 0.0 }).collect();
    fft.process(&mut buffer);

    let mut magnitude = Array1::<f64>::zeros(n / 2);
    let scale = 2.0 / n as f64;

    for i in 0..(n / 2) {
        magnitude[i] = buffer[i].norm() * scale;
    }

    magnitude
}