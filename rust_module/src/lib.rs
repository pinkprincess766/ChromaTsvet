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
    distance = 0
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
) -> PyResult<Bound<'py, PyDict>> {
    // Sanitize once at the Python boundary so every filter choice reaches FFT safely.
    let mut signal = signal::filters::sanitize_signal(&ndarray::Array1::from_vec(data));

    // 1. Фильтрация
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

    // 4. Поиск пиков
    let peaks = signal::peak_detection::detect_peaks_with_settings(
        &corrected_spectrum,
        threshold,
        prominence,
        distance,
    );

    let dict = PyDict::new(py);
    let _ = dict.set_item("spectrum", corrected_spectrum.to_vec());
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

    Ok(dict)
}

#[pyfunction]
fn detect_peaks(_py: Python, data: Vec<f64>, threshold: f64) -> PyResult<Vec<Peak>> {
    let arr = ndarray::Array1::from_vec(data);
    Ok(signal::peak_detection::detect_peaks_adaptive(
        &arr, threshold,
    ))
}
