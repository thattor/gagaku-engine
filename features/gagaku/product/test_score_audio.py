import copy
import json
import math
import unittest

from .audio import ROOT
from .score_audio import render, validate


class ScoreAudioTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((ROOT/'score-fixture.json').read_text())

    def test_unverified_score_cannot_be_used_as_product(self):
        with self.assertRaisesRegex(ValueError, 'tomede'):
            validate(self.fixture, production=True)
        # Even an injected ready flag must not override the blocked route.
        self.fixture['production_ready'] = True
        with self.assertRaises(ValueError):
            validate(self.fixture, production=True)

    def test_missing_source_and_pitch_are_rejected(self):
        for key in ('source', 'midi'):
            fixture = copy.deepcopy(self.fixture)
            fixture['cells'][0][key] = None
            with self.assertRaises(ValueError):
                validate(fixture)

    def test_no_unknown_chord_is_filled_in(self):
        unknown = next(c for c in self.fixture['cells'] if c['pitch_status'] == 'unresolved')
        # Move unknown cell to beginning to keep the engineering test short.
        unknown = dict(unknown, id='sho.L1.P1')
        _, _, events, gaps = render({}, self.fixture, [unknown], 1)
        self.assertEqual(events, [])
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]['seconds'], 6)
        unknown['midi'] = [69]  # An injected guess cannot silently fill an unread cell.
        _, _, events, gaps = render({}, self.fixture, [unknown], 1)
        self.assertEqual(events, [])
        self.assertEqual(len(gaps), 1)

    def test_octave_and_tuning_are_applied_to_own_bank(self):
        bank = {'hichiriki': {'loop': [math.sin(2*math.pi*i/1024) for i in range(1024)], 'gain': .1}}
        cell = next(c for c in self.fixture['cells'] if c['id'] == 'hichiriki.L1.P2')
        cell = dict(cell, id='hichiriki.L1.P1')
        stems, _, events, gaps = render(bank, self.fixture, [cell], 1)
        from features.gagaku.evaluate import _estimate_f0
        expected = 430 * 2 ** ((79-69)/12)
        self.assertAlmostEqual(_estimate_f0(list(stems['hichiriki'][4800:24000]),48000,expected), expected, delta=2)
        self.assertEqual(len(events), 1)
        self.assertEqual(gaps, [])
        self.assertEqual(events[0]['timing_status'], 'preview_design')


if __name__ == '__main__':
    unittest.main()
