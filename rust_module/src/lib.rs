use pyo3::prelude::*;
use pyo3::types::PyDict;

mod types;
mod signal;

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
#[pyo3(signature = (data, sample_rate = 1.0, filter_type = "savgol", window_type = "hann", threshold = 3.0))]
fn process_signal<'py>(
    py: Python<'py>,
    data: Vec<f64>,
    sample_rate: f64,
    filter_type: &str,
    window_type: &str,
    threshold: f64,
) -> PyResult<Bound<'py, PyDict>> {
    let mut signal = ndarray::Array1::from_vec(data);

    // 1. Фильтрация
    signal = match filter_type.to_lowercase().as_str() {
        "savgol" => signal::filters::savgol_filter(&signal, 11, 3),
        "median" => signal::filters::median_filter(&signal, 5),
        _ => signal,
    };

    // 2. FFT + оконная функция
    let spectrum = signal::fft::compute_magnitude_spectrum(&signal, window_type, sample_rate);

    // 3. Поиск пиков
    let peaks = signal::peak_detection::detect_peaks_adaptive(&spectrum, threshold);

    let dict = PyDict::new(py);
    let _ = dict.set_item("spectrum", spectrum.to_vec());
    let _ = dict.set_item("peaks", peaks);
    let _ = dict.set_item("sample_rate", sample_rate);

    Ok(dict)
}

#[pyfunction]
fn detect_peaks(_py: Python, data: Vec<f64>, threshold: f64) -> PyResult<Vec<Peak>> {
    let arr = ndarray::Array1::from_vec(data);
    Ok(signal::peak_detection::detect_peaks_adaptive(&arr, threshold))
}