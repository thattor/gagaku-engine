import copy
import unittest
from .three_pipe_pass import plan,sounding_spans,finish_plan,validate
class PassTest(unittest.TestCase):
    def test_two_body_visits_and_shared_sho_pipe_hold(self):
        events=plan();spans=sounding_spans(events)
        self.assertEqual(len(events),348)
        self.assertEqual({i for s in spans for i in s['ledger_ids']},{e['id'] for e in events})
        held=[s for s in spans if s['instrument']=='sho' and s['start']<96<s['end']]
        self.assertTrue(held)
        self.assertTrue(all({e.split('.')[0] for e in s['ledger_ids']}=={'pass1','pass2'} for s in held))
    def test_initial_same_pitch_only_glyph_selection(self):
        rows=[e for e in plan() if e.get('initial_adoption')]
        self.assertEqual([e['midi'] for e in rows[:5]],[83,81,81,78,79])
        self.assertEqual([e['midi'] for e in rows[:5]],[e['midi'] for e in rows[5:]])
        self.assertEqual(rows[0]['chant_candidate'],'トロホ')
        self.assertEqual(rows[5]['chant_candidate'],'チラハ')
    def test_reject_mutated_adoption_or_coverage(self):
        events=copy.deepcopy(plan());events[0]['performance_verified']=True
        with self.assertRaises(ValueError):validate(events)
        with self.assertRaises(ValueError):validate(plan()[:-1])
    def test_exit_leaves_full_release_and_never_promotes(self):
        for t,b in [(0,96),(95.75,96),(95.75+1/48000,192),(95.75+.25/48000,192),(95.75+.75/48000,192),(95.75-.25/48000,96),(95.75-.75/48000,96),(96,192),(192,192)]:
            r=finish_plan(t);self.assertEqual(r['end_frame'],b*48000)
            self.assertFalse(r['verified_exit']);self.assertFalse(r['tomede'])
        for t in [-1,193,float('nan'),True]:
            with self.assertRaises(ValueError):finish_plan(t)
if __name__=='__main__':unittest.main()
