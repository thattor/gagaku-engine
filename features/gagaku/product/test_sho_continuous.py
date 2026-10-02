import copy
import unittest
from .sho_continuous import checkpoints, controls, spans, validate_checkpoints, validate_spans, load_control, validate_control

class ContinuousCandidate(unittest.TestCase):
    def test_contiguous_coverage_with_two_compounds(self):
        points=checkpoints('1932')
        self.assertEqual(len(points),34)
        self.assertEqual((points[0]['start'],points[-1]['end']),(0,48))
        for a,b in zip(points,points[1:]): self.assertEqual(a['end'],b['start'])
        for cell in ('sho.L3.P6','sho.L4.P3'):
            self.assertEqual([p['end']-p['start'] for p in points if p['cell_id']==cell],[.75,.75])
    def test_edition_difference_is_explicit(self):
        variants=[checkpoints(edition) for edition in ('1932','1894')]
        for a,b in zip(*variants):
            if a['cell_id']=='sho.L2.P3':
                self.assertEqual(set(a['pipes'])-set(b['pipes']),{'下'})
                self.assertEqual(set(b['pipes'])-set(a['pipes']),{'乙'})
            else:
                self.assertEqual(a,b)
        with self.assertRaises(ValueError): checkpoints('automatic')
    def test_five_continuations_do_not_retrigger(self):
        points=checkpoints('1932'); changes=controls(points)
        for cell in ('sho.L1.P2','sho.L2.P6','sho.L2.P8','sho.L4.P6','sho.L4.P8'):
            point=next(p for p in points if p['cell_id']==cell)
            change=next(c for c in changes if c['time']==point['start'])
            self.assertEqual((change['remove'],change['add']),([],[]))
    def test_explicit_modern_sequences(self):
        points=checkpoints('1932'); changes=controls(points)
        for pair,expected in [('ichi_kotsu',[(32.15,['凢'],[]),(32.25,['一'],['乞']),(32.35,[],['八'])]),
                              ('ju_ge',[(39.65,['八'],[]),(39.75,['十'],['千','美'])])]:
            actual=[(c['time'],c['remove'],c['add']) for c in changes if pair in c['kind']]
            self.assertEqual(actual,expected)
    def test_every_settled_checkpoint_matches_pipe_spans(self):
        for edition in ('1932','1894'):
            points=checkpoints(edition); events=spans(points,controls(points))
            for p in points:
                t=(p['start']+p['end'])/2
                self.assertEqual({e['pipe'] for e in events if e['start']<=t<e['end']},set(p['pipes']))
            # 行/七 are common to every selected checkpoint: one uninterrupted span each.
            for pipe in ('行','七'):
                self.assertEqual([(e['start'],e['end']) for e in events if e['pipe']==pipe],[(0,48)])
    def test_rejects_checkpoint_gaps_and_missing_compound(self):
        points=checkpoints('1932'); points[2]['start']+=.1
        with self.assertRaises(ValueError): validate_checkpoints(points)
        points=checkpoints('1932'); points.pop()
        with self.assertRaises(ValueError): validate_checkpoints(points)
        points=checkpoints('1932'); points[0]['performance_verified']=True
        with self.assertRaises(ValueError): validate_checkpoints(points)
    def test_rejects_duplicate_nonfinite_and_untraced_voice(self):
        points=checkpoints('1932'); base=spans(points,controls(points))
        for field,value in [('start',float('nan')),('end',49),('checkpoint_ids',[]),('performance_verified',True)]:
            events=copy.deepcopy(base); events[0][field]=value
            with self.assertRaises(ValueError): validate_spans(events)
        events=copy.deepcopy(base); events.append(copy.deepcopy(events[0]))
        with self.assertRaises(ValueError): validate_spans(events)
    def test_rejects_bad_control_operations(self):
        points=checkpoints('1932'); changes=controls(points)
        changes[0]['add'].append(changes[0]['add'][0])
        with self.assertRaises(ValueError): spans(points,changes)
    def test_incomplete_knowledge_is_not_promoted(self):
        points=checkpoints('1932')
        self.assertEqual(sum(p['reading_status']=='inherited_legacy_not_rechecked' for p in points),24)
        self.assertFalse(any(p['performance_verified'] for p in points))
        self.assertTrue(all(p['timing_status']=='author_design' for p in points))

    def test_rejects_review_status_and_source_counterexamples(self):
        for key,value in [('glyph_status','verified'),('sources',[{}])]:
            control=load_control(); control['extra_reading'][key]=value
            with self.assertRaises(ValueError): validate_control(control)
        for key,value in [('reading_status','verified'),('reading_evidence',{}),('source',{}),('symbol','乙'),('part',2)]:
            points=checkpoints('1932'); points[1][key]=value
            with self.assertRaises(ValueError): validate_checkpoints(points)
