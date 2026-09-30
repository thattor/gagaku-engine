"""Independent physical sound candidates. All values are design assumptions.

Reed: Bernoulli valve coupled to a closed/open cylindrical delay line.
Jet: delayed tanh jet displacement pressure source and modal pipe admittance.
Sources are equations/facts, not copied recordings, figures or source code.
These are generic proxies, not independently validated instrument models.
"""
import math

FS = 48000


def reed(frequency, seconds=2.0):
    rho, speed, radius = 1.2, 340.0, 0.003
    impedance = rho * speed / (math.pi * radius**2)
    width, opening, closing_pressure = 0.006, 0.00025, 4500.0
    delay = FS / (2 * frequency)
    history = [0.0] * (math.ceil(delay) + 2)
    reflected = displacement = velocity = 0.0
    omega, q = 2 * math.pi * frequency * 3, 3.0
    result = []
    for i in range(round(seconds * FS)):
        position = i - delay
        j = math.floor(position)
        fraction = position - j
        back = ((1 - fraction) * history[j % len(history)]
                + fraction * history[(j + 1) % len(history)]) if j >= 0 else 0
        reflected += 0.65 * (-0.985 * back - reflected)
        mouth = 3000 * min(1, i / (0.08 * FS))
        gap = max(0.0, opening - displacement)
        k = impedance * width * gap * math.sqrt(2 / rho)
        drive = mouth - 2 * reflected
        root = 2 * abs(drive) / (math.sqrt(k * k + 4 * abs(drive)) + k) if drive else 0
        pressure_drop = math.copysign(root * root, drive)
        pressure = mouth - pressure_drop
        # Four substeps for the reed mass/spring/damper, bounded by contact.
        dt = 1 / (4 * FS)
        for _ in range(4):
            velocity += dt * (omega**2 * (opening * pressure_drop / closing_pressure - displacement)
                              - omega / q * velocity)
            displacement += dt * velocity
        outgoing = pressure - reflected
        history[i % len(history)] = outgoing
        result.append(pressure)
    return result


def jet(frequency, seconds=2.0):
    # Modal admittance is a design approximation for an open cylindrical tube.
    rho, h, window, u0, offset, contraction = 1.2, 0.001, 0.01, 22.0, 0.0001, 0.6
    b = 0.4 * h
    tau = window / (0.4 * u0)
    delay = max(1, round(tau * FS))
    history = [0.0] * (delay + 1)
    displacement_gain = math.exp(0.3 / h * window) * h / u0
    source_gain = rho * (4 / math.pi * math.sqrt(2 * h * window)) * u0 * b / window
    modes = []
    # Bilinear transform of a*s/(s*s + omega/Q*s + omega*omega).
    for n in range(1, 6):
        omega = 2 * FS * math.tan(math.pi * frequency * n / FS)
        a, damping = 20.0 / n, omega / (20 / math.sqrt(n))
        scale = 4 * FS**2 + 2 * FS * damping + omega**2
        modes.append([a * 2 * FS / scale,
                      (2 * omega**2 - 8 * FS**2) / scale,
                      (4 * FS**2 - 2 * FS * damping + omega**2) / scale, 0.0, 0.0])
    previous_pressure = previous_pressure2 = previous_jet = 0.0
    result = []
    for i in range(round(seconds * FS)):
        acoustic = history[(i - delay) % len(history)] if i >= delay else 0.0
        # An initial impulse, not a periodic oscillator, starts the feedback.
        acoustic += 1e-5 if i == delay else 0.0
        jet_value = math.tanh((displacement_gain * acoustic - offset) / b)
        source = source_gain * (jet_value - previous_jet) * FS * min(1, i / (0.1 * FS))
        previous_jet = jet_value
        admittance = sum(m[0] for m in modes)
        memory = sum(-m[0] * previous_pressure2 - m[1] * m[3] - m[2] * m[4] for m in modes)
        driving = admittance * source + memory
        loss = rho / (2 * contraction**2)
        coefficient = admittance * loss
        velocity = math.copysign(2 * abs(driving) / (1 + math.sqrt(1 + 4 * coefficient * abs(driving))), driving)
        pressure = source - loss * velocity * abs(velocity)
        for m in modes:
            current = m[0] * (pressure - previous_pressure2) - m[1] * m[3] - m[2] * m[4]
            m[4], m[3] = m[3], current
        previous_pressure2, previous_pressure = previous_pressure, pressure
        history[i % len(history)] = velocity
        result.append(pressure)
    return result


def transpose(samples, semitones):
    """Resample own physical output; shifts spectrum as well as pitch."""
    ratio = 2**(semitones / 12)
    length = math.floor((len(samples) - 1) / ratio)
    result = []
    for i in range(length):
        position = i * ratio
        j = int(position)
        f = position - j
        result.append(samples[j] * (1 - f) + samples[j + 1] * f)
    return result
