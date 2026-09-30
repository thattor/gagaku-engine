"""Reproducible sample-rate and onset-duration diagnostics for the sho PoC.

This records measurements for comparison; it does not change acceptance criteria
or interpret evaluator Gate 1 results as validation of the model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from features.gagaku import evaluate, sho_one_pipe  # noqa: E402

REFERENCE = ROOT / "features/gagaku/refs/hikichi_2003_ichi.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rms(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def eval_cli(wav_path: Path, result_path: Path) -> dict[str, Any]:
    """Run the evaluator's public CLI and return its written JSON document."""
    command = [sys.executable, str(ROOT / "features/gagaku/evaluate.py"),
               "--wav", str(wav_path), "--reference", str(REFERENCE),
               "--output", str(result_path)]
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(result_path.read_text(encoding="utf-8"))


def record_render(output_dir: Path, label: str, parameters: dict[str, Any]) -> dict[str, Any]:
    signal = sho_one_pipe.render(**parameters)
    rate = parameters["sample_rate_hz"]
    wav_path = output_dir / f"{label}.wav"
    wav_record = sho_one_pipe.write_wav(wav_path, signal, rate)
    evaluation_path = output_dir / f"{label}.evaluation.json"
    result = eval_cli(wav_path, evaluation_path)
    raw_spectrum = evaluate._spectrum(signal, rate, result["measurements"]["f0_hz"])
    return {
        "id": label,
        "parameters": parameters,
        "wav": wav_record,
        "evaluation": {
            "path": str(evaluation_path),
            "schema_version": result["schema_version"],
            "f0_hz": result["measurements"]["f0_hz"],
            "h2_amplitude": result["measurements"]["spectrum"]["harmonic_amplitudes"].get("2"),
            "h4_amplitude": result["measurements"]["spectrum"]["harmonic_amplitudes"].get("4"),
            "h4_over_h2": _ratio(result["measurements"]["spectrum"]["harmonic_amplitudes"].get("4"),
                                  result["measurements"]["spectrum"]["harmonic_amplitudes"].get("2")),
            "spectral_centroid_hz": result["measurements"]["spectrum"]["centroid_hz"],
            "gate_1_status_recorded_without_acceptance_claim": result["gate_1"]["status"],
        },
        "raw_internal_signal_rms_pa": rms(signal),
        "raw_float_spectral_centroid_hz": raw_spectrum["centroid_hz"],
        "raw_float_spectrum_note": "Same spectral algorithm and PCM-estimated f0 applied before PCM16 quantization; diagnostic only",
        "raw_internal_signal_peak_pa": max(abs(x) for x in signal),
    }


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def onset_rms_windows(signal: list[float], rate: int, seconds: float) -> dict[str, Any]:
    """Fixed early and late 0.75 s windows, clipped only for 1.5 s renders."""
    early = (0.75, 1.5)
    late = (max(0.0, seconds - 0.75), seconds)

    def measure(window: tuple[float, float]) -> dict[str, float]:
        start = min(len(signal), round(window[0] * rate))
        end = min(len(signal), round(window[1] * rate))
        return {"start_s": window[0], "end_s": window[1], "rms_pa": rms(signal[start:end])}

    return {"early_window": measure(early), "late_window": measure(late)}


