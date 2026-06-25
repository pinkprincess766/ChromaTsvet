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
    normalize = false
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
    let spectrum = signal::fft::compute_magnitude_spectrum(&signal, window_type, sample_rate);

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

    // Area normalization is applied after baseline correction, but before peak
    // detection. It makes spectra with different intensity scales easier to
    // compare; downstream identification uses cosine similarity, which is
    // scale-invariant.
    let (analysis_spectrum, normalization_area) = if normalize {
        signal::normalization::normalize_area(&corrected_spectrum)
    } else {
        (corrected_spectrum.to_owned(), 0.0)
    };
    let normalized = normalize && normalization_area > 0.0;

    // 5. Frequency axis and peak picking
    let frequency_axis =
        signal::fft::compute_frequency_axis(analysis_spectrum.len(), signal_len, sample_rate);
    let mut peaks = signal::peak_detection::detect_peaks_with_settings(
        &analysis_spectrum,
        threshold,
        prominence,
        distance,
    );
    let bin_width = if signal_len > 0 {
        sample_rate / signal_len as f64
    } else {
        0.0
    };
    for peak in peaks.iter_mut() {
        peak.frequency = peak.position * bin_width;
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
