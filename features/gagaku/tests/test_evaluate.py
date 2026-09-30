import json
import math
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

from features.gagaku.evaluate import evaluate


class EvaluateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.reference = self.root / "reference.json"
        self.reference.write_text(json.dumps({
            "reference_id": "synthetic-test",
            "target_hz": 483.7,
            "frequency_tolerance_percent": 2.0,
            "qualitative_targets": {
                "threshold_depends_on_pipe_length": True,
                "high_frequency_content_increases_with_pressure": True,
                "second_and_fourth_harmonics_enhanced": True,
            },
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def make_wav(self, frequency, name="candidate.wav"):
        path = self.root / name
        rate = 48000
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            frames = bytearray()
            for index in range(rate):
                t = index / rate
                value = 0.25 * math.sin(2 * math.pi * frequency * t)
                value += 0.35 * math.sin(2 * math.pi * frequency * 2 * t)
                value += 0.40 * math.sin(2 * math.pi * frequency * 4 * t)
                frames.extend(struct.pack("<h", round(max(-0.99, min(0.99, value)) * 32767)))
            wav.writeframes(frames)
        return path

    def test_tone_frequency_passes_but_missing_gate_evidence_fails_overall(self):
        path = self.make_wav(478.8)
        result = evaluate(path, self.reference)
        self.assertLessEqual(result["measurements"]["frequency_error_percent"], 2.0)
        self.assertEqual(result["gate_1"]["status"], "FAIL")
        criteria = {item["id"]: item["status"] for item in result["gate_1"]["criteria"]}
        self.assertEqual(criteria["fundamental_frequency_error"], "PASS")
        self.assertEqual(criteria["pipe_length_threshold_dependence"], "UNVERIFIED")
        self.assertEqual(criteria["pressure_dependent_high_frequency_growth"], "UNVERIFIED")
        self.assertEqual(criteria["second_and_fourth_harmonics_enhanced"], "PASS")
        self.assertEqual(len(result["wav"]["sha256"]), 64)
        self.assertEqual(len(result["provenance"]["evaluator_source_sha256"]), 64)
        self.assertEqual(result["reference"]["target_hz"], 483.7)

    def test_fft_centroid_matches_known_harmonic_magnitude_centroid(self):
        from features.gagaku.evaluate import _spectrum

        rate = 12000
        samples = [
            0.7 * math.sin(2 * math.pi * 440 * i / rate)
            + 0.35 * math.sin(2 * math.pi * 880 * i / rate)
            for i in range(rate)
        ]
        result = _spectrum(samples, rate, 440.0)
        self.assertAlmostEqual(result["centroid_hz"], (440 * 0.7 + 880 * 0.35) / 1.05, delta=4.0)
        self.assertIn("radix-2 FFT", result["centroid_method"])

    def test_native_rate_fft_preserves_high_frequency_centroid_content(self):
        from features.gagaku.evaluate import _spectrum

        rate = 48000
        components = [(440.0, 0.7), (880.0, 0.35), (5000.0, 0.2)]
        samples = [
            sum(amplitude * math.sin(2 * math.pi * frequency * i / rate) for frequency, amplitude in components)
            for i in range(rate)
        ]
        result = _spectrum(samples, rate, 440.0)
        expected = sum(frequency * amplitude for frequency, amplitude in components) / sum(amplitude for _, amplitude in components)
        self.assertAlmostEqual(result["centroid_hz"], expected, delta=12.0)

    def test_harmonic_peak_survives_small_f0_estimation_error(self):
        from features.gagaku.evaluate import _goertzel_amplitude, _spectrum

        rate = 12000
        actual_f0 = 478.8
        estimated_f0 = 479.1
        samples = [
            0.2 * math.sin(2 * math.pi * actual_f0 * i / rate)
            + 0.6 * math.sin(2 * math.pi * 2 * actual_f0 * i / rate)
            + 0.35 * math.sin(2 * math.pi * 4 * actual_f0 * i / rate)
            for i in range(rate)
        ]
        # The old single-frequency probe loses H4 after 1.2 Hz detuning.
        old_h4 = _goertzel_amplitude(samples, rate, 4 * estimated_f0)
        self.assertLess(old_h4, 0.3)
        spectrum = _spectrum(samples, rate, estimated_f0)
        self.assertTrue(spectrum["second_and_fourth_dominant"])
        self.assertGreater(spectrum["harmonic_amplitudes"]["4"], 0.3)
        self.assertAlmostEqual(spectrum["harmonic_peak_frequencies_hz"]["4"],
                               4 * actual_f0, delta=1.0)

    def test_harmonic_fft_refines_biased_autocorrelation_without_reference_tone(self):
        from features.gagaku.evaluate import _estimate_f0, _refine_f0_from_harmonics

        rate = 48000
        actual_f0 = 478.306
        components = ((1, 0.05), (2, 0.8), (4, 0.7), (6, 0.4), (7, 0.3), (9, 0.2))
        samples = [
            sum(amplitude * math.sin(2 * math.pi * actual_f0 * harmonic * index / rate)
                for harmonic, amplitude in components)
            for index in range(rate)
        ]

        # Strong even harmonics pull the normalized autocorrelation estimate
        # away from the known non-bin-centered fundamental.
        initial = _estimate_f0(samples, rate, target_hz=483.7)
        self.assertGreater(abs(initial - actual_f0), 0.1)

        refined, provenance = _refine_f0_from_harmonics(samples, rate, initial)
        self.assertAlmostEqual(refined, actual_f0, delta=0.1)
        self.assertGreater(abs(refined - 483.7), 1.0)
        self.assertEqual(provenance["method"], "magnitude_weighted_median_of_log_parabolic_h1_h6_fft_peaks")
        self.assertIn(2, [peak["harmonic"] for peak in provenance["peaks"]])
        self.assertIn(4, [peak["harmonic"] for peak in provenance["peaks"]])

    def test_frequency_outside_tolerance_is_fail(self):
        result = evaluate(self.make_wav(510.0), self.reference)
        criterion = next(c for c in result["gate_1"]["criteria"] if c["id"] == "fundamental_frequency_error")
        self.assertEqual(criterion["status"], "FAIL")

    def test_cli_writes_fail_result_and_spectrum_csv_with_success_exit(self):
        wav = self.make_wav(478.8)
        output = self.root / "result.json"
        process = subprocess.run([
            sys.executable, "-m", "features.gagaku.evaluate",
            "--wav", str(wav), "--reference", str(self.reference), "--output", str(output),
        ], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["gate_1"]["status"], "FAIL")
        csv_path = Path(result["artifacts"]["spectrum_csv"])
        self.assertTrue(csv_path.exists())
        self.assertIn("harmonic,frequency_hz,relative_amplitude", csv_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
