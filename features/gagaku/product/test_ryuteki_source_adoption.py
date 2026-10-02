import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import audio
from . import ryuteki_source_adoption as adopted
from . import three_pipe_body as body


class SourceAdoptionTest(unittest.TestCase):
    def test_all_32_target_locations_are_canvas15_in_four_columns(self):
        cells = adopted.policy()['cells']
        self.assertEqual(len(cells), 32)
        self.assertEqual(len({c['id'] for c in cells}), 32)
        self.assertEqual({c['source']['canvas'] for c in cells}, {15})
        self.assertEqual({c['source']['sha256'] for c in cells}, {adopted.IMAGE_SHA256})
        for cell in cells:
            x0, y0, x1, y1 = cell['source']['bbox_normalized']
            self.assertEqual([x0, x1], adopted.COLUMNS[cell['line']])
            self.assertEqual([y0, y1], adopted.ROWS[cell['primary'] - 1:cell['primary'] + 1])
            self.assertFalse(cell['performance_verified'])
            if cell['line'] < 4:
                self.assertEqual(cell['legacy_cell_id'], f"ryuteki.L{cell['line'] + 1}.P{cell['primary']}")
            else:
                self.assertIsNone(cell['legacy_cell_id'])
        self.assertEqual(cells[0]['chant_candidate'], 'チラハ')
        self.assertEqual(cells[0]['legacy_chant_candidate'], 'トラロ')
        self.assertEqual(cells[0]['initial_only_annotation']['chant_candidate'], 'トロホ')

    def test_only_ryuteki_changes_and_remapped24_preserve_adopted_pitch_and_timing(self):
        old, new = body.plan(), adopted.plan()
        for instrument in ('sho', 'hichiriki'):
            self.assertEqual([e for e in new if e['instrument'] == instrument],
                             [e for e in old if e['instrument'] == instrument])
        indexed = {e['id']: e for e in old}
        remapped = [e for e in new if e.get('legacy_event_id')]
        self.assertEqual(len({e['cell_ids'][0] for e in remapped}), 24)
        for event in remapped:
            before = indexed[event['legacy_event_id']]
            self.assertEqual(event['midi'], before['midi'])
            self.assertEqual(event['start'], before['start'] - 24)
            self.assertEqual(event['end'], before['end'] - 24)
            self.assertEqual(event['finger_candidate'], before['finger_candidate'])
            self.assertEqual(event['special_adoption'], before['special_adoption'])
        self.assertFalse(any(e['source'].get('canvas') == 14 for e in new if e['instrument'] == 'ryuteki'))
        self.assertFalse(any(e.get('legacy_event_id', '').startswith('ryuteki.L1.')
                             for e in remapped))

    def test_new_last8_equal_subdivision_and_retained_pitch_continuity(self):
        events = adopted.plan()
        expected = [[76], [86, 86], [78, 79, 78], [76], [76], [76], [76], [76]]
        for point, pitches in enumerate(expected, 1):
            selected = [e for e in events if e['cell_ids'] == [f'ryuteki.L4.P{point}']]
            self.assertEqual([e['midi'] for e in selected], pitches)
            self.assertEqual([e['start'] for e in selected],
                             [72 + (point - 1) * 3 + 3 * i / len(pitches) for i in range(len(pitches))])
            self.assertTrue(all(e['end'] - e['start'] == 3 / len(pitches) for e in selected))
            self.assertTrue(all(e['legacy_event_id'] is None for e in selected))
        spans = body.sounding_spans(events)
        retained = next(s for s in spans if 'ryuteki.L4.P6.N1' in s['ledger_ids'])
        self.assertEqual(retained['end'], 96)
        self.assertTrue({'ryuteki.L4.P7.N1', 'ryuteki.L4.P8.N1'} <= set(retained['ledger_ids']))
        self.assertEqual(len([i for s in spans for i in s['ledger_ids']]), len(events))
        self.assertEqual({i for s in spans for i in s['ledger_ids']}, {e['id'] for e in events})
        for instrument in adopted.INSTRUMENTS:
            self.assertEqual(len({c for e in events if e['instrument'] == instrument for c in e['cell_ids']}), 32)
        self.assertTrue(all(e['performance_verified'] is False for e in events))

    def test_audio_preserves_frozen_other_stems_and_changes_only_ryuteki_mix(self):
        loop = [math.sin(2 * math.pi * i / 127) for i in range(127)]
        bank = {n: {'loop': loop, 'gain': .02} for n in adopted.INSTRUMENTS}
        with patch.object(adopted, 'FS', 80), patch.object(body, 'FS', 80), patch.object(audio, 'FS', 80), \
                patch.object(body, 'metrics', return_value={'nonfinite_count': 0, 'full_scale_count': 0}):
            before, _ = body.render(bank, body.plan())
            after = adopted.render(bank, adopted.plan())
        for name in ('sho', 'hichiriki'):
            self.assertEqual(before[name], after[name])
            self.assertEqual(audio.pcm(before[name]), audio.pcm(after[name]))
        for name in ('ryuteki', 'ensemble'):
            self.assertNotEqual(before[name], after[name])
        for name, signal in after.items():
            channels = 2 if name == 'ensemble' else 1
            self.assertEqual(len(signal), 96 * 80 * channels)
            self.assertEqual(list(signal[-channels:]), [0] * channels)

    def test_raw_first_excerpt_is_framed_without_claiming_terminal_zero(self):
        from array import array
        with tempfile.TemporaryDirectory() as tmp, patch.object(adopted, 'FS', 80), patch.object(audio, 'FS', 80):
            path = Path(tmp) / 'excerpt.wav'
            audio.write_wav(path, 2, [array('f', [.01, -.01]) * (24 * 80)])
            measured = adopted.inspect_pcm(path, 24, 2, require_terminal_zero=False)
            self.assertFalse(measured['final_frame_zero'])
            self.assertFalse(measured['terminal_zero_required'])
            with self.assertRaises(ValueError):
                adopted.inspect_pcm(path, 24, 2)
            with self.assertRaises(ValueError):
                adopted.inspect_pcm(path, 23, 2, require_terminal_zero=False)

    def test_frozen_validator_is_not_weakened(self):
        with self.assertRaises(ValueError):
            body.validate(adopted.plan())
        body.validate(body.plan())

    def test_reject_schedule_glyph_pitch_source_and_verified_mutations(self):
        original = adopted.plan()
        for key, value in (('midi', 1), ('start', 94), ('end', float('nan')),
                           ('performance_verified', True), ('cell_ids', []), ('source', {}),
                           ('finger_candidate', 'invented'), ('legacy_event_id', 'ryuteki.L1.P1.N1')):
            bad = copy.deepcopy(original)
            bad[-1][key] = value
            with self.assertRaises(ValueError):
                adopted.validate(bad)
        for bad in (None, [], original[:-1], original + [original[0]]):
            with self.assertRaises(ValueError):
                adopted.validate(bad)

    def test_reject_policy_promotion_parameter_changes_and_source_drift(self):
        original = json.loads(adopted.SPEC.read_text())
        for key, value in (('verified_exit', True), ('tomede', True), ('traditional_nihen_verified', True),
                           ('fully_verified_performance_events', 1), ('musical_acceptance', 'PASS'),
                           ('strict_reading_status', 'PASS'), ('a4_hz', 440), ('release_seconds', .8),
                           ('attack_seconds', .08), ('seconds_per_primary_cell', 2), ('dependency_hashes', {})):
            bad = copy.deepcopy(original)
            bad[key] = value
            self.reject_policy(bad)
        for key, value in (('finger_candidates', ['五', '上', 'テ']), ('performance_verified', True),
                           ('legacy_cell_id', 'ryuteki.L1.P1'), ('source', {})):
            bad = copy.deepcopy(original)
            bad['cells'][26][key] = value
            self.reject_policy(bad)
        bad = copy.deepcopy(original)
        bad['source_partition']['canvas'] = 14
        self.reject_policy(bad)
        with patch.object(adopted, 'digest', return_value='0' * 64), self.assertRaises(ValueError):
            adopted.policy()

    def reject_policy(self, bad):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'spec.json'
            path.write_text(json.dumps(bad))
            with patch.object(adopted, 'SPEC', path), self.assertRaises(ValueError):
                adopted.policy()


if __name__ == '__main__':
    unittest.main()
