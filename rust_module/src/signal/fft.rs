use ndarray::prelude::*;
use rustfft::{num_complex::Complex, FftPlanner};

pub fn compute_magnitude_spectrum(signal: &Array1<f64>, window_type: &str) -> Array1<f64> {
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

    // For real-valued input, the single-sided spectrum contains DC, positive
    // frequencies, and the Nyquist bin when `n` is even. DC and Nyquist do not
    // have mirrored partners, so only the interior positive-frequency bins are
    // doubled to preserve amplitude.
    let spectrum_len = n / 2 + 1;
    let mut magnitude = Array1::<f64>::zeros(spectrum_len);
    for bin in 0..spectrum_len {
        let has_mirrored_partner = bin != 0 && !(n % 2 == 0 && bin == n / 2);
        let scale = if has_mirrored_partner { 2.0 } else { 1.0 } / n as f64;
        magnitude[bin] = buffer[bin].norm() * scale;
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
        let axis = compute_frequency_axis(5, 8, 800.0);

        assert_eq!(axis, vec![0.0, 100.0, 200.0, 300.0, 400.0]);
    }

    #[test]
    fn frequency_axis_falls_back_for_invalid_sample_rate() {
        let axis = compute_frequency_axis(3, 4, f64::NAN);

        assert_eq!(axis, vec![0.0, 0.25, 0.5]);
    }

    #[test]
    fn single_sided_spectrum_includes_even_length_nyquist_bin() {
        let signal = array![1.0, -1.0, 1.0, -1.0];
        let spectrum = compute_magnitude_spectrum(&signal, "rectangular");

        assert_eq!(spectrum.len(), 3);
        assert!((spectrum[0] - 0.0).abs() < 1e-12);
        assert!((spectrum[1] - 0.0).abs() < 1e-12);
        assert!((spectrum[2] - 1.0).abs() < 1e-12);
    }

    #[test]
    fn single_sided_spectrum_scales_dc_once() {
        let signal = array![1.0, 1.0, 1.0, 1.0];
        let spectrum = compute_magnitude_spectrum(&signal, "rectangular");

        assert_eq!(spectrum.len(), 3);
        assert!((spectrum[0] - 1.0).abs() < 1e-12);
        assert!((spectrum[1] - 0.0).abs() < 1e-12);
        assert!((spectrum[2] - 0.0).abs() < 1e-12);
    }

    #[test]
    fn single_sided_spectrum_scales_interior_bins_twice() {
        let signal = array![0.0, 1.0, 0.0, -1.0];
        let spectrum = compute_magnitude_spectrum(&signal, "rectangular");

        assert_eq!(spectrum.len(), 3);
        assert!((spectrum[1] - 1.0).abs() < 1e-12);
    }
}
