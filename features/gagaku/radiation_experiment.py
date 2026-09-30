"""Compare a spherical exterior-pressure observation for the one-pipe sho PoC.

All results are EXPERIMENTAL_UNVALIDATED. The runner leaves the evaluator and its
criteria unchanged and records the original Gate 1 IDs as a separate diagnostic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from features.gagaku.experiment import rms  # noqa: E402
from features.gagaku.sho_one_pipe import PAPER_DOI, PAPER_PARAMETERS, render, write_wav  # noqa: E402

REFERENCE = ROOT / "features/gagaku/refs/hikichi_2003_ichi.json"
PRESSURES_PA = (400, 600, 800)
ONSET_PRESSURES_PA = (100, 125, 300, 350, 375, 400, 450, 600)
LENGTHS_M = (0.142, 0.241, 0.34, 0.425, 0.567)
COARSE_PRESSURES_PA = (100, 200, 300, 400, 600, 800, 1000)
SAMPLE_RATE_HZ = 48000
EXTERIOR_DISTANCE_M = 0.05
ONSET_RMS_THRESHOLD_PA = 1.0
CAUSSE_LOW_KA_REACTIVE_COEFFICIENT = 0.6133


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_wav(wav_path: Path, output_path: Path) -> dict[str, Any]:
    """Use the public evaluator CLI unchanged and return its JSON output."""
    subprocess.run(
        [sys.executable, "-m", "features.gagaku.evaluate", "--wav", str(wav_path),
         "--reference", str(REFERENCE), "--output", str(output_path)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return json.loads(output_path.read_text(encoding="utf-8"))


def measure_observation(output_dir: Path, q: float, pressure: int, signal_name: str,
                        radiation_radius_m: float | None) -> dict[str, Any]:
    signal = render(
        pressure_pa=pressure, pipe_length_m=0.241, seconds=3.0,
        sample_rate_hz=SAMPLE_RATE_HZ, reed_q=q, additional_mass_ratio=0.0,
        pipe_model="spherical", output_signal=signal_name,
        exterior_distance_m=EXTERIOR_DISTANCE_M,
        radiation_radius_m=radiation_radius_m,
    )
    unit = "m3/s" if signal_name == "entrance_volume_velocity" else "Pa"
    label = f"q{q:g}-{pressure}pa-{signal_name}"
    wav_path = output_dir / f"{label}.wav"
    wav = write_wav(wav_path, signal, SAMPLE_RATE_HZ, physical_unit=unit)
    evaluation_path = output_dir / f"{label}.evaluation.json"
    evaluation = evaluate_wav(wav_path, evaluation_path)
    spectrum = evaluation["measurements"]["spectrum"]
    harmonics = spectrum["harmonic_amplitudes"]
    h2, h4 = harmonics.get("2"), harmonics.get("4")
    return {
        "reed_q": q,
        "pressure_pa": pressure,
        "signal": signal_name,
        "wav": wav,
        "evaluation_path": str(evaluation_path),
        "measurements": {
            "f0_hz": evaluation["measurements"]["f0_hz"],
            "frequency_error_percent": evaluation["measurements"]["frequency_error_percent"],
            "spectral_centroid_hz": spectrum["centroid_hz"],
            "harmonic_amplitudes": harmonics,
            "h4_over_h2": h4 / h2 if h2 else None,
            "h2_h4_rule_pass": spectrum["second_and_fourth_dominant"],
        },
        "unchanged_evaluator_gate_status": evaluation["gate_1"]["status"],
    }


def measure_onset(output_dir: Path, q: float, pressure: int, length: float,
                  *, include_fine: bool, radiation_radius_m: float | None) -> dict[str, Any]:
    signal = render(
        pressure_pa=pressure, pipe_length_m=length, seconds=1.5,
        sample_rate_hz=SAMPLE_RATE_HZ, reed_q=q, additional_mass_ratio=0.0,
        pipe_model="spherical", output_signal="pipe_pressure",
        exterior_distance_m=EXTERIOR_DISTANCE_M,
        radiation_radius_m=radiation_radius_m,
    )
    # Retain the existing experiment's centered steady-window RMS convention.
    steady_rms = rms(signal[len(signal) // 2:])
    return {
        "reed_q": q,
        "pipe_length_m": length,
        "pressure_pa": pressure,
        "pipe_model": "spherical",
        "radiation_radius_m": radiation_radius_m,
        "output_signal": "pipe_pressure",
        "duration_s": 1.5,
        "steady_window_s": [0.75, 1.5],
        "raw_internal_p2_rms_pa": steady_rms,
        "onset_threshold_pa": ONSET_RMS_THRESHOLD_PA,
        "oscillates": steady_rms >= ONSET_RMS_THRESHOLD_PA,
        "grid": "fine_original_length" if include_fine else "coarse_by_length",
    }


def run(output_dir: Path, q: float, radiation_radius_m: float | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    observations = [measure_observation(output_dir, q, pressure, signal_name, radiation_radius_m)
                    for pressure in PRESSURES_PA
                    for signal_name in ("pipe_pressure", "entrance_volume_velocity", "radiation_pressure")]
    radiation = {row["pressure_pa"]: row for row in observations
                 if row["signal"] == "radiation_pressure"}
    onset = []
    coarse_by_length = []
    for length in LENGTHS_M:
        rows = [measure_onset(output_dir, q, pressure, length, include_fine=False,
                              radiation_radius_m=radiation_radius_m)
                for pressure in COARSE_PRESSURES_PA]
        first = next((row["pressure_pa"] for row in rows if row["oscillates"]), None)
        coarse_by_length.append({
            "pipe_length_m": length,
            "first_tested_oscillating_pressure_pa": first,
            "measurements": rows,
        })
        onset.extend(rows)
    fine_original = [measure_onset(output_dir, q, pressure, 0.241, include_fine=True,
                                   radiation_radius_m=radiation_radius_m)
                     for pressure in ONSET_PRESSURES_PA]
    onset.extend(fine_original)
    fine_first = next((row["pressure_pa"] for row in fine_original if row["oscillates"]), None)

    eval_800 = json.loads(Path(radiation[800]["evaluation_path"]).read_text(encoding="utf-8"))
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    target = float(reference["target_hz"])
    frequency_error = radiation[800]["measurements"]["frequency_error_percent"]
    centroids = [radiation[p]["measurements"]["spectral_centroid_hz"] for p in PRESSURES_PA]
    centroid_growth = all(value is not None for value in centroids) and all(
        right > left for left, right in zip(centroids, centroids[1:]))
    thresholds = [row["first_tested_oscillating_pressure_pa"] for row in coarse_by_length]
    length_trend = len(set(thresholds)) > 1
    h2h4 = radiation[800]["measurements"]["h2_h4_rule_pass"]
    pipe_radius_m = PAPER_PARAMETERS["pipe_radius_m"]
    effective_radiation_radius_m = pipe_radius_m if radiation_radius_m is None else radiation_radius_m
    area_ratio_beta = pipe_radius_m ** 2 / (4 * effective_radiation_radius_m ** 2)
    criteria = [
        {
            "id": "fundamental_frequency_error",
            "status": "PASS" if frequency_error <= float(reference.get("frequency_tolerance_percent", 2.0)) else "FAIL",
            "measurement": {"target_hz": target, "measured_hz": radiation[800]["measurements"]["f0_hz"],
                            "absolute_error_percent": frequency_error,
                            "tolerance_percent": float(reference.get("frequency_tolerance_percent", 2.0)),
                            "observation": "radiation_pressure at 800 Pa"},
        },
        {
            "id": "pipe_length_threshold_dependence",
            "status": "PASS" if length_trend else "FAIL",
            "measurement": [{"pipe_length_m": row["pipe_length_m"],
                             "first_tested_oscillating_pressure_pa": row["first_tested_oscillating_pressure_pa"]}
                            for row in coarse_by_length],
            "rule": "the five coarse first-onset pressures must not all be equal; each onset uses raw internal p2 steady RMS >= 1 Pa",
        },
        {
            "id": "pressure_dependent_high_frequency_growth",
            "status": "PASS" if centroid_growth else "FAIL",
            "measurement": {"pressures_pa": list(PRESSURES_PA), "radiation_pressure_centroids_hz": centroids},
            "rule": "radiation-pressure spectral centroid must increase strictly at 400, 600, and 800 Pa",
        },
        {
            "id": "second_and_fourth_harmonics_enhanced",
            "status": "PASS" if h2h4 is True else "FAIL",
            "measurement": radiation[800]["measurements"]["harmonic_amplitudes"],
            "rule": eval_800["measurements"]["spectrum"]["definition"],
        },
    ]
    gate_status = "PASS" if all(item["status"] == "PASS" for item in criteria) else "FAIL"

    source_paths = {
        "radiation_experiment.py": Path(__file__),
        "sho_one_pipe.py": ROOT / "features/gagaku/sho_one_pipe.py",
        "spherical_load.py": ROOT / "features/gagaku/spherical_load.py",
        "evaluate.py": ROOT / "features/gagaku/evaluate.py",
        "experiment.py": ROOT / "features/gagaku/experiment.py",
        "reference.json": REFERENCE,
    }
    try:
        checkout_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                         check=True, text=True, capture_output=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        checkout_commit = None
    result = {
        "schema_version": "gagaku-radiation-experiment-v0.1",
        "validation_status": "EXPERIMENTAL_UNVALIDATED",
        "gate_1": {
            "status": gate_status,
            "measurement_status": gate_status,
            "criteria": criteria,
            "interpretation": "Experimental diagnostic only. These four statuses do not replace or modify the existing Gate 1 result.",
        },
        "physical_model_validation_status": "UNVALIDATED",
        "acceptance_status": "UNVERIFIED",
        "experiment": {
            "issue": 53,
            "paper_doi": PAPER_DOI,
            "condition": "Q35_baseline" if q == 35.0 else f"Q{q:g}_sensitivity",
            "radiation_condition": "full_sphere" if radiation_radius_m is None else "low_frequency_matched_sphere",
            "is_primary_gate_condition": False,
            "model": "one-pipe reed/slit/pipe model with spherical exterior radiation observation",
            "experimental_unvalidated_note": "The spherical exterior-pressure implementation is a PoC observation model and has not been checked against a calibrated external microphone or paper waveform. Do not treat its Gate-like criteria as accepted model validation.",
            "radiation_approximation": {
                "geometry": "full sphere",
                "sphere_radius_m": effective_radiation_radius_m,
                "radiating_area_m2": 4.0 * 3.141592653589793 * effective_radiation_radius_m ** 2,
                "area_ratio_beta": area_ratio_beta,
                "status": "independent experimental approximation; not the exact Hikichi/Causse unflanged Levine-Schwinger radiation model",
                "low_frequency_match": None if radiation_radius_m is None else {
                    "source": "Causse et al. 1984, Section II.B; DOI 10.1121/1.390402",
                    "unflanged_pipe_normalized_load_leading_terms": {
                        "real_kr_squared_coefficient": 0.25,
                        "imaginary_kr_coefficient": CAUSSE_LOW_KA_REACTIVE_COEFFICIENT,
                    },
                    "sphere_radius_rule": "a = r / (4 * 0.6133); chosen from the low-ka reactive coefficient, independently of target/result fitting",
                    "matching_scope": "This sphere matches the first two low-ka expansion terms, but remains an experimental lumped approximation and is not the exact Levine-Schwinger model.",
                },
            },
            "parameters": {
                "sample_rate_hz": SAMPLE_RATE_HZ,
                "pipe_length_m": 0.241,
                "pressures_pa": list(PRESSURES_PA),
                "reed_q": q,
                "additional_mass_ratio": 0.0,
                "pipe_model": "spherical",
                "radiation_radius_m": radiation_radius_m,
                "area_ratio_beta": area_ratio_beta,
                "exterior_distance_m": EXTERIOR_DISTANCE_M,
                "pressure_ramp_seconds": 0.05,
                "render_duration_s": 3.0,
            },
            "paper_model_parameters": PAPER_PARAMETERS,
            "implementation_assumptions": [
                "Spherical exterior radiation at 5 cm is an independent full-sphere approximation and is not the exact unflanged Levine-Schwinger model.",
                "The matched-radius condition chooses a=pipe_radius/(4*0.6133) from the Causse et al. 1984 Section II.B low-ka reactive coefficient; no measured target or resulting spectrum is fitted.",
                "The spherical path has no fitted wall-loss parameter; fractional propagation uses linear interpolation on the discrete sample grid.",
                "Every observation WAV is independently normalized to PCM16 by write_wav; WAV amplitude is not calibrated pressure.",
                "The unchanged evaluator is run on pipe_pressure, entrance_volume_velocity, and radiation_pressure WAVs; only radiation_pressure supplies the frequency, centroid, and H2/H4 diagnostic criteria.",
                "Onset remains the existing 1.5 s independent cold start and 1 Pa RMS rule, measured on raw internal p2 over 0.75-1.5 s.",
                "The coarse length sweep is evaluated separately at each of five pipe lengths; the fine onset grid is at original 0.241 m only.",
            ],
            "observation_sweep": observations,
            "onset_protocol": {
                "duration_s": 1.5,
                "sample_rate_hz": SAMPLE_RATE_HZ,
                "steady_window_s": [0.75, 1.5],
                "classification": "raw internal p2 RMS >= 1 Pa",
                "coarse_pressure_grid_pa": list(COARSE_PRESSURES_PA),
                "coarse_pipe_lengths_m": list(LENGTHS_M),
                "fine_original_length_pressure_grid_pa": list(ONSET_PRESSURES_PA),
                "fine_pipe_length_m": 0.241,
                "measurements": onset,
                "coarse_by_length": coarse_by_length,
                "fine_original_length_first_tested_oscillating_pressure_pa": fine_first,
            },
        },
        "provenance": {
            "source_commit": os.environ.get("GAGAKU_SOURCE_COMMIT") or checkout_commit,
            "checkout_commit": checkout_commit,
            "source_sha256": {name: file_hash(path) for name, path in source_paths.items()},
            "reference_id": reference.get("reference_id"),
            "reference_sha256": file_hash(REFERENCE),
            "evaluator_cli": "python -m features.gagaku.evaluate --wav ... --reference ... --output ...",
        },
    }
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--low-frequency-matched-radius", action="store_true",
                        help="Use a sphere radius matched to Causse's low-ka reactive coefficient")
    args = parser.parse_args(argv)
    matched_radius = (PAPER_PARAMETERS["pipe_radius_m"] /
                      (4 * CAUSSE_LOW_KA_REACTIVE_COEFFICIENT)) if args.low_frequency_matched_radius else None
    baseline = run(args.output_dir, 35.0, matched_radius)
    q8 = run(args.output_dir / "q8", 8.0, matched_radius)
    baseline["experiment"]["q_sensitivity"] = {
        "baseline_reed_q": 35.0,
        "radiation_condition": baseline["experiment"]["radiation_condition"],
        "comparison_reed_q": 8.0,
        "comparison_result": str(args.output_dir / "q8" / "result.json"),
        "comparison_gate_like_status_experimental_unvalidated": q8["gate_1"]["status"],
        "interpretation": "Separate sensitivity condition; not a fitted replacement for Q35.",
    }
    (args.output_dir / "result.json").write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"validation_status": "EXPERIMENTAL_UNVALIDATED",
                      "radiation_condition": baseline["experiment"]["radiation_condition"],
                      "q35_gate_like_status": baseline["gate_1"]["status"],
                      "q8_gate_like_status": q8["gate_1"]["status"],
                      "result": str(args.output_dir / "result.json"),
                      "q8_result": str(args.output_dir / "q8" / "result.json")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
