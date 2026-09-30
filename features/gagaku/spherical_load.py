"""Passive experimental load: lossless cylinder feeding a full pulsating sphere.

The default sphere radius equals the tube radius, so its radiating area is four
times the tube area. This area discontinuity is an explicit approximation,
not an identified sho termination or a reproduction of Causse's unflanged-pipe
formula. Exterior distance is measured from the sphere CENTER.

For S=pi*r**2, A=4*pi*a**2, beta=S/A, tau=a/c:
    Zrad/Z0 = beta*tau*s/(1+tau*s)
    R(s) = ((beta-1)*tau*s-1)/((beta+1)*tau*s+1).
A bilinear transform preserves passivity. Each pipe traversal uses the same
linear fractional delay; round-trip delay is the square of that operator.
There are no empirical wall losses or arbitrary gain factors.

Provenance: Hikichi et al. (2003), Sec. IV.C, DOI 10.1121/1.1534605,
uses a spherical-radiation assumption without stating its boundary formula.
Causse et al. (1984), Secs. II.B/II.E, DOI 10.1121/1.390402, actually uses
Levine-Schwinger pipe radiation with area corrections; it does not identify
this breathing-sphere approximation. The sphere impedance follows outgoing
spherical waves and is equivalent to parallel R=rho*c/A and M=rho*a/A.
A source-derived radius comparison is a=r/(4*0.6133). Causse et al., JASA
75(1), printed p.243 (PDF page index 3), Sec.II.B "Radiation impedance",
unnumbered formula under "For z < 1.5", with z=k*r, gives leading normalized
terms Re(Zrad/Z0)=(k*r)**2/4 and Im(Zrad/Z0)=0.6133*k*r. For a full sphere,
these terms are (k*r)**2/4 and r/(4*a)*k*r. Equating only the reactive term
therefore fixes this radius, without fitting any simulated harmonic or pitch.
At r=3.5 mm it gives a=1.4267079732594164 mm. Higher-order terms, actual tube
geometry and wall losses remain unmatched; this is not the complete formula.
Official independent equation reference:
https://www.mathworks.com/help/audio/ref/sphericalsourceradiationimpedance.html
Primary Causse source:
https://pubs.aip.org/asa/jasa/article-pdf/75/1/241/11499462/241_1_online.pdf
"""
from __future__ import annotations

import cmath
from dataclasses import dataclass
import math
from typing import Sequence


@dataclass(frozen=True)
class ReflectionState:
    previous_input: float = 0.0
    previous_output: float = 0.0


def reflection_coefficients(*, sample_rate_hz: int, pipe_radius_m: float,
                            radiation_radius_m: float | None = None,
                            sound_speed_m_s: float = 340.0) -> tuple[float, float, float]:
    """Return b0,b1,a1 for y[n]=b0*x[n]+b1*x[n-1]-a1*y[n-1]."""
    a = pipe_radius_m if radiation_radius_m is None else radiation_radius_m
    if not all(math.isfinite(v) and v > 0 for v in
               (sample_rate_hz, pipe_radius_m, a, sound_speed_m_s)):
        raise ValueError("Sampling rate, radii and sound speed must be finite and positive")
    beta = pipe_radius_m**2 / (4 * a**2)
    tau = a / sound_speed_m_s
    k = 2 * sample_rate_hz
    denominator = 1 + (beta + 1) * tau * k
    return (((beta - 1) * tau * k - 1) / denominator,
            (-(beta - 1) * tau * k - 1) / denominator,
            (1 - (beta + 1) * tau * k) / denominator)


def _sample(history: Sequence[float], index: int) -> float:
    if index < 0:
        return 0.0
    if index >= len(history):
        raise IndexError("Delayed history is not available")
    return history[index]


def delayed_sample(history: Sequence[float], index: int, delay_samples: float,
                   *, traversals: int = 1) -> float:
    """Linear fractional delay, or its exact square for two pipe traversals."""
    if not math.isfinite(delay_samples) or delay_samples < 0:
        raise ValueError("Delay must be finite and nonnegative")
    integer = math.floor(delay_samples)
    fraction = delay_samples - integer
    if traversals == 1:
        value = (1 - fraction) * _sample(history, index - integer)
        if fraction:
            value += fraction * _sample(history, index - integer - 1)
        return value
    if traversals == 2:
        value = (1 - fraction)**2 * _sample(history, index - 2 * integer)
        if fraction:
            value += 2 * fraction * (1 - fraction) * _sample(history, index - 2 * integer - 1)
            value += fraction**2 * _sample(history, index - 2 * integer - 2)
        return value
    raise ValueError("Only one or two traversals are supported")


def _filter(value: float, state: ReflectionState,
            coefficients: tuple[float, float, float]) -> tuple[float, ReflectionState]:
    b0, b1, a1 = coefficients
    result = b0 * value + b1 * state.previous_input - a1 * state.previous_output
    return result, ReflectionState(value, result)


