"""Physical and numerical invariants for the experimental spherical load."""
import cmath
import math
import random
import unittest

from features.gagaku.spherical_load import (
    ReflectionState, SphericalReflection, _filter, delayed_sample,
    frequency_response, radiation_pressure, reflection_coefficients,
)


class SphericalLoadTests(unittest.TestCase):
    def test_passive_reflection_matches_continuous_load_under_tustin(self):
        pipe_radius = .0035
        for radius in (pipe_radius, pipe_radius / (4 * .6133)):
            beta = pipe_radius**2 / (4 * radius**2)
            tau = radius / 340
            for rate in (48000, 96000, 192000):
                with self.subTest(radius_m=radius, sample_rate_hz=rate):
                    b0, b1, a1 = reflection_coefficients(
                        sample_rate_hz=rate, pipe_radius_m=pipe_radius,
                        radiation_radius_m=radius)
                    self.assertLess(abs(a1), 1)
                    for step in range(1001):
                        theta = math.pi * step / 1001
                        q = cmath.exp(-1j * theta)
                        actual = (b0 + b1 * q) / (1 + a1 * q)
                        s = 2j * rate * math.tan(theta / 2)
                        load = beta * tau * s / (1 + tau * s)
                        expected = (load - 1) / (load + 1)
                        self.assertLessEqual(abs(actual), 1 + 1e-14)
                        self.assertGreaterEqual(load.real, -1e-14)
                        self.assertAlmostEqual(abs(actual - expected), 0, places=13)
                    self.assertAlmostEqual((b0 + b1) / (1 + a1), -1)
                    self.assertAlmostEqual((b0 - b1) / (1 - a1), (beta - 1)/(beta + 1))

    def test_source_derived_radius_matches_unflanged_low_frequency_terms(self):
        # Causse et al., JASA 75 (1984), p.243, Sec.II.B, unnumbered
        # "For z < 1.5" formula: Re(Z/Z0) ~ (kr)^2/4; Im(Z/Z0) ~ .6133*kr.
        # This probes the implemented reflection filter, then infers its load.
        pipe_radius, rate = .0035, 48000
        radius = pipe_radius / (4 * .6133)
        for kr in (1e-2, 1e-3, 1e-4):
            frequency = kr * 340 / (2 * math.pi * pipe_radius)
            response = frequency_response(
                frequency_hz=frequency, sample_rate_hz=rate,
                pipe_length_m=.241, pipe_radius_m=pipe_radius,
                radiation_radius_m=radius)
            reflection = response['termination_reflection']
            normalized_load = (1 + reflection) / (1 - reflection)
            # Finite-kr and bilinear-warp errors are O((kr)^2) relatively.
            self.assertLess(abs(normalized_load.real / (kr*kr/4) - 1), 5*kr*kr)
            self.assertLess(abs(normalized_load.imag / (.6133*kr) - 1), 5*kr*kr)

    def test_impulse_and_noise_cannot_gain_reflected_energy(self):
        coefficients = reflection_coefficients(sample_rate_hz=48000, pipe_radius_m=.0035)
        generator = random.Random(53)
        signals = ([1.] + [0.] * 1023, [generator.uniform(-1, 1) for _ in range(4096)])
        for signal in signals:
            state = ReflectionState()
            output = []
            for value in list(signal) + [0.] * 1024:
                result, state = _filter(value, state, coefficients)
                output.append(result)
            self.assertLessEqual(sum(y*y for y in output), sum(x*x for x in signal) + 1e-12)

    def test_round_trip_is_two_identical_forward_delays(self):
        history = [1.] + [0.] * 255
        delay = .241 / 340 * 48000
        once = [delayed_sample(history, n, delay) for n in range(len(history))]
        twice = [delayed_sample(once, n, delay) for n in range(len(history))]
        direct = [delayed_sample(history, n, delay, traversals=2) for n in range(len(history))]
        self.assertLess(max(abs(a-b) for a, b in zip(twice, direct)), 1e-15)
        self.assertAlmostEqual(sum(direct), 1)
        self.assertTrue(all(value >= 0 for value in direct))

    def test_prediction_does_not_commit_future_reflection(self):
        history = [math.sin(n*.37) for n in range(1000)]
        load = SphericalReflection(sample_rate_hz=48000, pipe_length_m=.241, pipe_radius_m=.0035)
        reference = SphericalReflection(sample_rate_hz=48000, pipe_length_m=.241, pipe_radius_m=.0035)
        for n in range(200):
            initial = load.state
            value, current = load.predict(history, n)
            future, _ = load.predict(history, n+1, state=current)
            self.assertEqual(load.state, initial)
            self.assertEqual(value, reference.step(history, n))
            reference_next, _ = reference.predict(history, n+1)
            self.assertEqual(future, reference_next)
            load.commit(current)

    def test_exterior_pressure_has_inverse_distance_and_retardation(self):
        rate, radius, speed = 48000, .0035, 340
        # Whole-sample difference isolates physical spreading from interpolation.
        near = radius + 10 * speed / rate
        far = radius + 17 * speed / rate
        history = [1.] + [0.] * 511
        parameters = dict(sample_rate_hz=rate, pipe_length_m=.241,
                          pipe_radius_m=radius, sound_speed_m_s=speed)
        a = radiation_pressure(history, exterior_distance_m=near, **parameters)
        b = radiation_pressure(history, exterior_distance_m=far, **parameters)
        self.assertGreater(max(abs(x) for x in a), 0)
        self.assertLess(max(abs(b[n] - near/far*a[n-7]) for n in range(7, len(b))), 1e-14)

    def test_observed_pressure_matches_network_frequency_response(self):
        parameters = dict(sample_rate_hz=48000, pipe_length_m=.241, pipe_radius_m=.0035)
        z0 = 1.2 * 340 / (math.pi * .0035**2)
        for frequency in (480, 1920):
            theta = 2 * math.pi * frequency / 48000
            history = [math.cos(theta*n) for n in range(8000)]
            signal = radiation_pressure(history, **parameters)
            # The window contains an integer number of both probe frequencies.
            actual = 2/4800 * sum(signal[n] * cmath.exp(-1j*theta*n)
                                  for n in range(3200, 8000))
            response = frequency_response(frequency_hz=frequency, **parameters)
            expected = response['radiation_pressure_per_input_flow_pa_s_m3'] / (
                response['input_impedance_pa_s_m3'] + z0)
            self.assertLess(abs(actual - expected), 1e-12)

    def test_dc_pressure_zero_and_load_transfer_share_one_network(self):
        parameters = dict(sample_rate_hz=48000, pipe_length_m=.241, pipe_radius_m=.0035)
        dc = frequency_response(frequency_hz=0, **parameters)
        self.assertAlmostEqual(abs(dc['input_impedance_pa_s_m3']), 0, places=7)
        self.assertAlmostEqual(abs(dc['radiation_pressure_per_input_flow_pa_s_m3']), 0, places=7)
        z0 = 1.2 * 340 / (math.pi * .0035**2)
        for frequency in (100, 483.7, 967.4, 1934.8, 4000, 10000):
            response = frequency_response(frequency_hz=frequency, **parameters)
            reflection = response['round_trip_reflection']
            zin = response['input_impedance_pa_s_m3']
            self.assertLessEqual(abs(reflection), 1)
            self.assertGreaterEqual(zin.real, -1e-7)
            self.assertAlmostEqual(abs((zin-z0)/(zin+z0)-reflection), 0, places=13)
        steady = radiation_pressure([1.]*512, **parameters)
        self.assertLess(max(abs(x) for x in steady[256:]), 1e-14)


if __name__ == '__main__':
    unittest.main()
