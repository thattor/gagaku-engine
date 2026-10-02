import copy
import unittest
from .three_pipe_line1 import plan
from .three_pipe_prefix import _compile_plan, validate

class Line1Tests(unittest.TestCase):
    def test_first_line_has_complete_melodies_and_held_sho(self):
        events=plan()
        self.assertEqual(len(events),39)
        self.assertEqual({n:sum(e['instrument']==n for e in events) for n in ('sho','ryuteki','hichiriki')},
                         {'sho':16,'ryuteki':14,'hichiriki':9})
        for name in ('sho','ryuteki','hichiriki'):
            self.assertEqual({c for e in events if e['instrument']==name for c in e['cell_ids']},
                             {f'{name}.L1.P{p}' for p in range(1,9)})
        held=[e for e in events if e['instrument']=='sho' and 'sho.L1.P5' in e['cell_ids']]
        self.assertTrue(held)
        self.assertTrue(all('sho.L1.P6' in e['cell_ids'] and e['start']<=12 and e['end']>=18 for e in held))
        for name in ('ryuteki','hichiriki'):
            notes=sorted((e for e in events if e['instrument']==name),key=lambda e:e['start'])
            self.assertEqual((notes[0]['start'],notes[-1]['end']),(0,24))
            self.assertTrue(all(a['end']==b['start'] for a,b in zip(notes,notes[1:])))

    def test_new_cells_cannot_be_promoted_or_retimed(self):
        for field,value in [('performance_verified',True),('reading_status','verified'),('start',float('nan')),
                            ('end',23),('source',None),('midi',1)]:
            events=copy.deepcopy(plan())
            event=next(e for e in events if e['id']=='ryuteki.L1.P8.N1')
            event[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError): validate(events,8)
        events=plan();events.pop()
        with self.assertRaises(ValueError): validate(events,8)

    def test_unsupported_scopes_rejected(self):
        for count in (0,6,9,True):
            with self.subTest(count=count),self.assertRaises(ValueError): _compile_plan(count)

if __name__=='__main__': unittest.main()