def run(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    common = {"pipe_length_m": 0.241, "pressure_pa": 800.0,
              "reflection_loss": 0.98, "output_signal": "pipe_pressure"}
    convergence = []
    for q in (35.0, 8.0):
        for rate in (48000, 96000, 192000):
            parameters = {**common, "reed_q": q, "seconds": 3.0,
                          "sample_rate_hz": rate,
                          # Keep the reflection's physical Gaussian width at its 48 kHz value.
                          "reflection_sigma_samples": rate / 48000.0}
            convergence.append(record_render(output_dir, f"convergence-q{int(q)}-{rate}", parameters))

    onset = []
    for q, pressures in ((35.0, (100.0, 125.0)), (8.0, (350.0, 375.0))):
        for pressure in pressures:
            for seconds in (1.5, 6.0):
                ramps = (0.05,) if seconds == 1.5 else (0.05, 3.0)
                for ramp in ramps:
                    parameters = {"pressure_pa": pressure, "pipe_length_m": 0.241,
                                  "seconds": seconds, "sample_rate_hz": 48000,
                                  "reed_q": q, "reflection_loss": 0.98,
                                  "reflection_sigma_samples": 1.0,
                                  "pressure_ramp_seconds": ramp,
                                  "output_signal": "pipe_pressure"}
                    signal = sho_one_pipe.render(**parameters)
                    label = f"onset-q{int(q)}-p{int(pressure)}-t{seconds:g}-r{ramp:g}"
                    wav_path = output_dir / f"{label}.wav"
                    wav_record = sho_one_pipe.write_wav(wav_path, signal, 48000)
                    evaluation_path = output_dir / f"{label}.evaluation.json"
                    result = eval_cli(wav_path, evaluation_path)
                    onset.append({
                        "id": label, "parameters": parameters, "wav": wav_record,
                        "raw_internal_signal_rms_pa": rms(signal),
                        "windows": onset_rms_windows(signal, 48000, seconds),
                        "evaluation": {"path": str(evaluation_path),
                                       "f0_hz": result["measurements"]["f0_hz"],
                                       "spectral_centroid_hz": result["measurements"]["spectrum"]["centroid_hz"],
                                       "gate_1_status_recorded_without_acceptance_claim": result["gate_1"]["status"]},
                    })

    try:
        checkout_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                         check=True, text=True, capture_output=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        checkout_commit = None
    source_commit = os.environ.get("GAGAKU_SOURCE_COMMIT") or checkout_commit
    manifest = {
        "schema_version": "gagaku-diagnostics-v0.1",
        "purpose": "numerical sample-rate convergence and onset-duration sensitivity diagnostics",
        "acceptance": "descriptive only; no criterion adjustment and no Gate 1 pass claim",
        "source_commit": source_commit,
        "checkout_commit": checkout_commit,
        "source_hashes": {
            "sho_one_pipe_py_sha256": sha256(ROOT / "features/gagaku/sho_one_pipe.py"),
            "evaluate_py_sha256": sha256(ROOT / "features/gagaku/evaluate.py"),
            "diagnostics_py_sha256": sha256(Path(__file__)),
            "reference_sha256": sha256(REFERENCE),
        },
        "reference": {"path": str(REFERENCE), "reference_id": json.loads(REFERENCE.read_text())["reference_id"]},
        "convergence_experiment": {
            "fixed": {"pressure_pa": 800.0, "pipe_length_m": 0.241, "duration_s": 3.0,
                      "reflection_loss": 0.98, "reflection_sigma_physical_samples_at_48khz": 1.0},
            "sample_rates_hz": [48000, 96000, 192000], "reed_q_values": [35.0, 8.0],
            "width_scaling": "reflection_sigma_samples = sample_rate_hz / 48000",
            "runs": convergence,
        },
        "onset_duration_experiment": {
            "fixed_sample_rate_hz": 48000, "pipe_length_m": 0.241,
            "q_pressure_pairs_pa": [{"reed_q": 35.0, "pressures": [100.0, 125.0]},
                                     {"reed_q": 8.0, "pressures": [350.0, 375.0]}],
            "durations_s": [1.5, 6.0], "pressure_ramps_s": [0.05, 3.0],
            "early_window_s": [0.75, 1.5], "late_window": "final 0.75 s",
            "window_note": "The early window is fixed at 0.75-1.5 s. With a 3 s ramp it contains only the ramp-up; the 0.05 s ramp is already at full pressure. The late window for a 1.5 s render coincides with the early window.",
            "runs": onset,
        },
    }
    path = output_dir / "diagnostics.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    manifest = run(args.output_dir)
    print(json.dumps({"diagnostics": str(args.output_dir / "diagnostics.json"),
                      "convergence_runs": len(manifest["convergence_experiment"]["runs"]),
                      "onset_runs": len(manifest["onset_duration_experiment"]["runs"]),
                      "source_commit": manifest["source_commit"],
                      "checkout_commit": manifest["checkout_commit"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
