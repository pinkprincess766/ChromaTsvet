use pyo3::prelude::*;

#[derive(Debug, Clone)]
#[pyclass(get_all, set_all)]
pub struct Peak {
    pub position: f64,
    pub intensity: f64,
    pub width: f64,
    pub area: f64,
    pub snr: f64,
}

#[pymethods]
impl Peak {
    #[new]
    pub fn new(position: f64, intensity: f64) -> Self {
        Self {
            position,
            intensity,
            width: 0.0,
            area: 0.0,
            snr: 0.0,
        }
    }
}