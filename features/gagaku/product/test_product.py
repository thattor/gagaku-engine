import json
import math
from pathlib import Path
import unittest

from features.gagaku.player import BoundaryError
from .audio import ROOT, inspect, pcm, plan, diagnostic_structure, voice
from .models import jet, reed


class ProductTests(unittest.TestCase):
    def test_production_refuses_diagnostic_substitution(self):
        with self.assertRaises(BoundaryError):
            plan(300, structure=diagnostic_structure())

    def test_unverified_exit_cannot_be_used_even_in_adapter(self):
        structure=diagnostic_structure()
        structure['exit_boundaries'][0]['validation_status']='unverified'
        with self.assertRaises(BoundaryError):
            plan(300, structure=structure, diagnostic=True)

    def test_finish_waits_for_line_four_and_audible_ending(self):
        for request in (0.001,9.99,10.01,39.99,40.01,300,600,1200):
            result=plan(request,structure=diagnostic_structure(),diagnostic=True)
            self.assertEqual(result['ended_phase'],'ended')
            self.assertEqual(result['timeline'][-2]['line'],3)
            self.assertEqual(result['timeline'][-2]['end_phase'],'tomede')
            self.assertGreaterEqual(result['end_seconds']-6,request)
            self.assertEqual(result['timeline'][-1]['seconds'],6)

    def test_defect_detectors_reject_known_failures(self):
        for signal in ([],[0.0]*10,[math.nan,1],[math.inf,1]):
            with self.assertRaises(ValueError): inspect(signal)
        for signal in ([1.0],[-1.0],[math.nan]):
            with self.assertRaises(ValueError): pcm(signal)
        self.assertEqual(len(pcm([0,.25,-.25])),6)

    def test_physical_models_have_sustained_finite_output(self):
        for fn in (reed,jet):
            signal=fn(440,0.5)
            self.assertEqual(len(signal),24000)
            self.assertGreater(inspect(signal[-12000:])['rms'],1e-6)

    def test_voice_envelope_and_pitch(self):
        # Synthetic periodic test input tests interpolation/control, not instrument likeness.
        bank={'sho':{'loop':[math.sin(2*math.pi*i/1024) for i in range(1024)],'gain':.1}}
        from features.gagaku.evaluate import _estimate_f0
        signal=voice(bank,'sho',69,1)
        self.assertEqual(signal[0],0)
        self.assertEqual(signal[-1],0)
        self.assertAlmostEqual(_estimate_f0(list(signal[4800:-4800]),48000,440),440,delta=1)

    def test_allowlist_contains_no_reference_media_or_unknowns(self):
        rights=json.loads((ROOT/'rights.json').read_text())
        materials={x['id']:x for x in rights['materials']}
        for identifier in rights['production_allowlist']:
            material=materials[identifier]
            self.assertEqual(material['status'],'verified')
            self.assertEqual(material['use'],'production_diagnostic')
        self.assertNotIn('ndl-sho-1932',rights['production_allowlist'])

if __name__=='__main__': unittest.main()
