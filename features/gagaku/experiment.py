"""Reproducible Issue #53 one-pipe render and Issue #52 Gate 1 measurement."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from features.gagaku.sho_one_pipe import PAPER_DOI, PAPER_PARAMETERS, render, write_wav


REFERENCE = Path(__file__).parent / "refs" / "hikichi_2003_ichi.json"
PRESSURES_PA = (400, 600, 800)
LENGTHS_M = (0.142, 0.241, 0.34, 0.425, 0.567)
THRESHOLD_TEST_PRESSURES_PA = (100, 200, 300, 400, 600, 800, 1000)
FINE_ORIGINAL_PRESSURES_PA = tuple(range(75, 451, 25))


def rms(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def run(output_dir: Path, *, reed_q: float = 35.0, include_q8_comparison: bool = True) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    wavs = {}
    entrance_flow_wavs = {}
    spectra = []
    entrance_flow_spectra = []
    for pressure_pa in PRESSURES_PA:
        signal = render(pressure_pa=pressure_pa, reed_q=reed_q)
        wav = write_wav(output_dir / f"ichi-{pressure_pa}pa.wav", signal, 48000)
        wavs[str(pressure_pa)] = wav
        # U_in is the modeled physical source used by the paper's pipe
        # transfer calculation. Its normalized PCM is diagnostic only: no
        # transfer or radiation model is applied here.
        entrance_flow = render(pressure_pa=pressure_pa, reed_q=reed_q,
                               output_signal="entrance_volume_velocity")
        flow_wav = write_wav(output_dir / f"ichi-entrance-flow-{pressure_pa}pa.wav",
                             entrance_flow, 48000, physical_unit="m3/s")
        entrance_flow_wavs[str(pressure_pa)] = flow_wav
        # Evaluate every waveform with the same #54 algorithm. The 800 Pa
        # result is the primary 24.1 cm / B4 comparison.
        result_path = output_dir / f"evaluation-{pressure_pa}pa.json"
        subprocess.run(
            [sys.executable, "-m", "features.gagaku.evaluate", "--wav", wav["path"],
             "--reference", str(REFERENCE), "--output", str(result_path)],
            check=True,
        )
        evaluation = json.loads(result_path.read_text())
        harmonics = evaluation["measurements"]["spectrum"]["harmonic_amplitudes"]
        spectra.append({"pressure_pa": pressure_pa,
                        "f0_hz": evaluation["measurements"]["f0_hz"],
                        "centroid_hz": evaluation["measurements"]["spectrum"]["centroid_hz"],
                        "h4_over_h2": harmonics["4"] / harmonics["2"] if harmonics["2"] else None,
                        "h2_h4_rule_pass": evaluation["measurements"]["spectrum"]["second_and_fourth_dominant"],
                        "internal_pressure_rms_pa": rms(signal[len(signal) // 2:]),
                        "wav_sha256": wav["sha256"]})
        flow_path = output_dir / f"evaluation-entrance-flow-{pressure_pa}pa.json"
        subprocess.run(
            [sys.executable, "-m", "features.gagaku.evaluate", "--wav", flow_wav["path"],
             "--reference", str(REFERENCE), "--output", str(flow_path)],
            check=True,
        )
        flow_evaluation = json.loads(flow_path.read_text())
        flow_harmonics = flow_evaluation["measurements"]["spectrum"]["harmonic_amplitudes"]
        entrance_flow_spectra.append({
            "pressure_pa": pressure_pa,
            "f0_hz": flow_evaluation["measurements"]["f0_hz"],
            "centroid_hz": flow_evaluation["measurements"]["spectrum"]["centroid_hz"],
            "h4_over_h2": flow_harmonics["4"] / flow_harmonics["2"] if flow_harmonics["2"] else None,
            "h2_h4_rule_pass": flow_evaluation["measurements"]["spectrum"]["second_and_fourth_dominant"],
            "wav_sha256": flow_wav["sha256"],
        })

    threshold_sweep = []
    for length_m in LENGTHS_M:
        measurements = []
        for pressure_pa in THRESHOLD_TEST_PRESSURES_PA:
            signal = render(pressure_pa=pressure_pa, pipe_length_m=length_m, reed_q=reed_q,
                            seconds=1.5)
            steady_rms = rms(signal[len(signal) // 2:])
            measurements.append({"pressure_pa": pressure_pa,
                                 "internal_pressure_rms_pa": steady_rms,
                                 "oscillates": steady_rms >= 1.0})
        threshold_sweep.append({
            "pipe_length_m": length_m,
            "nominal_quarter_wave_resonance_hz": 340 / (4 * length_m),
            "first_tested_oscillating_pressure_pa": next(
                (row["pressure_pa"] for row in measurements if row["oscillates"]), None),
            "measurements": measurements,
        })

    fine_original_onset = []
    for pressure_pa in FINE_ORIGINAL_PRESSURES_PA:
        signal = render(pressure_pa=pressure_pa, pipe_length_m=0.241,
                        reed_q=reed_q, seconds=1.5)
        steady_rms = rms(signal[len(signal) // 2:])
        fine_original_onset.append({"pressure_pa": pressure_pa,
                                    "internal_pressure_rms_pa": steady_rms,
                                    "oscillates": steady_rms >= 1.0})

    primary_path = output_dir / "evaluation-800pa.json"
    result = json.loads(primary_path.read_text())
    centroids = [row["centroid_hz"] for row in spectra]
    spectrum_trend = all(value is not None for value in centroids) and all(
        b > a for a, b in zip(centroids, centroids[1:]))
    thresholds = [row["first_tested_oscillating_pressure_pa"] for row in threshold_sweep]
    length_trend = len(set(thresholds)) > 1
    original_onset_pa = next(row["first_tested_oscillating_pressure_pa"]
                             for row in threshold_sweep if row["pipe_length_m"] == 0.241)
    inhibited_band_row = next(row for row in threshold_sweep if row["pipe_length_m"] == 0.34)
    for criterion in result["gate_1"]["criteria"]:
        if criterion["id"] == "pressure_dependent_high_frequency_growth":
            criterion.update(
                status="PASS" if spectrum_trend else "FAIL",
                measurement={"pressures_pa": list(PRESSURES_PA), "centroids_hz": centroids},
                reason="Centroid must increase strictly at 0.4, 0.6 and 0.8 kPa; "
                       "these are internal-pressure proxy WAVs, not external radiation recordings",
            )
        elif criterion["id"] == "pipe_length_threshold_dependence":
            criterion.update(
                status="PASS" if length_trend else "FAIL",
                measurement={"thresholds_by_length": [
                    {"pipe_length_m": row["pipe_length_m"],
                     "first_tested_oscillating_pressure_pa": row["first_tested_oscillating_pressure_pa"]}
                    for row in threshold_sweep]},
                reason="Coarse first-tested onset from cold starts and 1 Pa RMS rule; "
                       "different lengths must not all have the same observed onset",
            )
    result["gate_1"]["status"] = (
        "PASS" if all(c["status"] == "PASS" for c in result["gate_1"]["criteria"])
        else "FAIL")
    result["gate_1"]["overall_reason"] = (
        "all measured criteria pass" if result["gate_1"]["status"] == "PASS"
        else "at least one measured criterion fails; see criteria and diagnosis")
    result["experiment"] = {
        "issue": 53,
        "paper_doi": PAPER_DOI,
        "condition": "Q35_baseline" if reed_q == 35.0 else f"Q{reed_q:g}_sensitivity",
        "is_primary_gate_condition": reed_q == 35.0,
        "model": "coupled reed/slit inertia/pipe reflection, internal pressure and un-radiated entrance flow",
        "parameters": {"sample_rate_hz": 48000, "pipe_length_m": 0.241,
                       "pressures_pa": list(PRESSURES_PA), "reed_q": reed_q,
                       "additional_mass_ratio": 0.0, "reflection_loss": 0.98,
                       "reflection_sigma_samples": 1.0},
        "paper_model_parameters": PAPER_PARAMETERS,
        "paper_parameter_source": "Hikichi et al. 2003 Table II and Eqs. 1-3",
        "onset_protocol": {
            "input": "positive pressure, independent cold start for every run, 50 ms ramp",
            "duration_s": 1.5,
            "steady_window_s": [0.75, 1.5],
            "classification": "internal p2 steady-window RMS >= 1 Pa",
            "coarse_pressure_grid_pa": list(THRESHOLD_TEST_PRESSURES_PA),
            "fine_original_length_pressure_grid_pa": list(FINE_ORIGINAL_PRESSURES_PA),
            "fine_pipe_length_m": 0.241,
            "comparison_limit": "paper's experiment gradually increased pressure; this finite cold-start protocol differs",
        },
        "implementation_assumptions": [
            "Gaussian reflection loss 0.98 and width 1 sample are not numerically specified in accessed paper",
            "50 ms pressure ramp initializes motion; no target-frequency forcing",
            "WAV maps internal pipe pressure to PCM16 with per-file listening gain; no calibrated radiated pressure",
            "Entrance volume velocity U_in is an un-radiated diagnostic PCM WAV with its own per-file gain",
            "Onset is a coarse 1.5 s cold-start test with 1 Pa steady-state RMS criterion",
            "Fine original-length onset sweep uses the same 1.5 s cold-start and 1 Pa RMS rule at 25 Pa spacing from 75 to 450 Pa",
        ],
        "pressure_sweep": spectra,
        "entrance_volume_velocity_sweep": entrance_flow_spectra,
        "threshold_sweep": threshold_sweep,
        "fine_original_length_onset_sweep": fine_original_onset,
        "paper_comparison": {
            "original_pipe_experimental_positive_threshold_pa": 370,
            "original_pipe_experimental_negative_threshold_pa": 90,
            "our_original_pipe_first_tested_positive_onset_pa": original_onset_pa,
            "our_original_pipe_fine_first_tested_positive_onset_pa": next(
                (row["pressure_pa"] for row in fine_original_onset if row["oscillates"]), None),
            "positive_onset_difference_pa": original_onset_pa - 370 if original_onset_pa is not None else None,
            "fine_positive_onset_difference_pa": next(
                (row["pressure_pa"] - 370 for row in fine_original_onset if row["oscillates"]), None),
            "positive_onset_comparison_status": "DIFFERENT_COLD_START_PROTOCOL",
            "published_simulation_inhibited_resonance_band_hz": [210, 350],
            "our_250hz_resonance_first_tested_onset_pa": inhibited_band_row["first_tested_oscillating_pressure_pa"],
            "inhibited_band_comparison_status": (
                "CONSISTENT_WITH_NO_ONSET_UP_TO_1KPA"
                if inhibited_band_row["first_tested_oscillating_pressure_pa"] is None
                else "DISCREPANT_ONSET_OBSERVED"),
            "note": "Our coarse and fine cold-start onset sweeps are not the paper's gradually ramped-pressure experiment; no numerical tolerance for threshold was set by Issue #52.",
        },
        "diagnosis_if_fail": [
            "The internal-pressure proxy omits the paper's exit radiation transfer function; compare H2/H4 after implementing and checking that transfer.",
            "The paper reports that H2/H4 predominance is not caused by pipe transfer resonance peaks; test source flow and transfer separately rather than tuning the exit response to force harmonics.",
            "The original-length cold-start onset is protocol-dependent and differs from the paper's gradually ramped-pressure measurement; compare Q and initial conditions before parameter identification.",
            "The published symmetric reed model does not reproduce the measured positive/negative threshold asymmetry (+370/-90 Pa); the present positive-only simulation cannot establish it.",
            ("At a nominal 250 Hz pipe resonance this condition sounds at 1 kPa, unlike the paper's simulated 210-350 Hz inhibited band; revisit pipe reflection and reed parameters."
             if inhibited_band_row["first_tested_oscillating_pressure_pa"] is not None else
             "At a nominal 250 Hz pipe resonance this condition remains silent through 1 kPa, consistent with the paper's simulated inhibited band under the coarse test."),
            "Acquire permissioned real ichi recordings or digitized paper measurements before quantitative timbre/threshold matching.",
        ],
        "next_experiment": "Measure reed Q independently by free ringdown; acquire rights-cleared synchronized reed displacement, internal pressure and 5 cm exterior pressure at 400/600/800 Pa; derive entrance impedance and exit radiation from one pipe/termination model, then rerun #52 without changing its harmonic rule.",
    }
    source = Path(__file__).parent / "sho_one_pipe.py"
    result["provenance"].update(
        source_commit=os.environ.get("GAGAKU_SOURCE_COMMIT") or subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
        ).stdout.strip(),
        checkout_commit=result["provenance"]["git_commit"],
        model_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        reference_sha256=hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
        waveform_manifest=wavs,
        entrance_volume_velocity_waveform_manifest=entrance_flow_wavs,
    )
    if include_q8_comparison:
        q8_result = run(output_dir / "q8", reed_q=8.0, include_q8_comparison=False)
        result["experiment"]["q_sensitivity"] = {
            "baseline_reed_q": reed_q,
            "comparison_reed_q": 8.0,
            "source": "Hikichi et al. 2003 Sec. III.D estimates Q=8-10 for threshold; Table II uses Q=8-35",
            "comparison_result": str(output_dir / "q8" / "result.json"),
            "comparison_gate_1_status": q8_result["gate_1"]["status"],
            "comparison_f0_hz": q8_result["measurements"]["f0_hz"],
            "comparison_fine_first_tested_onset_pa": q8_result["experiment"]["paper_comparison"]["our_original_pipe_fine_first_tested_positive_onset_pa"],
            "baseline_pressure_sweep": spectra,
            "comparison_pressure_sweep": q8_result["experiment"]["pressure_sweep"],
            "baseline_unradiated_flow_sweep": entrance_flow_spectra,
            "comparison_unradiated_flow_sweep": q8_result["experiment"]["entrance_volume_velocity_sweep"],
            "interpretation": "Separate model sensitivity condition, not a fitted replacement for Q=35",
        }
    with (output_dir / "pressure-centroids.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["pressure_pa", "f0_hz", "centroid_hz",
                                                         "h4_over_h2", "h2_h4_rule_pass",
                                                         "internal_pressure_rms_pa", "wav_sha256"])
        writer.writeheader()
        writer.writerows(spectra)
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reed-q", type=float, default=35.0)
    parser.add_argument("--no-q8-comparison", action="store_true")
    args = parser.parse_args()
    result = run(args.output_dir, reed_q=args.reed_q,
                 include_q8_comparison=not args.no_q8_comparison and args.reed_q != 8.0)
    print(json.dumps({"gate_1": result["gate_1"]["status"],
                      "frequency_error_percent": result["measurements"]["frequency_error_percent"],
                      "result": str(args.output_dir / "result.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
