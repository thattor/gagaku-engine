import copy
from array import array
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import three_pipe_long as long
from .models import FS
from .three_pipe_pass import plan as pass_plan


class LongTest(unittest.TestCase):
    def test_canonical_pass_adoption_and_full_coverage(self):
        events = long.plan()
        self.assertEqual(len(events), 696)
        canonical = {e['id']: e for e in pass_plan()}
        self.assertEqual({e['pass_number'] for e in events}, {1, 2, 3, 4})
        for e in events:
            original = canonical[e['canonical_pass_event_id']]
            offset = (e['pass_number'] - original['pass_number']) * 96
            comparable = copy.deepcopy(e)
            comparable.pop('canonical_pass_event_id')
            self.assertEqual(e['start'], original['start'] + offset)
            self.assertEqual(e['end'], original['end'] + offset)
            comparable.update(id=original['id'], start=original['start'],
                              end=original['end'], pass_number=original['pass_number'])
            self.assertEqual(comparable, original)
        rows = [e for e in events if e.get('initial_adoption')]
        self.assertEqual(len(rows), 20)
        self.assertEqual([e['chant_candidate'] for e in rows[::5]], ['トロホ', 'チラハ', 'チラハ', 'チラハ'])
        for index in range(4):
            self.assertEqual([e['midi'] for e in rows[index * 5:(index + 1) * 5]], [83, 81, 81, 78, 79])
        for number in range(1, 5):
            for instrument in long.INSTRUMENTS:
                actual = {c for e in events if e['pass_number'] == number and e['instrument'] == instrument
                          for c in e['cell_ids']}
                self.assertEqual(actual, {f'{instrument}.L{line}.P{point}'
                                          for line in range(1, 5) for point in range(1, 9)})

    def test_sho_continuity_and_ledger_conservation_at_every_join(self):
        events = long.plan()
        spans = long.sounding_spans(events)
        ids = [ident for s in spans for ident in s['ledger_ids']]
        self.assertEqual(len(ids), len(events))
        self.assertEqual(set(ids), {e['id'] for e in events})
        for boundary in (96, 192, 288):
            before = {e['pipe'] for e in events if e['instrument'] == 'sho' and e['end'] == boundary}
            after = {e['pipe'] for e in events if e['instrument'] == 'sho' and e['start'] == boundary}
            held = [s for s in spans if s['instrument'] == 'sho' and s['start'] < boundary < s['end']]
            self.assertTrue(held)
            self.assertEqual({s['pipe'] for s in held}, before & after)
            for s in held:
                numbers = {int(ident.split('.')[0][4:]) for ident in s['ledger_ids']}
                self.assertTrue({boundary // 96, boundary // 96 + 1} <= numbers)
        for pipe in {s['pipe'] for s in spans if s['instrument'] == 'sho'}:
            ordered = sorted((s for s in spans if s['instrument'] == 'sho' and s['pipe'] == pipe),
                             key=lambda s: s['start'])
            self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(ordered, ordered[1:])))

    def test_render_uses_continuous_voices_and_matches_span_lengths(self):
        calls = []

        def probe_voice(bank, instrument, midi, seconds, attack, release):
            calls.append((instrument, seconds, attack, release))
            signal = array('f', [.01]) * round(seconds * long.FS)
            signal[0] = signal[-1] = 0
            return signal

        with patch.object(long, 'FS', 80), patch.object(long, 'voice', side_effect=probe_voice):
            signals = long.render({}, long.plan())
            self.assertEqual(len(signals['ensemble']), 384 * 80 * 2)
            self.assertTrue(all(len(signals[n]) == 384 * 80 for n in long.INSTRUMENTS))
            self.assertTrue(any(n == 'sho' and seconds > 96 for n, seconds, _, _ in calls))
            for boundary in (96, 192, 288):
                frame = boundary * 80
                self.assertGreater(signals['sho'][frame], 0)
                self.assertEqual(signals['sho'][frame], signals['sho'][frame - 1])
            self.assertTrue(all(attack == .15 and release == .25 for _, _, attack, release in calls))

    def test_all_deadlines_are_conservative_with_subframe_requests(self):
        for index, boundary in enumerate(long.EXIT_SECONDS):
            deadline = boundary - .25
            for offset in (-1, -.75, -.25, 0, .25, .75, 1):
                seconds = deadline + offset / FS
                result = long.finish_plan(seconds)
                expected = boundary if offset <= 0 or boundary == 384 else long.EXIT_SECONDS[index + 1]
                self.assertEqual(result['end_frame'], expected * FS)
                self.assertLessEqual(result['request_frame'], result['end_frame'])
                self.assertEqual(result['release_start_frame'], round((expected - .25) * FS))
                self.assertEqual(result['full_release_after_request'], seconds <= expected - .25)
                self.assertFalse(result['verified_exit'])
                self.assertFalse(result['tomede'])
        for seconds in (383.750001, 383.9, 384):
            result = long.finish_plan(seconds)
            self.assertEqual(result['end_frame'], 384 * FS)
            self.assertEqual(result['request_status'], 'bounded_terminal_completion_release_already_scheduled')
            self.assertFalse(result['full_release_after_request'])
        self.assertEqual(long.finish_plan(0)['end_frame'], 96 * FS)

    def test_requests_deterministic_and_nonpromoted(self):
        logs = long.exit_requests()
        self.assertEqual(len(logs), 1034)
        self.assertEqual(logs, long.exit_requests())
        self.assertEqual({e['end_frame'] for e in logs}, {t * FS for t in long.EXIT_SECONDS})
        self.assertTrue(all(e['verified_exit'] is False and e['tomede'] is False for e in logs))

    def test_only_authored_exits_are_rendered_and_release_is_complete(self):
        with patch.object(long, 'FS', 80):
            signal = array('f', [.2, -.2]) * (384 * 80)
            for boundary in long.EXIT_SECONDS:
                exit_signal = long.boundary_exit(signal, 2, boundary * 80)
                self.assertEqual(len(exit_signal), boundary * 80 * 2)
                start = (boundary * 80 - 20) * 2
                self.assertEqual(exit_signal[:start], signal[:start])
                self.assertEqual(exit_signal[start:start + 2], signal[start:start + 2])
                self.assertEqual(list(exit_signal[-2:]), [0, 0])
                self.assertLess(abs(exit_signal[-4]), abs(exit_signal[-6]))
            for channels, frame in ((0, 96 * 80), (3, 96 * 80), (True, 96 * 80),
                                    (1.0, 96 * 80), (2, 95 * 80), (2, True), (2, 385 * 80)):
                with self.assertRaises(ValueError):
                    long.boundary_exit(signal, channels, frame)
            with self.assertRaises(ValueError):
                long.boundary_exit(array('f', [0, 0]), 2, 96 * 80)

    def test_reject_bad_requests_and_modified_ledger(self):
        for seconds in (-1, 384 + 1 / FS, float('nan'), float('inf'), float('-inf'), True, None, '96'):
            with self.assertRaises(ValueError):
                long.finish_plan(seconds)
        events = long.plan()
        for bad in (None, [], events[:-1], events + [events[0]], [None] * len(events)):
            with self.assertRaises(ValueError):
                long.validate(bad)
        for key, value in (('performance_verified', True), ('start', float('nan')),
                           ('midi', 1), ('cell_ids', []), ('pass_number', 1), ('id', []),
                           ('chant_candidate', 'incorrect')):
            bad = copy.deepcopy(events)
            bad[-1][key] = value
            with self.assertRaises(ValueError):
                long.validate(bad)

    def test_source_drift_or_policy_promotion_fails_closed(self):
        with patch.object(long, 'digest', return_value='0' * 64):
            with self.assertRaises(ValueError):
                long.plan()
        original = json.loads(long.SPEC.read_text())
        for change in ('tomede', 'verified_exit', 'traditional_nihen_verified', 'strict_reading_status'):
            spec = copy.deepcopy(original)
            if change in ('tomede', 'verified_exit'):
                spec['exit_adoption'][change] = True
            elif change == 'traditional_nihen_verified':
                spec['repeat_adoption'][change] = True
            else:
                spec[change] = 'PASS'
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'spec.json'
                path.write_text(json.dumps(spec))
                with patch.object(long, 'SPEC', path), self.assertRaises(ValueError):
                    long.plan()


if __name__ == '__main__':
    unittest.main()
