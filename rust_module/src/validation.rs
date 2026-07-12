use crate::pipeline::{process_signal_data, ProcessSettings, ProcessingWarning};
use crate::Peak;
use std::f64::consts::PI;
use std::time::{Duration, Instant};

const REPRESENTATIVE_SAMPLE_RATE: f64 = 1_024.0;
const REPRESENTATIVE_LEN: usize = 2_048;
const BENCHMARK_REPETITIONS: usize = 200;

fn representative_signal(len: usize) -> Vec<f64> {
    (0..len)
        .map(|sample| {
            let t = sample as f64 / REPRESENTATIVE_SAMPLE_RATE;
            let baseline = 0.08 + 0.015 * (2.0 * PI * 1.25 * t).sin();
            let first = 1.4 * (2.0 * PI * 48.0 * t).sin();
            let second = 0.65 * (2.0 * PI * 139.5 * t).sin();
            let third = 0.30 * (2.0 * PI * 311.0 * t).sin();
            let deterministic_noise = 0.025 * ((sample * 37 % 101) as f64 / 50.0 - 1.0);

            baseline + first + second + third + deterministic_noise
        })
        .collect()
}

fn representative_settings() -> ProcessSettings {
    ProcessSettings::from_python_args(
        REPRESENTATIVE_SAMPLE_RATE,
        "none",
        "hann",
        0.05,
        true,
        "improved",
        0.0,
        2,
        true,
        true,
        "savgol",
        7,
        0.0,
    )
}

fn hostile_cases() -> Vec<Vec<f64>> {
    vec![
        vec![],
        vec![1.0],
        vec![1.0, 2.0],
        vec![0.0, f64::NAN, 1.0, f64::INFINITY, f64::NEG_INFINITY, 0.0],
        vec![1.0e6, -1.0e6, 5.0e5, -5.0e5, 0.0, 1.0, -1.0],
        vec![0.0; 64],
    ]
}

fn assert_finite_output(output: &crate::pipeline::ProcessOutput) {
    assert!(output.spectrum.iter().all(|value| value.is_finite()));
    assert!(output.frequency_axis.iter().all(|value| value.is_finite()));
    assert!(output.peaks.iter().all(peak_is_finite));
}

fn peak_is_finite(peak: &Peak) -> bool {
    peak.position.is_finite()
        && peak.frequency.is_finite()
        && peak.intensity.is_finite()
        && peak.prominence.is_finite()
        && peak.baseline_level.is_finite()
        && peak.left_base.is_finite()
        && peak.right_base.is_finite()
        && peak.width.is_finite()
        && peak.width_hz.is_finite()
        && peak.area.is_finite()
        && peak.noise.is_finite()
        && peak.snr.is_finite()
}

#[test]
fn validation_pipeline_never_emits_non_finite_outputs_for_hostile_inputs() {
    for input in hostile_cases() {
        let output = process_signal_data(input, representative_settings());
        assert_finite_output(&output);
    }
}

#[test]
fn validation_pipeline_is_deterministic_for_representative_signal() {
    let input = representative_signal(REPRESENTATIVE_LEN);

    let first = process_signal_data(input.clone(), representative_settings());
    let second = process_signal_data(input, representative_settings());

    assert_eq!(first.spectrum.to_vec(), second.spectrum.to_vec());
    assert_eq!(first.frequency_axis, second.frequency_axis);
    assert_eq!(first.peaks.len(), second.peaks.len());
    assert_eq!(
        first
            .peaks
            .iter()
            .map(|peak| peak.position)
            .collect::<Vec<_>>(),
        second
            .peaks
            .iter()
            .map(|peak| peak.position)
            .collect::<Vec<_>>()
    );
    assert_eq!(first.warnings, second.warnings);
}

#[test]
fn validation_frequency_axis_obeys_fft_bin_contract() {
    for signal_len in [4usize, 5, 16, 255, 1024] {
        for sample_rate in [1.0, 400.0, 44_100.0] {
            let settings = ProcessSettings::from_python_args(
                sample_rate,
                "none",
                "rectangular",
                0.01,
                false,
                "none",
                0.0,
                0,
                false,
                false,
                "none",
                0,
                0.0,
            );
            let output = process_signal_data(vec![0.0; signal_len], settings);
            let expected_bin_width = sample_rate / signal_len as f64;

            assert_eq!(output.frequency_axis.len(), output.spectrum.len());
            for (bin, frequency) in output.frequency_axis.iter().enumerate() {
                assert!((*frequency - bin as f64 * expected_bin_width).abs() < 1e-12);
            }
        }
    }
}

#[test]
fn validation_diagnostics_report_safety_fallbacks() {
    let settings = ProcessSettings::from_python_args(
        f64::NAN,
        "not-a-filter",
        "not-a-window",
        0.01,
        true,
        "not-a-baseline",
        0.0,
        0,
        true,
        true,
        "not-a-smoother",
        7,
        0.0,
    );

    let output = process_signal_data(vec![0.0, 0.0, 0.0, 0.0], settings);

    assert!(output
        .warnings
        .contains(&ProcessingWarning::InvalidSampleRateFallback));
    assert!(output
        .warnings
        .contains(&ProcessingWarning::UnknownFilterFallback));
    assert!(output
        .warnings
        .contains(&ProcessingWarning::UnknownWindowFallback));
    assert!(output
        .warnings
        .contains(&ProcessingWarning::UnknownBaselineFallback));
    assert!(output
        .warnings
        .contains(&ProcessingWarning::UnknownSmoothingDisabled));
    assert!(output
        .warnings
        .contains(&ProcessingWarning::AreaNormalizationSkipped));
}

#[test]
#[ignore = "manual benchmark: run with `cargo test benchmark_representative_pipeline -- --ignored --nocapture`"]
fn benchmark_representative_pipeline() {
    let input = representative_signal(REPRESENTATIVE_LEN);
    let start = Instant::now();

    for _ in 0..BENCHMARK_REPETITIONS {
        let output = process_signal_data(input.clone(), representative_settings());
        assert_finite_output(&output);
    }

    let elapsed = start.elapsed();
    let per_run = elapsed / BENCHMARK_REPETITIONS as u32;
    println!(
        "representative pipeline: {:?} total for {} runs, {:?} per run",
        elapsed, BENCHMARK_REPETITIONS, per_run
    );

    // This is a guardrail, not a contractual SLA. It catches catastrophic
    // accidental slowdowns while avoiding machine-specific micro-claims.
    assert!(per_run < Duration::from_millis(50));
}
