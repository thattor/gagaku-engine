import copy
import unittest
from .three_pipe_body import plan,validate,sounding_spans

class BodyTest(unittest.TestCase):
    def test_full_body_and_new_cells(self):
        events=plan()
        for inst in ('sho','ryuteki','hichiriki'):
            self.assertEqual(len({c for e in events if e['instrument']==inst for c in e['cell_ids']}),32)
        self.assertTrue(all(e['performance_verified'] is False for e in events))
        self.assertEqual(max(e['end'] for e in events),96)
    def test_reject_gap_and_promotion(self):
        for mutation in ('gap','promotion','nonfinite','missing'):
            events=copy.deepcopy(plan())
            if mutation=='gap': events[0]['start']=.01
            if mutation=='promotion':events[0]['performance_verified']=True
            if mutation=='nonfinite':events[0]['end']=float('nan')
            if mutation=='missing':events=[e for e in events if 'ryuteki.L4.P8' not in e['cell_ids']]
            with self.assertRaises(ValueError):validate(events)
    def test_specials_remain_hypotheses(self):
        events=plan()
        special=[e for e in events if e.get('special_adoption')]
        self.assertTrue(special)
        self.assertTrue(all(e['reading_status']=='explicit_adopted_hypothesis' for e in special))
        self.assertEqual([e['midi'] for e in events if e['cell_ids']==['ryuteki.L3.P3']],[86,85])

    def test_continuation_keeps_waveform_span(self):
        events=plan();spans=sounding_spans(events)
        span=next(s for s in spans if 'ryuteki.L2.P5.N1' in s['ledger_ids'])
        self.assertIn('ryuteki.L2.P6.N1',span['ledger_ids'])
        self.assertEqual((span['start'],span['end']),(36,42))
        self.assertEqual({i for s in spans for i in s['ledger_ids']},{e['id'] for e in events})

if __name__=='__main__':unittest.main()
