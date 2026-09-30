"""Small, dependency-free acoustic evaluator for gagaku physical-source WAVs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "gagaku-acoustic-evaluation-v0.3"


def _read_wav(path: Path) -> tuple[list[float], int, int]:
    with wave.open(str(path), "rb") as wav:
        channels, width, rate, frames, compression = (
            wav.getnchannels(), wav.getsampwidth(), wav.getframerate(),
            wav.getnframes(), wav.getcomptype(),
        )
        if compression != "NONE":
            raise ValueError(f"compressed WAV is unsupported: {compression}")
        raw = wav.readframes(frames)
    if channels < 1 or rate <= 0 or not raw:
        raise ValueError("WAV has no audio frames")
    if width not in (1, 2, 3, 4):
        raise ValueError(f"unsupported PCM sample width: {width} bytes")
    stride = channels * width
    if len(raw) % stride:
        raise ValueError("WAV payload is not aligned to complete frames")
    samples: list[float] = []
    scale = float(1 << (8 * width - 1))
    for offset in range(0, len(raw), stride):
        total = 0.0
        for channel in range(channels):
            start = offset + channel * width
            chunk = raw[start:start + width]
            if width == 1:
                value = chunk[0] - 128
            elif width == 2:
                value = struct.unpack("<h", chunk)[0]
            elif width == 3:
                integer = int.from_bytes(chunk, "little", signed=False)
                value = integer - (1 << 24) if integer & (1 << 23) else integer
            else:
                value = struct.unpack("<i", chunk)[0]
            total += value / scale
        samples.append(total / channels)
    return samples, rate, channels


def _estimate_f0(samples: list[float], rate: int, target_hz: float) -> float:
    # Autocorrelation on at most 1.5 s, decimated to keep the pure-Python CLI quick.
    factor = max(1, rate // 12000)
    x = samples[::factor]
    sr = rate / factor
    if len(x) < 128:
        raise ValueError("WAV is too short to estimate fundamental frequency")
    # Center a stable middle segment; discard DC before correlation.
    limit = min(len(x), int(sr * 1.5))
    start = max(0, (len(x) - limit) // 2)
    x = x[start:start + limit]
    mean = sum(x) / len(x)
    x = [v - mean for v in x]
    if max(x) - min(x) < 1e-8:
        raise ValueError("WAV is silent or has negligible amplitude")
    lo = max(2, int(sr / (target_hz * 1.25)))
    hi = min(len(x) // 2, int(sr / (target_hz * 0.75)))
    correlations: list[tuple[int, float]] = []
    for lag in range(lo, hi + 1):
        a = x[:-lag]
        b = x[lag:]
        numerator = sum(u * v for u, v in zip(a, b))
        denom = math.sqrt(sum(u * u for u in a) * sum(v * v for v in b))
        correlations.append((lag, numerator / denom if denom else -1.0))
    best_index = max(range(len(correlations)), key=lambda i: correlations[i][1])
    lag, _ = correlations[best_index]
    fractional_lag = float(lag)
    if 0 < best_index < len(correlations) - 1:
        left, center, right = (correlations[i][1] for i in (best_index - 1, best_index, best_index + 1))
        curvature = left - 2 * center + right
        if abs(curvature) > 1e-12:
            fractional_lag += max(-0.5, min(0.5, 0.5 * (left - right) / curvature))
    measured = sr / fractional_lag
    if not math.isfinite(measured) or measured <= 0:
        raise ValueError("could not estimate a valid fundamental frequency")
    return measured


def _goertzel_amplitude(samples: list[float], rate: int, frequency: float) -> float:
    n = len(samples)
    omega = 2.0 * math.pi * frequency / rate
    coeff = 2.0 * math.cos(omega)
    s1 = s2 = 0.0
    mean = sum(samples) / n
    # Hann window limits leakage from the finite analysis segment.
    for i, sample in enumerate(samples):
        window = 0.5 - 0.5 * math.cos(2 * math.pi * i / max(1, n - 1))
        value = (sample - mean) * window + coeff * s1 - s2
        s2, s1 = s1, value
    power = max(0.0, s1 * s1 + s2 * s2 - coeff * s1 * s2)
    window_sum = n / 2.0
    return 2.0 * math.sqrt(power) / window_sum


def _fft_magnitude_spectrum(samples: list[float], rate: float) -> tuple[list[float], list[float]]:
    """Return positive-frequency bins from a Hann-windowed radix-2 FFT."""
    if not samples:
        return [], []
    n = 1 << (len(samples) - 1).bit_length()
    mean = sum(samples) / len(samples)
    real = [0.0] * n
    imag = [0.0] * n
    denom = max(1, len(samples) - 1)
    for i, value in enumerate(samples):
        window = 0.5 - 0.5 * math.cos(2 * math.pi * i / denom)
        real[i] = (value - mean) * window
    # In-place bit-reversal permutation.
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            real[i], real[j] = real[j], real[i]
            imag[i], imag[j] = imag[j], imag[i]
    # Iterative Cooley-Tukey butterflies.
    size = 2
    while size <= n:
        angle = -2 * math.pi / size
        step_r, step_i = math.cos(angle), math.sin(angle)
        half = size // 2
        for base in range(0, n, size):
            wr, wi = 1.0, 0.0
            for offset in range(half):
                even = base + offset
                odd = even + half
                tr = wr * real[odd] - wi * imag[odd]
                ti = wr * imag[odd] + wi * real[odd]
                real[odd] = real[even] - tr
                imag[odd] = imag[even] - ti
                real[even] += tr
                imag[even] += ti
                wr, wi = wr * step_r - wi * step_i, wr * step_i + wi * step_r
        size *= 2
    freqs = [i * rate / n for i in range(n // 2 + 1)]
    magnitudes = [math.hypot(real[i], imag[i]) for i in range(n // 2 + 1)]
    return freqs, magnitudes


def _refine_f0_from_harmonics(samples: list[float], rate: int,
                              initial_f0_hz: float) -> tuple[float, dict[str, Any]]:
    """Refine autocorrelation f0 from observed H1-H6 peaks near its estimate.

    The reference pitch is deliberately not an input. A one-second Hann FFT
    provides sub-bin peak interpolation; a magnitude-weighted median of the
    observed partial frequencies divided by harmonic number limits the effect
    of a weak or unrelated individual peak. Search remains bounded to +/-1%
    around the initial autocorrelation estimate for every partial.
    """
    if not math.isfinite(initial_f0_hz) or initial_f0_hz <= 0:
        raise ValueError("initial f0 must be finite and positive")
    count = min(len(samples), rate)
    if count < 128:
        return initial_f0_hz, {"method": "autocorrelation_fallback_short_signal", "peaks": []}
    start = max(0, (len(samples) - count) // 2)
    x = samples[start:start + count]
    frequencies, magnitudes = _fft_magnitude_spectrum(x, float(rate))
    if len(frequencies) < 4:
        return initial_f0_hz, {"method": "autocorrelation_fallback_short_fft", "peaks": []}
    bin_hz = frequencies[1] - frequencies[0]
    candidates: list[tuple[float, float]] = []
    peak_records = []
    for harmonic in range(1, 7):
        predicted = harmonic * initial_f0_hz
        if predicted >= rate / 2:
            break
        lower = max(1, math.ceil(predicted * 0.99 / bin_hz))
        upper = min(len(magnitudes) - 2, math.floor(predicted * 1.01 / bin_hz))
        if lower > upper:
            continue
        peak_bin = max(range(lower, upper + 1), key=magnitudes.__getitem__)
        amplitude = magnitudes[peak_bin]
        if not math.isfinite(amplitude) or amplitude <= 0:
            continue
        interpolated_bin = float(peak_bin)
        if 0 < peak_bin < len(magnitudes) - 1:
            left, center, right = (math.log(max(magnitudes[index], 1e-300))
                                   for index in (peak_bin - 1, peak_bin, peak_bin + 1))
            curvature = left - 2 * center + right
            if abs(curvature) > 1e-12:
                interpolated_bin += max(-0.5, min(0.5, 0.5 * (left - right) / curvature))
        peak_hz = interpolated_bin * bin_hz
        estimate = peak_hz / harmonic
        candidates.append((estimate, amplitude))
        peak_records.append({"harmonic": harmonic, "peak_hz": peak_hz,
                             "f0_candidate_hz": estimate, "fft_peak_magnitude": amplitude})

    if not candidates:
        return initial_f0_hz, {"method": "autocorrelation_fallback_no_observed_harmonics",
                               "search_relative_width": 0.01, "peaks": []}
    candidates.sort(key=lambda item: item[0])
    total_weight = sum(weight for _, weight in candidates)
    midpoint = total_weight / 2
    cumulative = 0.0
    refined = candidates[-1][0]
    for candidate, weight in candidates:
        cumulative += weight
        if cumulative >= midpoint:
            refined = candidate
            break
    return refined, {
        "method": "magnitude_weighted_median_of_log_parabolic_h1_h6_fft_peaks",
        "search_relative_width": 0.01,
        "initial_autocorrelation_f0_hz": initial_f0_hz,
        "refined_f0_hz": refined,
        "observed_peak_count": len(peak_records),
        "peaks": peak_records,
    }


def _spectrum(samples: list[float], rate: int, f0: float) -> dict[str, Any]:
    # Keep the native sample rate: simple decimation aliases high-frequency energy
    # into the measured band and biases the spectral centroid downward.
    sr = float(rate)
    count = min(len(samples), int(rate * 1.0))
    start = max(0, (len(samples) - count) // 2)
    x = samples[start:start + count]
    frequencies, magnitudes = _fft_magnitude_spectrum(x, sr)
    # A single Goertzel probe at h*f0 becomes fragile at high h: a 0.3 Hz
    # fundamental estimate error displaces H4 by 1.2 Hz, exceeding a 1 s
    # Hann main lobe. Measure the strongest actual spectral bin in a narrow
    # neighborhood of each predicted harmonic, without changing the spectrum.
    harmonics = {}
    harmonic_peak_frequencies = {}
    bin_hz = sr / (2 * (len(frequencies) - 1)) if len(frequencies) > 1 else sr
    for h in range(1, 11):
        predicted = f0 * h
        if predicted >= sr / 2:
            break
        half_width_hz = max(2.0, 0.5 * h)
        left = max(1, math.ceil((predicted - half_width_hz) / bin_hz))
        right = min(len(magnitudes) - 1, math.floor((predicted + half_width_hz) / bin_hz))
        if left > right:
            continue
        peak_bin = max(range(left, right + 1), key=magnitudes.__getitem__)
        harmonics[str(h)] = 2.0 * magnitudes[peak_bin] / (len(x) / 2.0)
        harmonic_peak_frequencies[str(h)] = frequencies[peak_bin]
    if not harmonics:
        return {"harmonic_amplitudes": {}, "centroid_hz": None, "second_and_fourth_dominant": None}
    # Use all positive-frequency bins; sparse frequency probes can miss narrow peaks
    # and make the magnitude centroid depend on where the grid happens to land.
    weighted = sum(freq * mag for freq, mag in zip(frequencies[1:], magnitudes[1:]))
    total = sum(magnitudes[1:])
    centroid = weighted / total if total else None
    selected = [harmonics[k] for k in ("2", "4") if k in harmonics]
    strongest = max(harmonics.values())
    prominent = len(selected) == 2 and strongest > 0 and all(a >= strongest * 0.5 for a in selected)
    return {
        "harmonic_amplitudes": harmonics,
        "harmonic_peak_frequencies_hz": harmonic_peak_frequencies,
        "harmonic_method": "Hann-windowed FFT peak within max(2 Hz, 0.5 Hz x harmonic number) of h x estimated f0",
        "centroid_hz": centroid,
        "centroid_method": "Hann-windowed radix-2 FFT, magnitude-weighted positive-frequency bins",
        "second_and_fourth_dominant": prominent,
        "definition": "H2 and H4 each at least half the strongest of measured H1-H10 amplitudes",
    }


def evaluate(wav_path: Path, reference_path: Path) -> dict[str, Any]:
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    target = float(reference["target_hz"])
    tolerance = float(reference.get("frequency_tolerance_percent", 2.0))
    if not math.isfinite(target) or target <= 0 or not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("reference target_hz and frequency_tolerance_percent must be valid positive values")
    samples, rate, channels = _read_wav(wav_path)
    initial_f0 = _estimate_f0(samples, rate, target)
    f0, f0_refinement = _refine_f0_from_harmonics(samples, rate, initial_f0)
    error = abs(f0 - target) / target * 100.0
    spectrum = _spectrum(samples, rate, f0)
    qualitative = reference.get("qualitative_targets", {})
    criteria: list[dict[str, Any]] = [{
        "id": "fundamental_frequency_error",
        "status": "PASS" if error <= tolerance else "FAIL",
        "measurement": {"target_hz": target, "measured_hz": f0, "absolute_error_percent": error, "tolerance_percent": tolerance},
        "reason": f"absolute f0 error {'within' if error <= tolerance else 'exceeds'} {tolerance:g}% tolerance",
    }]
    for key, label in (
        ("threshold_depends_on_pipe_length", "pipe_length_threshold_dependence"),
        ("high_frequency_content_increases_with_pressure", "pressure_dependent_high_frequency_growth"),
    ):
        if qualitative.get(key, True):
            criteria.append({
                "id": label, "status": "UNVERIFIED", "measurement": None,
                "reason": "a single WAV cannot establish dependence across pipe lengths or blowing pressures; no matched sweep observations were provided",
            })
    if qualitative.get("second_and_fourth_harmonics_enhanced", True):
        observed = spectrum["second_and_fourth_dominant"]
        criteria.append({
            "id": "second_and_fourth_harmonics_enhanced",
            "status": ("PASS" if observed else "FAIL") if observed is not None else "UNVERIFIED",
            "measurement": {"harmonic_amplitudes": spectrum["harmonic_amplitudes"], "operational_rule": spectrum["definition"]},
            "reason": "single-WAV relative harmonic rule evaluated" if observed is not None else "harmonic observation unavailable",
        })
    # Criteria the evaluator cannot infer are explicitly surfaced instead of being silently skipped.
    statuses = {item["status"] for item in criteria}
    overall = "PASS" if criteria and statuses == {"PASS"} else "FAIL"
    digest = hashlib.sha256(wav_path.read_bytes()).hexdigest()
    try:
        commit = __import__("subprocess").run(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2],
            text=True, capture_output=True, check=True,
        ).stdout.strip()
    except Exception:
        commit = None
    return {
        "schema_version": SCHEMA_VERSION,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "reference": {"path": str(reference_path), "reference_id": reference.get("reference_id"), "target_hz": target, "source": reference.get("source"), "document": reference},
        "parameters": reference.get("paper_model_parameters", {}),
        "wav": {"path": str(wav_path), "sha256": digest, "sample_rate_hz": rate, "channels": channels, "duration_s": len(samples) / rate},
        "measurements": {"f0_hz": f0, "initial_f0_hz": initial_f0,
                         "refined_f0_hz": f0, "f0_refinement": f0_refinement,
                         "frequency_error_percent": error, "spectrum": spectrum},
        "gate_1": {"status": overall, "criteria": criteria, "overall_reason": "all required criteria passed" if overall == "PASS" else "one or more required criteria failed or remain unverified"},
        "provenance": {"evaluator": SCHEMA_VERSION,
                       "evaluator_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       "git_commit": commit, "python_version": sys.version.split()[0]},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a physical-source WAV against a JSON reference.")
    parser.add_argument("--wav", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate(args.wav, args.reference)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        spectrum_path = args.output.with_name(args.output.stem + ".spectrum.csv")
        result["artifacts"] = {"spectrum_csv": str(spectrum_path)}
        with spectrum_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["harmonic", "frequency_hz", "relative_amplitude"])
            for harmonic, amplitude in result["measurements"]["spectrum"]["harmonic_amplitudes"].items():
                writer.writerow([harmonic,
                                 result["measurements"]["spectrum"]["harmonic_peak_frequencies_hz"][harmonic],
                                 amplitude])
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, json.JSONDecodeError, wave.Error, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
