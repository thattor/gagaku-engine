"""One-pipe sho experiment based on Hikichi et al. (JASA 2003), Eqs. 1-3.

This computes a coupled reed, slit flow, and delayed pipe-pressure reflection.
The default internal pipe pressure is an audible proxy. An experimental full
sphere load can produce exterior pressure; it is not the paper's exact load
and has no measured reference waveform validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import wave


PAPER_DOI = "10.1121/1.1534605"
PAPER_PARAMETERS = {
    "reed_length_m": 0.01,
    "reed_width_m": 0.002,
    "reed_thickness_m": 0.0003,
    "reed_gap_m": 0.00001,
    "reed_natural_frequency_hz": 470.0,
    "reed_density_kg_m3": 8000.0,
    "pipe_radius_m": 0.0035,
    "air_density_kg_m3": 1.2,
    "sound_speed_m_s": 340.0,
    "air_channel_length_m": 0.001,
    "flow_contraction_coefficient": 0.61,
}


def render(
    *,
    pressure_pa: float = 800.0,
    pipe_length_m: float = 0.241,
    seconds: float = 3.0,
    sample_rate_hz: int = 48000,
    reed_q: float = 35.0,
    additional_mass_ratio: float = 0.0,
    reflection_loss: float = 0.98,
    reflection_sigma_samples: float = 1.0,
    output_signal: str = "pipe_pressure",
    pressure_ramp_seconds: float = 0.05,
    pipe_model: str = "gaussian",
    exterior_distance_m: float = 0.05,
    radiation_radius_m: float | None = None,
) -> list[float]:
    """Return internal pressure, entrance flow, or experimental exterior pressure.

    The paper specifies a Gaussian-type pipe reflection but does not give its
    width/loss in the accessible text. Those parameters are explicit PoC
    assumptions, not attributed measurements. A 50 ms pressure ramp supplies
    a deterministic initial perturbation; no sinusoidal source is injected.
    pipe_model='spherical' instead couples a full sphere (area four times the
    pipe area); Gaussian loss/width are unused in that separate experiment.
    """
    if not (0 <= pressure_pa <= 1000 and pipe_length_m > 0 and seconds > 0):
        raise ValueError("Pressure, pipe length, and duration are out of range")
    if not (sample_rate_hz >= 48000 and reed_q > 0 and 0 <= additional_mass_ratio <= 0.3):
        raise ValueError("Unsupported sample rate or reed parameters")
    if not (0 < reflection_loss < 1 and reflection_sigma_samples > 0):
        raise ValueError("Reflection loss and width must be positive and finite")
    if pipe_model not in ("gaussian", "spherical"):
        raise ValueError("Unsupported pipe model")
    if output_signal not in ("pipe_pressure", "entrance_volume_velocity", "radiation_pressure"):
        raise ValueError("Unsupported model output signal")
    if output_signal == "radiation_pressure" and pipe_model != "spherical":
        raise ValueError("Radiation pressure requires an explicit radiation load")
    radius = PAPER_PARAMETERS["pipe_radius_m"] if radiation_radius_m is None else radiation_radius_m
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("Radiation radius must be finite and positive")
    if not math.isfinite(exterior_distance_m) or exterior_distance_m <= radius:
        raise ValueError("Exterior distance must exceed the sphere radius")
    if not math.isfinite(pressure_ramp_seconds) or pressure_ramp_seconds <= 0:
        raise ValueError("Pressure ramp duration must be finite and positive")

    p = PAPER_PARAMETERS
    dt = 1 / sample_rate_hz
    omega = 2 * math.pi * p["reed_natural_frequency_hz"]
    impedance = p["air_density_kg_m3"] * p["sound_speed_m_s"] / (
        math.pi * p["pipe_radius_m"] ** 2
    )
    # 1.5 * W * L / m from Eq. 1, with m = rho_r * W * L * h * (1+alpha).
    reed_force = 1.5 / (
        p["reed_density_kg_m3"]
        * p["reed_thickness_m"]
        * (1 + additional_mass_ratio)
    )
    # Eq. 3: U_in = U + 0.4 W L dx/dt.
    reed_swept_flow = 0.4 * p["reed_width_m"] * p["reed_length_m"]
    delay = 2 * pipe_length_m / p["sound_speed_m_s"] * sample_rate_hz
    weights = [
        (i, math.exp(-0.5 * ((i - delay) / reflection_sigma_samples) ** 2))
        for i in range(max(1, int(delay - 4 * reflection_sigma_samples)),
                       int(delay + 4 * reflection_sigma_samples) + 2)
    ]
    total_weight = sum(weight for _, weight in weights)
    taps = [(i, -reflection_loss * weight / total_weight) for i, weight in weights]
    if pipe_model == "spherical":
        from features.gagaku.spherical_load import SphericalReflection
        reflection_filter = SphericalReflection(sample_rate_hz=sample_rate_hz,
            pipe_length_m=pipe_length_m, pipe_radius_m=p["pipe_radius_m"],
            radiation_radius_m=radius,
            sound_speed_m_s=p["sound_speed_m_s"])

    count = round(seconds * sample_rate_hz)
    outgoing_history = [0.0] * (count + 2)
    pipe_pressure = []
    x = velocity = flow_speed = 0.0

    def slit_area(displacement: float) -> float:
        gap = p["reed_gap_m"]
        return (
            p["reed_width_m"] * math.hypot(displacement, gap)
            + 2 * p["reed_length_m"] * math.hypot(0.4 * displacement, gap)
        )

    def derivatives(
        displacement: float, reed_velocity: float, air_speed: float,
        driving_pressure: float, reflected_pressure: float,
    ) -> tuple[float, float, float]:
        area = slit_area(displacement)
        flow = p["flow_contraction_coefficient"] * area * air_speed
        pressure = impedance * (flow + reed_swept_flow * reed_velocity) + reflected_pressure
        reed_acceleration = (
            reed_force * (driving_pressure - pressure)
            - omega / reed_q * reed_velocity - omega**2 * displacement
        )
        # Eq. 2 in slit-velocity form: rho*delta*dy/dt = p-p2-rho*y|y|/2.
        flow_acceleration = (
            driving_pressure - pressure
            - p["air_density_kg_m3"] * air_speed * abs(air_speed) / 2
        ) / (p["air_density_kg_m3"] * p["air_channel_length_m"])
        return reed_velocity, reed_acceleration, flow_acceleration

    for index in range(count):
        driving = pressure_pa * min(1.0, index / (sample_rate_hz * pressure_ramp_seconds))
        if pipe_model == "spherical":
            reflected, reflection_state = reflection_filter.predict(outgoing_history, index)
            next_reflected, _ = reflection_filter.predict(outgoing_history, index + 1, reflection_state)
            reflection_filter.commit(reflection_state)
        else:
            reflected = sum(weight * outgoing_history[index - offset]
                            for offset, weight in taps if index >= offset)
            next_reflected = sum(weight * outgoing_history[index + 1 - offset]
                                 for offset, weight in taps if index + 1 >= offset)
        a = derivatives(x, velocity, flow_speed, driving, reflected)
        b = derivatives(x + dt * a[0] / 2, velocity + dt * a[1] / 2,
                        flow_speed + dt * a[2] / 2, driving,
                        (reflected + next_reflected) / 2)
        c = derivatives(x + dt * b[0] / 2, velocity + dt * b[1] / 2,
                        flow_speed + dt * b[2] / 2, driving,
                        (reflected + next_reflected) / 2)
        d = derivatives(x + dt * c[0], velocity + dt * c[1], flow_speed + dt * c[2],
                        driving, next_reflected)
        flow_in = (p["flow_contraction_coefficient"] * slit_area(x) * flow_speed
                   + reed_swept_flow * velocity)
        current_pressure = impedance * flow_in + reflected
        outgoing_history[index] = current_pressure + impedance * flow_in
        pipe_pressure.append(current_pressure if output_signal == "pipe_pressure" else flow_in)
        x += dt * (a[0] + 2 * b[0] + 2 * c[0] + d[0]) / 6
        velocity += dt * (a[1] + 2 * b[1] + 2 * c[1] + d[1]) / 6
        flow_speed += dt * (a[2] + 2 * b[2] + 2 * c[2] + d[2]) / 6
        if not all(math.isfinite(value) for value in (x, velocity, flow_speed)):
            raise ArithmeticError(f"Non-finite model state at sample {index}")
    if output_signal == "radiation_pressure":
        from features.gagaku.spherical_load import radiation_pressure
        return radiation_pressure(outgoing_history[:count], sample_rate_hz=sample_rate_hz,
                                  pipe_length_m=pipe_length_m, pipe_radius_m=p["pipe_radius_m"],
                                  radiation_radius_m=radius,
                                  exterior_distance_m=exterior_distance_m,
                                  sound_speed_m_s=p["sound_speed_m_s"])
    return pipe_pressure


def write_wav(path: Path, pressure: list[float], sample_rate_hz: int,
              *, physical_unit: str = "Pa") -> dict:
    """Write mono PCM16; per-file scale is a listening gain, not calibration."""
    if not pressure:
        raise ValueError("Empty signal")
    peak = max(abs(value) for value in pressure)
    if peak == 0:
        raise ValueError("Model did not sound")
    gain = 0.8 * 32767 / peak
    pcm = struct.pack("<" + "h" * len(pressure),
                      *(round(value * gain) for value in pressure))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, sample_rate_hz, len(pressure), "NONE", "not compressed"))
        wav.writeframes(pcm)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "sample_rate_hz": sample_rate_hz, "frames": len(pressure),
            "peak_signal_physical_units": peak, "physical_unit": physical_unit,
            "pcm_gain_per_physical_unit": gain}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pressure-pa", type=float, default=800)
    parser.add_argument("--pipe-length-m", type=float, default=0.241)
    parser.add_argument("--seconds", type=float, default=3.0)
    args = parser.parse_args()
    parameters = {"pressure_pa": args.pressure_pa, "pipe_length_m": args.pipe_length_m,
                  "seconds": args.seconds, "sample_rate_hz": 48000, "reed_q": 35.0,
                  "additional_mass_ratio": 0.0, "reflection_loss": 0.98,
                  "reflection_sigma_samples": 1.0}
    signal = render(**parameters)
    wav = write_wav(args.output_dir / "ichi.wav", signal, 48000)
    manifest = {"model": "Hikichi et al. equations 1-3, one-pipe approximation",
                "source_doi": PAPER_DOI, "parameters": parameters,
                "paper_parameters": PAPER_PARAMETERS,
                "implementation_assumptions": {
                    "reflection_loss": "0.98; not stated numerically in accessed paper",
                    "reflection_sigma_samples": "1.0; Gaussian width not stated numerically in accessed paper",
                    "initial_perturbation": "50 ms pressure ramp",
                    "output": "internal pipe pressure proxy; no external radiation transfer",
                }, "wav": wav}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "parameters.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