class SphericalReflection:
    """Returned twice-incoming pressure from history of twice-outgoing pressure.

    predict() does not mutate. At sample n, predict n from committed state, then
    predict n+1 using the returned state; commit only the state for n. This
    provides the known reflection endpoints for the source's RK integration.
    """

    def __init__(self, *, sample_rate_hz: int, pipe_length_m: float,
                 pipe_radius_m: float, radiation_radius_m: float | None = None,
                 sound_speed_m_s: float = 340.0):
        self.coefficients = reflection_coefficients(
            sample_rate_hz=sample_rate_hz, pipe_radius_m=pipe_radius_m,
            radiation_radius_m=radiation_radius_m, sound_speed_m_s=sound_speed_m_s)
        if not math.isfinite(pipe_length_m) or pipe_length_m <= 0:
            raise ValueError("Pipe length must be finite and positive")
        self.one_way_delay_samples = pipe_length_m / sound_speed_m_s * sample_rate_hz
        if self.one_way_delay_samples < 1:
            raise ValueError("Pipe must have at least one sample of one-way delay")
        self.state = ReflectionState()

    def predict(self, history: Sequence[float], index: int,
                state: ReflectionState | None = None) -> tuple[float, ReflectionState]:
        value = delayed_sample(history, index, self.one_way_delay_samples, traversals=2)
        return _filter(value, self.state if state is None else state, self.coefficients)

    def commit(self, state: ReflectionState) -> None:
        self.state = state

    def step(self, history: Sequence[float], index: int) -> float:
        result, state = self.predict(history, index)
        self.commit(state)
        return result


def radiation_pressure(twice_outgoing_history: Sequence[float], *,
                       sample_rate_hz: int, pipe_length_m: float,
                       pipe_radius_m: float, radiation_radius_m: float | None = None,
                       exterior_distance_m: float = 0.05,
                       sound_speed_m_s: float = 340.0) -> list[float]:
    """Return exterior Pa, truncated to input duration; distance is from center.

    Forward wave B=D*w; backward wave R*B; end pressure=(B+R*B)/2.
    Exterior pressure=(a/d)*delay((d-a)/c)*end_pressure. No extra derivative:
    the frequency-dependent radiation impedance already supplies that behavior.
    """
    a = pipe_radius_m if radiation_radius_m is None else radiation_radius_m
    load = SphericalReflection(sample_rate_hz=sample_rate_hz, pipe_length_m=pipe_length_m,
                              pipe_radius_m=pipe_radius_m, radiation_radius_m=a,
                              sound_speed_m_s=sound_speed_m_s)
    if not math.isfinite(exterior_distance_m) or exterior_distance_m < a:
        raise ValueError("Exterior center distance must be finite and at least the sphere radius")
    state = ReflectionState()
    end_pressure = []
    for index in range(len(twice_outgoing_history)):
        incoming = delayed_sample(twice_outgoing_history, index, load.one_way_delay_samples)
        reflected, state = _filter(incoming, state, load.coefficients)
        end_pressure.append((incoming + reflected) / 2)
    delay = (exterior_distance_m - a) / sound_speed_m_s * sample_rate_hz
    return [a / exterior_distance_m * delayed_sample(end_pressure, index, delay)
            for index in range(len(end_pressure))]


def frequency_response(*, frequency_hz: float, sample_rate_hz: int,
                       pipe_length_m: float, pipe_radius_m: float,
                       radiation_radius_m: float | None = None,
                       exterior_distance_m: float = 0.05,
                       sound_speed_m_s: float = 340.0,
                       air_density_kg_m3: float = 1.2) -> dict[str, complex]:
    """Exact response of the implemented digital pipe/load/observation operators."""
    a = pipe_radius_m if radiation_radius_m is None else radiation_radius_m
    if (not math.isfinite(frequency_hz) or not 0 <= frequency_hz <= sample_rate_hz / 2
            or not math.isfinite(exterior_distance_m) or exterior_distance_m < a
            or not math.isfinite(air_density_kg_m3) or air_density_kg_m3 <= 0):
        raise ValueError("Invalid frequency, distance or density")
    load = SphericalReflection(sample_rate_hz=sample_rate_hz, pipe_length_m=pipe_length_m,
                              pipe_radius_m=pipe_radius_m, radiation_radius_m=a,
                              sound_speed_m_s=sound_speed_m_s)
    q = cmath.exp(-2j * math.pi * frequency_hz / sample_rate_hz)
    b0, b1, a1 = load.coefficients
    reflection = (b0 + b1 * q) / (1 + a1 * q)

    def delay_response(samples: float) -> complex:
        integer = math.floor(samples)
        fraction = samples - integer
        return q**integer * ((1 - fraction) + fraction * q)

    forward = delay_response(load.one_way_delay_samples)
    round_trip = reflection * forward**2
    z0 = air_density_kg_m3 * sound_speed_m_s / (math.pi * pipe_radius_m**2)
    zin = z0 * (1 + round_trip) / (1 - round_trip)
    exit_transfer = z0 * (1 + reflection) * forward / (1 - round_trip)
    exterior = a / exterior_distance_m * delay_response(
        (exterior_distance_m - a) / sound_speed_m_s * sample_rate_hz) * exit_transfer
    return {"termination_reflection": reflection,
            "round_trip_reflection": round_trip,
            "input_impedance_pa_s_m3": zin,
            "exit_pressure_per_input_flow_pa_s_m3": exit_transfer,
            "radiation_pressure_per_input_flow_pa_s_m3": exterior}
