use pyo3::prelude::*;
use pyo3::types::PyDict;

mod pipeline;
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
    let settings = pipeline::ProcessSettings::from_python_args(
        sample_rate,
        filter_type,
        window_type,
        threshold,
        baseline,
        baseline_method,
        prominence,
        distance,
        normalize,
        spectrum_smoothing,
        spectrum_smoothing_method,
        spectrum_smoothing_window,
        min_snr,
    );
    let output = pipeline::process_signal_data(data, settings);

    let dict = PyDict::new(py);
    let _ = dict.set_item("spectrum", output.spectrum.to_vec());
    let _ = dict.set_item("frequency_axis", output.frequency_axis);
    let _ = dict.set_item("peaks", output.peaks);
    let _ = dict.set_item("sample_rate", output.sample_rate);
    let _ = dict.set_item("baseline_corrected", output.baseline_corrected);
    let _ = dict.set_item("baseline_method", output.baseline_method);
    let _ = dict.set_item("peak_threshold", output.peak_threshold);
    let _ = dict.set_item("peak_prominence", output.peak_prominence);
    let _ = dict.set_item("peak_distance", output.peak_distance);
    let _ = dict.set_item("peak_min_snr", output.peak_min_snr);
    let _ = dict.set_item("spectrum_smoothed", output.spectrum_smoothed);
    let _ = dict.set_item(
        "spectrum_smoothing_method",
        output.spectrum_smoothing_method,
    );
    let _ = dict.set_item(
        "spectrum_smoothing_window",
        output.spectrum_smoothing_window,
    );
    let _ = dict.set_item("normalized", output.normalized);
    let _ = dict.set_item(
        "normalization",
        if output.normalized { "area" } else { "none" },
    );
    let _ = dict.set_item("normalization_area", output.normalization_area);

    Ok(dict)
}

#[pyfunction]
fn detect_peaks(_py: Python, data: Vec<f64>, threshold: f64) -> PyResult<Vec<Peak>> {
    let arr = ndarray::Array1::from_vec(data);
    Ok(signal::peak_detection::detect_peaks_adaptive(
        &arr, threshold,
    ))
}
