use ndarray::prelude::*;

pub fn apply_window(signal: &Array1<f64>, window_type: &str) -> Array1<f64> {
    let n = signal.len();
    let mut windowed = signal.to_owned();

    if n <= 1 {
        return windowed;
    }

    match window_type.to_lowercase().as_str() {
        "hann" => {
            for i in 0..n {
                let w =
                    0.5 * (1.0 - (2.0 * std::f64::consts::PI * i as f64 / (n - 1) as f64).cos());
                windowed[i] *= w;
            }
        }
        "hamming" => {
            for i in 0..n {
                let w =
                    0.54 - 0.46 * (2.0 * std::f64::consts::PI * i as f64 / (n - 1) as f64).cos();
                windowed[i] *= w;
            }
        }
        _ => {} // rectangular (no window)
    }
    windowed
}
