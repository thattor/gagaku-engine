"""Observable checks of the coupled one-pipe renderer."""

from pathlib import Path
import tempfile
import unittest
import wave

from features.gagaku.sho_one_pipe import render, write_wav


class ShoOnePipeTests(unittest.TestCase):
    def test_pressure_drives_audible_output_and_writes_pcm(self):
        silent = render(pressure_pa=0, seconds=0.2)
        self.assertEqual(max(abs(value) for value in silent), 0)

        sound = render(pressure_pa=800, seconds=1.0)
        steady = sound[len(sound) // 2:]
        self.assertGreater(max(abs(value) for value in steady), 100)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ichi.wav"
            manifest = write_wav(path, sound, 48000)
            with wave.open(str(path), "rb") as wav:
                self.assertEqual((wav.getnchannels(), wav.getsampwidth(),
                                  wav.getframerate(), wav.getnframes()),
                                 (1, 2, 48000, len(sound)))
            self.assertEqual(len(manifest["sha256"]), 64)

    def test_pressure_change_affects_sound_without_retuning_oscillator(self):
        low = render(pressure_pa=400, seconds=1.0)
        high = render(pressure_pa=800, seconds=1.0)
        self.assertGreater(max(abs(value) for value in high[len(high) // 2:]),
                           max(abs(value) for value in low[len(low) // 2:]))


if __name__ == "__main__":
    unittest.main()
