use pyo3::prelude::*;
use pyo3::types::PyDict;

mod signal;
mod types;

pub use types::Peak;

#[pymodule]
fn spectrometer_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_version, m)?)?;
    m.add_function(wrap_pyfunction!(process_signal, m)?)?;
    m.add_function(wrap_pyfunction!(detect_peaks, m)?)?;

    Ok(())
}

#[pyfunction]
fn get_version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

#[pyfunction]
#[pyo3(signature = (
    data,
    sample_rate = 1.0,
    filter_type = "savgol",
    window_type = "hann",
    threshold = 3.0,
    baseline = true,
    baseline_method = "improved",
    prominence = 0.0,
    distance = 0,
    normalize = false,
    spectrum_smoothing = false,
    spectrum_smoothing_method = "savgol",
    spectrum_smoothing_window = 7,
    min_snr = 0.0
))]
fn process_signal<'py>(
    py: Python<'py>,
    data: Vec<f64>,
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
) -> PyResult<Bound<'py, PyDict>> {
    // Sanitize once at the Python boundary so every filter choice reaches FFT safely.
    let mut signal = signal::filters::sanitize_signal(&ndarray::Array1::from_vec(data));
    let signal_len = signal.len();
    let sample_rate = if sample_rate.is_finite() && sample_rate > 0.0 {
        sample_rate
    } else {
        1.0
    };

    // The Python GUI applies the selected signal filter before calling this
    // function and passes `filter_type = "none"`. Rust-side filtering remains
    // for backward compatibility with direct calls to the PyO3 API.
    signal = match filter_type.to_lowercase().as_str() {
        "savgol" => signal::filters::savgol_filter(&signal, 11, 3),
        "median" => signal::filters::median_filter(&signal, 5),
        _ => signal,
    };

    // 2. FFT + оконная функция
    let spectrum = signal::fft::compute_magnitude_spectrum(&signal, window_type);

    // 3. Baseline correction before peak detection
    let baseline_method = baseline_method.to_lowercase();
    let baseline_applied = baseline && baseline_method != "none";
    let corrected_spectrum = if baseline_applied {
        let window_size = (spectrum.len() / 20).max(5);
        let baseline_signal = match baseline_method.as_str() {
            "simple" => signal::filters::estimate_baseline_simple(&spectrum, window_size),
            _ => signal::filters::estimate_baseline(&spectrum, window_size),
        };
        &spectrum - &baseline_signal
    } else {
        spectrum.to_owned()
    };

    // Spectrum smoothing is deliberately placed after baseline correction and
    // before normalization, so peak detection sees a finite, comparable curve
    // without hiding the original acquisition filter semantics.
    let (smoothed_spectrum, smoothing_applied, smoothing_method, smoothing_window) =
        if spectrum_smoothing {
            signal::filters::smooth_spectrum(
                &corrected_spectrum,
                spectrum_smoothing_method,
                spectrum_smoothing_window,
            )
        } else {
            (corrected_spectrum.to_owned(), false, "none", 0)
        };

    // Area normalization is applied after baseline correction/spectrum
    // smoothing, but before peak detection. It makes spectra with different
    // intensity scales easier to compare; downstream identification can then
    // focus on shape and peak features.
    let (analysis_spectrum, normalization_area) = if normalize {
        signal::normalization::normalize_area(&smoothed_spectrum)
    } else {
        (smoothed_spectrum.to_owned(), 0.0)
    };
    let normalized = normalize && normalization_area > 0.0;

    // 5. Frequency axis and peak picking
    let frequency_axis =
        signal::fft::compute_frequency_axis(analysis_spectrum.len(), signal_len, sample_rate);
    // Computer programming is an art, because it applies accumulated knowledge to the world, because it requires skill and ingenuity, and especially because it produces objects of beauty
    let mut peaks = signal::peak_detection::detect_peaks_with_criteria(
        &analysis_spectrum,
        signal::peak_detection::PeakDetectionSettings::new(
            threshold,
            prominence,
            distance,
            min_snr,
        ),
    );
    let bin_width = if signal_len > 0 {
        sample_rate / signal_len as f64
    } else {
        0.0
    };
    for peak in peaks.iter_mut() {
        peak.frequency = peak.position * bin_width;
        peak.width_hz = peak.width * bin_width;
    }

    let dict = PyDict::new(py);
    let _ = dict.set_item("spectrum", analysis_spectrum.to_vec());
    let _ = dict.set_item("frequency_axis", frequency_axis);
    let _ = dict.set_item("peaks", peaks);
    let _ = dict.set_item("sample_rate", sample_rate);
    let _ = dict.set_item("baseline_corrected", baseline_applied);
    let _ = dict.set_item(
        "baseline_method",
        if baseline_applied {
            baseline_method.as_str()
        } else {
            "none"
        },
    );
    let _ = dict.set_item("peak_threshold", threshold);
    let _ = dict.set_item("peak_prominence", prominence);
    let _ = dict.set_item("peak_distance", distance);
    let _ = dict.set_item("peak_min_snr", min_snr);
    let _ = dict.set_item("spectrum_smoothed", smoothing_applied);
    let _ = dict.set_item("spectrum_smoothing_method", smoothing_method);
    let _ = dict.set_item("spectrum_smoothing_window", smoothing_window);
    let _ = dict.set_item("normalized", normalized);
    let _ = dict.set_item("normalization", if normalized { "area" } else { "none" });
    let _ = dict.set_item("normalization_area", normalization_area);

    Ok(dict)
}

#[pyfunction]
fn detect_peaks(_py: Python, data: Vec<f64>, threshold: f64) -> PyResult<Vec<Peak>> {
    let arr = ndarray::Array1::from_vec(data);
    Ok(signal::peak_detection::detect_peaks_adaptive(
        &arr, threshold,
    ))
}
