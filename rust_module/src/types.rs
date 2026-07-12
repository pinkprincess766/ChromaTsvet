use pyo3::prelude::*;

#[derive(Debug, Clone)]
#[pyclass(get_all, set_all, skip_from_py_object)]
pub struct Peak {
    pub position: f64,
    pub frequency: f64,
    pub intensity: f64,
    pub prominence: f64,
    pub baseline_level: f64,
    pub left_base: f64,
    pub right_base: f64,
    pub width: f64,
    pub width_hz: f64,
    pub area: f64,
    pub noise: f64,
    pub snr: f64,
    pub is_global_max: bool,
}

#[pymethods]
impl Peak {
    #[new]
    pub fn new(position: f64, intensity: f64) -> Self {
        Self {
            position,
            frequency: 0.0,
            intensity,
            prominence: 0.0,
            baseline_level: 0.0,
            left_base: 0.0,
            right_base: 0.0,
            width: 0.0,
            width_hz: 0.0,
            area: 0.0,
            noise: 0.0,
            snr: 0.0,
            is_global_max: false,
        }
    }
}
