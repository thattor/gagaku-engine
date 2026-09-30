"""Bounded sensitivity test of the assumed pipe reflection magnitude.

This tests an unspecified model parameter, not a measured tube impedance or
an exterior radiation model. Gate 1 and its harmonic rule are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from features.gagaku import evaluate as evaluator
from features.gagaku import sho_one_pipe as solver
from features.gagaku.experiment import REFERENCE, rms


REFLECTION_MAGNITUDES = (0.98, 0.94, 0.90)
REED_Q_VALUES = (35.0, 8.0)


def _fingerprint(path: Path) -> dict:
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for reed_q in REED_Q_VALUES:
        for magnitude in REFLECTION_MAGNITUDES:
            name = f"q{reed_q:g}-reflection-{magnitude:.2f}"
            parameters = {"pressure_pa": 800.0, "seconds": 3.0,
                          "sample_rate_hz": 48000, "reed_q": reed_q,
                          "pipe_length_m": 0.241,
                          "reflection_loss": magnitude,
                          "reflection_sigma_samples": 1.0,
                          "additional_mass_ratio": 0.0,
                          "pressure_ramp_seconds": 0.05,
                          "output_signal": "pipe_pressure"}
            signal = solver.render(**parameters)
            wav = solver.write_wav(output_dir / f"{name}-800pa.wav", signal, 48000)
            measured = evaluator.evaluate(Path(wav["path"]), REFERENCE)
            evaluation_path = output_dir / f"{name}-800pa-evaluation.json"
            evaluation_path.write_text(json.dumps(measured, ensure_ascii=False, indent=2) + "\n")
            spectrum = measured["measurements"]["spectrum"]
            harmonics = spectrum["harmonic_amplitudes"]
            onset_parameters = {**parameters, "pressure_pa": 375.0, "seconds": 1.5}
            probe = solver.render(**onset_parameters)
            probe_rms = rms(probe[len(probe) // 2:])
            steady = signal[len(signal) // 2:]
            rows.append({
                "parameters": parameters,
                "wav": wav,
                "evaluation": _fingerprint(evaluation_path),
                "f0_hz": measured["measurements"]["f0_hz"],
                "centroid_hz": spectrum["centroid_hz"],
                "h4_over_h2": harmonics["4"] / harmonics["2"] if harmonics["2"] else None,
                "h2_h4_rule_pass": spectrum["second_and_fourth_dominant"],
                "internal_pressure_rms_pa": rms(steady),
                "internal_pressure_mean_pa": sum(steady) / len(steady),
                "onset_probe": {"parameters": onset_parameters,
                                "steady_window_s": [0.75, 1.5],
                                "internal_pressure_rms_pa": probe_rms,
                                "oscillates_at_1_pa_rms": probe_rms >= 1.0},
            })
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    result = {
        "schema_version": "sho-reflection-sensitivity-v1",
        "source_commit": os.environ.get("GAGAKU_SOURCE_COMMIT", commit),
        "checkout_commit": commit,
        "source_files": [_fingerprint(Path(__file__)),
                         _fingerprint(Path(solver.__file__)),
                         _fingerprint(Path(evaluator.__file__)),
                         _fingerprint(REFERENCE)],
        "source_doi": solver.PAPER_DOI,
        "reflection_parameter_meaning": "Magnitude of the negative Gaussian round-trip reflection; smaller values mean more loss",
        "conditions": rows,
        "analysis_cautions": [
            "All WAVs are synthesized internal pipe pressure, not recordings or exterior radiation.",
            "The paper does not specify numerical Gaussian width or reflection magnitude. These conditions are sensitivity assumptions, not identified physical fits.",
            "The unchanged single-WAV evaluator leaves pressure and length trends unverified; no overall Gate 1 pass can follow from this diagnostic.",
            "A fixed 375 Pa, 1.5 s cold-start probe uses the existing 1 Pa RMS criterion. It is not a measured onset threshold or a gradual-pressure experiment.",
            "Constant reflection magnitude below one also changes the DC pipe load. A physically identified frequency-dependent tube and termination model remains a separate experiment.",
            "Do not select a reflection magnitude solely to make target harmonics or onset pass.",
        ],
    }
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output_dir)
    print(json.dumps({"result": str(args.output_dir / "result.json"),
                      "conditions": len(result["conditions"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
