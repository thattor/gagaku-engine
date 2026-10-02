import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import audio
from . import corrected_long as long


class CorrectedLongTest(unittest.TestCase):
    def test_four_pass_mapping_keeps_all_non_ryuteki_events_exact(self):
        events, old = long.plan(), long.inherited.plan()
        self.assertEqual([e for e in events if e['instrument'] != 'ryuteki'],
                         [e for e in old if e['instrument'] != 'ryuteki'])
        corrected = {e['id']: e for e in long.corrected.plan() if e['instrument'] == 'ryuteki'}
        self.assertEqual(len(corrected), 72)
        for number in range(1, 5):
            for instrument in long.INSTRUMENTS:
                cells = {c for e in events if e['instrument'] == instrument and e['pass_number'] == number
                         for c in e['cell_ids']}
                self.assertEqual(cells, {f'{instrument}.L{line}.P{point}'
                                        for line in range(1, 5) for point in range(1, 9)})
            selected = [e for e in events if e['instrument'] == 'ryuteki' and e['pass_number'] == number]
            self.assertEqual(len(selected), 72)
            for event in selected:
                original = corrected[event['canonical_corrected_event_id']]
                comparable = copy.deepcopy(event)
                for key in ('source_event_id', 'canonical_corrected_event_id', 'pass_number'):
                    comparable.pop(key)
                self.assertEqual(event['start'], original['start'] + (number - 1) * 96)
                self.assertEqual(event['end'], original['end'] + (number - 1) * 96)
                comparable.update(id=original['id'], start=original['start'], end=original['end'])
                self.assertEqual(comparable, original)
                self.assertEqual(event['source']['canvas'], 15)
                self.assertFalse(event['performance_verified'])
                self.assertNotIn('initial_adoption', event)
        firsts = [e for e in events if e['instrument'] == 'ryuteki' and e['cell_ids'] == ['ryuteki.L1.P1']]
        self.assertEqual({e['chant_candidate'] for e in firsts}, {'チラハ'})
        self.assertTrue(all(e['initial_only_annotation']['execution'].startswith('not separately executed') for e in firsts))

    def test_continuous_sho_and_ledger_conservation_at_all_joins(self):
        events = long.plan()
        spans = long.sounding_spans(events)
        old_spans = long.inherited.sounding_spans(long.inherited.plan())
        for instrument in ('sho', 'hichiriki'):
            self.assertEqual([s for s in spans if s['instrument'] == instrument],
                             [s for s in old_spans if s['instrument'] == instrument])
        ids = [i for s in spans for i in s['ledger_ids']]
        self.assertEqual(len(ids), len(events))
        self.assertEqual(set(ids), {e['id'] for e in events})
        self.assertEqual(len([s for s in spans if s['instrument'] == 'sho' and s['start'] == 0 and s['end'] == 384]), 2)
        for boundary in (96, 192, 288):
            held = [s for s in spans if s['instrument'] == 'sho' and s['start'] < boundary < s['end']]
            self.assertTrue(held)
            for span in held:
                passes = {int(i.split('.')[0][4:]) for i in span['ledger_ids']}
                self.assertTrue({boundary // 96, boundary // 96 + 1} <= passes)
        for number in range(4):
            last = next(s for s in spans if f'pass{number + 1}.ryuteki.L4.P6.N1' in s['ledger_ids'])
            self.assertEqual(last['end'], (number + 1) * 96)
            self.assertTrue({f'pass{number + 1}.ryuteki.L4.P7.N1', f'pass{number + 1}.ryuteki.L4.P8.N1'} <= set(last['ledger_ids']))

    def test_real_voice_renderer_preserves_other_stems_and_terminal_zeros(self):
        import math
        loop = [math.sin(2 * math.pi * i / 127) for i in range(127)]
        bank = {n: {'loop': loop, 'gain': .025} for n in long.INSTRUMENTS}
        with patch.object(long, 'FS', 80), patch.object(long.inherited, 'FS', 80), patch.object(audio, 'FS', 80):
            before = long.inherited.render(bank, long.inherited.plan())
            after = long.render(bank, long.plan())
            early = long.inherited.boundary_exit(after['ensemble'], 2, 96 * 80)
        for name in ('sho', 'hichiriki'):
            self.assertEqual(before[name], after[name])
            self.assertEqual(audio.pcm(before[name]), audio.pcm(after[name]))
        for name in ('ryuteki', 'ensemble'):
            self.assertNotEqual(before[name], after[name])
        for name, signal in after.items():
            channels = 2 if name == 'ensemble' else 1
            self.assertEqual(len(signal), 384 * 80 * channels)
            self.assertEqual(list(signal[-channels:]), [0] * channels)
        self.assertEqual(len(early), 96 * 80 * 2)
        self.assertEqual(list(early[-2:]), [0, 0])
        cutoff = (96 * 80 - round(.25 * 80)) * 2
        self.assertEqual(early[:cutoff], after['ensemble'][:cutoff])

    def test_finish_rules_delegate_unchanged_and_late_terminal_is_not_restarted(self):
        for boundary in (96, 192, 288, 384):
            for offset in (-1, -.75, -.25, 0, .25, .75, 1):
                time = boundary - .25 + offset / audio.FS
                self.assertEqual(long.finish_plan(time), long.inherited.finish_plan(time))
        for time in (383.750001, 383.9, 384):
            result = long.finish_plan(time)
            self.assertEqual(result['end_frame'], 384 * audio.FS)
            self.assertFalse(result['full_release_after_request'])
            self.assertEqual(result['request_status'], 'bounded_terminal_completion_release_already_scheduled')
            self.assertFalse(result['verified_exit'])
            self.assertFalse(result['tomede'])
        for time in (-1, 385, True, None, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                long.finish_plan(time)
        logs = long.inherited.exit_requests()
        self.assertEqual(len(logs), 1034)
        self.assertTrue(all(e['verified_exit'] is False and e['tomede'] is False for e in logs))

    def test_controller_copy_is_exact_and_test_only_adapts_require_path(self):
        self.assertEqual(audio.digest(audio.ROOT / 'corrected-long-player.js'), long.PLAYER_SHA256)
        import hashlib
        original_test = (audio.ROOT / 'test_corrected_long_player.cjs').read_bytes().replace(
            b"require('./corrected-long-player.js')", b"require('./long-player.js')")
        self.assertEqual(hashlib.sha256(original_test).hexdigest(),
                         'a625a9380d64f4fec25044679963ae4edc13408a6e131e6a1dc8b104d72b116a')
        html = (audio.ROOT / 'corrected-long-player.html').read_text()
        self.assertEqual(html.count('<button'), 4)
        for ident in ('start', 'finish', 'cancel', 'export'):
            self.assertIn(f'id="{ident}"', html)
        self.assertIn('corrected-long-ensemble-384s.wav', html)
        self.assertIn('corrected-long-inspection.json', html)
        self.assertNotIn('1932年の初度別列2点を初回に選択', html)

    def test_frozen_validator_and_wrong_schedule_are_rejected(self):
        with self.assertRaises(ValueError):
            long.inherited.validate(long.plan())
        with self.assertRaises(ValueError):
            long.validate(long.inherited.plan())
        original = long.plan()
        for key, value in (('performance_verified', True), ('midi', 1), ('end', float('nan')),
                           ('source', {}), ('canonical_corrected_event_id', 'wrong'), ('cell_ids', [])):
            bad = copy.deepcopy(original)
            bad[-1][key] = value
            with self.assertRaises(ValueError):
                long.validate(bad)
        for bad in (None, [], original[:-1], original + [original[0]]):
            with self.assertRaises(ValueError):
                long.validate(bad)

    def test_generation_rejects_existing_artifacts_before_policy_or_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'old-output'
            output.mkdir()
            old_report = output / 'corrected-long-inspection.json'
            old_audio = output / 'corrected-long-ensemble-384s.wav'
            old_report.write_bytes(b'{"generation_status":"COMPLETE"}')
            old_audio.write_bytes(b'preserved previous candidate audio')
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            with patch.object(long, 'policy') as policy, patch.object(long, 'make_bank') as make_bank:
                with self.assertRaisesRegex(ValueError, 'fresh or empty'):
                    long.generate(output)
                policy.assert_not_called()
                make_bank.assert_not_called()
            self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, before)
            file_path = Path(tmp) / 'not-a-directory'
            file_path.write_bytes(b'keep this too')
            with self.assertRaisesRegex(ValueError, 'fresh or empty'):
                long.generate(file_path)
            self.assertEqual(file_path.read_bytes(), b'keep this too')

    def test_policy_rejects_promotion_changed_controls_controller_or_dependencies(self):
        original = json.loads(long.SPEC.read_text())
        for key, value in (('verified_exit', True), ('tomede', True), ('traditional_nihen_verified', True),
                           ('fully_verified_performance_events', 1), ('musical_acceptance', 'PASS'),
                           ('strict_reading_status', 'PASS'), ('a4_hz', 440), ('release_seconds', 1.2),
                           ('attack_seconds', .08), ('passes', 3), ('duration_seconds', 288),
                           ('deadline_seconds', [95, 191, 287, 383]), ('dependency_hashes', {}),
                           ('source_partition', {}), ('controller_sha256', '0' * 64), ('player_commit', 'wrong')):
            bad = copy.deepcopy(original)
            bad[key] = value
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'spec.json'
                path.write_text(json.dumps(bad))
                with patch.object(long, 'SPEC', path), self.assertRaises(ValueError):
                    long.policy()
        with patch.object(long, 'digest', return_value='0' * 64), self.assertRaises(ValueError):
            long.policy()


if __name__ == '__main__':
    unittest.main()
