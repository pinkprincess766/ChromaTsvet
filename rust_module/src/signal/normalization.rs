use ndarray::prelude::*;

/// Normalize finite signal samples so the positive trapezoidal area is 1.0.
///
/// Baseline correction can leave small negative residuals, so the scale is
/// estimated from the physically meaningful positive area under the curve.
pub fn normalize_area(signal: &Array1<f64>) -> (Array1<f64>, f64) {
    let cleaned = super::filters::sanitize_signal(signal);
    let area = positive_trapezoidal_area(&cleaned);
    if !area.is_finite() || area <= f64::EPSILON {
        return (cleaned, 0.0);
    }

    (cleaned.mapv(|value| value / area), area)
}

pub fn positive_trapezoidal_area(signal: &Array1<f64>) -> f64 {
    if signal.is_empty() {
        return 0.0;
    }

    if signal.len() == 1 {
        return positive_value(signal[0]);
    }

    let mut area = 0.0;
    for i in 0..signal.len() - 1 {
        let left = positive_value(signal[i]);
        let right = positive_value(signal[i + 1]);
        area += (left + right) * 0.5;
    }

    area
}

fn positive_value(value: f64) -> f64 {
    if value.is_finite() {
        value.max(0.0)
    } else {
        0.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn area_normalization_scales_positive_integral_to_one() {
        let signal = array![0.0, 2.0, 2.0, 0.0];
        let (normalized, original_area) = normalize_area(&signal);

        assert!((original_area - 4.0).abs() < 1e-12);
        assert!((positive_trapezoidal_area(&normalized) - 1.0).abs() < 1e-12);
    }

    #[test]
    fn area_normalization_keeps_zero_area_signal_unchanged() {
        let signal = array![0.0, -1.0, 0.0];
        let (normalized, original_area) = normalize_area(&signal);

        assert_eq!(original_area, 0.0);
        assert_eq!(normalized, signal);
    }
}
