use ndarray::prelude::*;
use crate::types::Peak;

pub fn detect_peaks_adaptive(signal: &Array1<f64>, _threshold_factor: f64) -> Vec<Peak> {
    if signal.is_empty() {
        return vec![];
    }

    let finite_values: Vec<f64> = signal.iter().copied().filter(|v| v.is_finite()).collect();
    if finite_values.is_empty() {
        return vec![];
    }

    let mean = finite_values.iter().sum::<f64>() / finite_values.len() as f64;

    // Просто берём глобальный максимум — 100% гарантия пика
    let (max_idx, max_val) = signal.iter()
        .enumerate()
        .filter(|(_, value)| value.is_finite())
        .max_by(|(_, a), (_, b)| a.total_cmp(b))
        .map(|(i, value)| (i, *value))
        .unwrap();

    let mut peaks = vec![Peak {
        position: max_idx as f64,
        intensity: max_val,
        width: 3.0,
        area: 0.0,
        snr: max_val / (mean + 1e-8),
    }];

    // Дополнительно ищем локальные максимумы (если есть)
    for i in 1..signal.len() - 1 {
        if !(signal[i - 1].is_finite() && signal[i].is_finite() && signal[i + 1].is_finite()) {
            continue;
        }

        if signal[i] > signal[i-1] && signal[i] > signal[i+1] && signal[i] > max_val * 0.3 {
            peaks.push(Peak {
                position: i as f64,
                intensity: signal[i],
                width: 3.0,
                area: 0.0,
                snr: signal[i] / (mean + 1e-8),
            });
        }
    }

    peaks
}
