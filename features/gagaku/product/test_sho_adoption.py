import copy
import json
from pathlib import Path
import tempfile
import unittest
from .sho_adoption import load_spec, validate_spec, build_body, FROZEN
from .sho_listening import schedule

class AdoptionConsistency(unittest.TestCase):
    def test_counts_do_not_claim_completed_events(self):
        body=build_body()
        self.assertEqual(len(body['cells']),32)
        self.assertEqual(body['counts']['complete_performance_events_verified'],0)
        self.assertIsNone(body['counts']['complete_performance_events_required'])
        self.assertFalse(body['full_body_synthesis_ready'])
        self.assertEqual(sum(c['candidate_status']=='inherited_legacy_not_rechecked' for c in body['cells']),25)
        self.assertFalse(any(c['performance_verified'] for c in body['cells']))
    def test_corrects_compounds_without_silent_flattening(self):
        rows={c['cell_id']:c for c in build_body()['cells']}
        self.assertEqual(rows['sho.L3.P6']['chord_path'],['一','乞'])
        self.assertEqual(rows['sho.L4.P3']['chord_path'],['十','下'])
        for key in ('sho.L3.P6','sho.L4.P3'):
            self.assertEqual(rows[key]['legacy_symbol'],'九下')
            self.assertEqual(rows[key]['nominal_fractions'],[[1,2],[1,2]])
    def test_all_four_holds_have_predecessor_context(self):
        rows={c['cell_id']:c for c in build_body()['cells']}
        for key,chord in [('sho.L2.P6','一'),('sho.L2.P8','一'),('sho.L4.P6','乙'),('sho.L4.P8','乙')]:
            self.assertEqual(rows[key]['read_symbol'],'引')
            self.assertEqual(rows[key]['chord_path'],[chord])
            self.assertEqual(rows[key]['legacy_symbol'],'行')
    def test_edition_conflict_has_no_selected_pitch_path(self):
        row=next(c for c in build_body()['cells'] if c['cell_id']=='sho.L2.P3')
        self.assertIsNone(row['chord_path'])
        self.assertEqual(set(row['edition_conflict']['1932'])-set(row['edition_conflict']['1894']),{'下'})
        self.assertEqual(set(row['edition_conflict']['1894'])-set(row['edition_conflict']['1932']),{'乙'})
    def test_rejects_verified_promotion_and_missing_source(self):
        spec=load_spec(); spec['performance_verified']=True
        with self.assertRaises(ValueError): validate_spec(spec)
        spec=load_spec(); spec['corrections'][0]['primary_sources']=[]
        with self.assertRaises(ValueError): validate_spec(spec)
    def test_rejects_bad_division_duplicates_and_edition_autoselection(self):
        for change in ('fraction','duplicate','edition'):
            spec=load_spec()
            if change=='fraction': spec['corrections'][0]['nominal_fractions']=[[1,3],[2,3]]
            if change=='duplicate': spec['corrections'][1]=copy.deepcopy(spec['corrections'][0])
            if change=='edition': spec['edition_conflicts']['工']['decision']='1932'
            with self.assertRaises(ValueError): validate_spec(spec)
    def test_rejects_nonadjacent_hold_and_baseline_drift(self):
        spec=load_spec(); spec['corrections'][2]['predecessor_id']='sho.L2.P7'
        with self.assertRaises(ValueError): build_body(spec)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'fixture.json'; path.write_bytes(FROZEN.read_bytes()+b'\n')
            with self.assertRaises(ValueError): build_body(frozen=path)
    def test_rejects_review_counterexamples(self):
        for change in ('path','glyph','pitch','source','variant','operation','duration'):
            spec=load_spec()
            if change=='path': spec['corrections'][0]['chord_path']=['乙','乙']
            if change=='glyph': spec['corrections'][0]['read_symbol']='工'
            if change=='pitch': spec['pipe_midi']['一']=float('nan')
            if change=='source': spec['corrections'][0]['primary_sources']=['not a URL']
            if change=='operation': spec['corrections'][0]['operation_evidence']='not a URL'
            if change=='duration': spec['corrections'][0]['duration_evidence']='unrelated'
            if change=='variant': spec['edition_conflicts']['工']['1932']=['missing']
            with self.assertRaises(ValueError): build_body(spec)
    def test_events_distinguish_frozen_baseline_from_adoption(self):
        for corrected in (False,True):
            role='corrected_candidate' if corrected else 'frozen_baseline_comparison'
            self.assertTrue(all(e['source']['interpretation_role']==role for e in schedule(corrected)))
    def test_does_not_change_prior_listening_controls(self):
        # Pinned PR2 controls; source-only fields may grow, audible controls cannot.
        import hashlib
        keys=('pipe','midi','start','end','cell_id','timing_status','technique_status')
        expected={'baseline':'f3662cc55308b8e5c88c352c0c7cafe5bfd32a66c879f18b47ef83a33608187e','corrected':'250873464d5c2d6bbafb0479204fc22140d000d226b808ad82e821da49fe0fb8'}
        for kind in expected:
            value=[{k:e[k] for k in keys} for e in schedule(kind=='corrected')]
            digest=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
            self.assertEqual(digest,expected[kind])
