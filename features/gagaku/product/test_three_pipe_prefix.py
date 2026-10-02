import copy
import unittest
from .three_pipe_prefix import plan, validate

class PrefixTests(unittest.TestCase):
    def test_coverage_and_continuation(self):
        events=plan()
        self.assertEqual(len(events),29)
        for name in ('ryuteki','hichiriki'):
            notes=sorted((e for e in events if e['instrument']==name),key=lambda e:e['start'])
            self.assertEqual((notes[0]['start'],notes[-1]['end']),(0,15))
            self.assertTrue(all(a['end']==b['start'] for a,b in zip(notes,notes[1:])))
        held=[e for e in events if e['instrument']=='sho' and 'sho.L1.P2' in e['cell_ids']]
        self.assertTrue(held)
        self.assertTrue(all(e['start']==0 and e['end']>=6 for e in held))

    def test_refuses_promotions_and_source_pitch_changes(self):
        for field,value in [('performance_verified',True),('reading_status','verified'),('midi',1),('reading_evidence',[])]:
            with self.subTest(field=field):
                events=copy.deepcopy(plan());events[0][field]=value
                with self.assertRaises(ValueError): validate(events)

    def test_refuses_coverage_gaps_overlap_and_nonfinite(self):
        for mutation in ('missing','gap','overlap','nan'):
            events=copy.deepcopy(plan())
            target=next(e for e in events if e['instrument']=='ryuteki')
            if mutation=='missing': events.remove(target)
            elif mutation=='gap': target['end']-=.01
            elif mutation=='overlap': target['end']+=.01
            else: target['start']=float('nan')
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): validate(events)

if __name__=='__main__': unittest.main()
