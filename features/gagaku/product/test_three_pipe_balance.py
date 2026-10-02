from array import array
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from .three_pipe_balance import validate_levels, mix_pcm, load_source, write_pcm, read_pcm, SOURCE_INPUTS, APPROVED_AUDIO


class BalanceTests(unittest.TestCase):
    def test_integer_levels_and_missing_or_silent_rejected(self):
        for value in (True, 1.5, float('nan'), -1, 151):
            with self.assertRaises(ValueError): validate_levels({'sho': value, 'ryuteki': 100, 'hichiriki': 100})
        for levels in ({}, {'sho':100,'ryuteki':100}, {'sho':0,'ryuteki':0,'hichiriki':0}):
            with self.assertRaises(ValueError): validate_levels(levels)

    def test_known_channel_values_negative_ties_and_solo(self):
        stems = {'sho':array('h',[1000,5,-5,0]),'ryuteki':array('h',[2000,0,0,0]),'hichiriki':array('h',[-3000,0,0,0])}
        result, metrics = mix_pcm(stems, dict.fromkeys(stems,100))
        self.assertEqual(list(result),[900,-850,4,4,-4,-4,0,0])
        self.assertEqual(metrics['full_scale_count'],0)
        solo,_ = mix_pcm(stems,{'sho':0,'ryuteki':100,'hichiriki':0})
        self.assertEqual(list(solo[:2]),[1700,1000])

    def test_conservative_headroom_and_bad_stems_rejected(self):
        stems = dict.fromkeys(('sho','ryuteki','hichiriki'),array('h',[30000]))
        with self.assertRaises(ValueError): mix_pcm(stems,dict.fromkeys(stems,150))
        rounded={'sho':array('h',[1]),'ryuteki':array('h',[25699]),'hichiriki':array('h',[0])}
        with self.assertRaises(ValueError):mix_pcm(rounded,{'sho':100,'ryuteki':150,'hichiriki':0})
        with self.assertRaises(ValueError): mix_pcm({**stems,'sho':array('h',[1,2])},dict.fromkeys(stems,100))
        with self.assertRaises(ValueError): mix_pcm({**stems,'sho':[1]},dict.fromkeys(stems,100))

    def test_promoted_candidate_and_unknown_recording_rejected(self):
        report={'version':'three-pipe-pass-v1','duration_seconds':192,'verified_exit':True}
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'pass-inspection.json';p.write_text(json.dumps(report))
            with self.assertRaises(ValueError):load_source(directory)
            report.update(verified_exit=False,tomede=False,traditional_nihen_verified=False,fully_verified_performance_events=0,strict_reading_status='BLOCKED_PUBLIC_EVIDENCE',musical_acceptance='UNEVALUATED',files=[{'file':'three-pipe-pass-sho-192s.wav','sha256':'0'*64}])
            p.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'hash'):load_source(directory)

    def test_pcm_export_is_exact_and_wrong_format_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'mix.wav';values=array('h',[900,-850,-4,-4,0,0]);write_pcm(p,values)
            self.assertEqual(read_pcm(p,2,frames=3),values)
            with self.assertRaises(ValueError):read_pcm(p,1,frames=3)

    def test_required_source_paths_cannot_be_replaced_or_omitted(self):
        entries=[{'file':f'three-pipe-pass-{n}-192s.wav','sha256':sorted(APPROVED_AUDIO[n])[0]} for n in (*('sho','ryuteki','hichiriki'),'ensemble')]
        known={e['file']:e['sha256'] for e in entries}
        report={'version':'three-pipe-pass-v1','duration_seconds':192,'verified_exit':False,'tomede':False,'traditional_nihen_verified':False,'fully_verified_performance_events':0,'strict_reading_status':'BLOCKED_PUBLIC_EVIDENCE','musical_acceptance':'UNEVALUATED','files':entries}
        with tempfile.TemporaryDirectory() as directory:
            for replace in (False, True):
                hashes=dict.fromkeys(SOURCE_INPUTS,'a'*64);hashes.pop('features/gagaku/product/three-pipe-pass-v1.json')
                if replace:hashes['AGENTS.md']='a'*64
                report['source_hashes']=hashes
                (Path(directory)/'pass-inspection.json').write_text(json.dumps(report))
                with patch('features.gagaku.product.three_pipe_balance.digest',side_effect=lambda p:known.get(Path(p).name,'a'*64)):
                    with self.assertRaisesRegex(ValueError,'source hashes'):load_source(directory)
