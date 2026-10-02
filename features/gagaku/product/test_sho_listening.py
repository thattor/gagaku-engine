import copy
import unittest
from .sho_listening import schedule, validate

class ListeningControls(unittest.TestCase):
    def test_ordered_operations(self):
        events=schedule(True); validate(events)
        starts={e['pipe']:e['start'] for e in events if e['cell_id']=='sho.L3.P6'}
        ends={e['pipe']:e['end'] for e in events if e['cell_id']=='sho.L3.P5+P6'}
        self.assertLess(ends['凢'],ends['一'])
        self.assertEqual(ends['一'],starts['乞'])
        self.assertGreater(starts['八'],starts['乞'])
        ju=[e for e in events if e['cell_id']=='sho.L4.P3']
        self.assertLess(next(e['end'] for e in ju if e['pipe']=='八'),10.5)
        self.assertEqual(next(e['end'] for e in ju if e['pipe']=='十'),next(e['start'] for e in ju if e['pipe']=='千'))
        self.assertEqual(next(e['start'] for e in ju if e['pipe']=='美'),10.5)
    def test_common_pipes_and_hold_not_retriggered(self):
        events=schedule(True)
        for p in ('乙','行','七','千'):
            self.assertEqual(sum(e['pipe']==p and e['start']<6 for e in events),1)
        for cell in ('sho.L2.P5+P6','sho.L4.P5+P6'):
            self.assertTrue(all(e['end']-e['start']==3 for e in events if e['cell_id']==cell))
    def test_rejects_bad_controls(self):
        for field,value in [('start',float('nan')),('end',19),('cell_id',None),('timing_status','verified')]:
            events=copy.deepcopy(schedule(True)); events[0][field]=value
            with self.assertRaises(ValueError): validate(events)
        events=schedule(True); events.append(copy.deepcopy(events[0]))
        with self.assertRaises(ValueError): validate(events)
    def test_baseline_keeps_unread_gaps(self):
        events=schedule(False); validate(events)
        self.assertFalse(any(e['start']<6 and e['end']>3 for e in events))
        self.assertFalse(any(e['start']<12 and e['end']>9 for e in events))
