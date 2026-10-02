"""24-second first-line three-pipe candidate, with an excerpt fade only."""
import argparse
from array import array
import json
from pathlib import Path
import subprocess
import sys
import wave

from .audio import ROOT, digest, make_bank, save_json, write_wav
from .models import FS
from .three_pipe_prefix import INSTRUMENTS, _compile_plan, render, validate

PRIMARY_COUNT=8
DURATION=24.0


def plan():
    events=_compile_plan(PRIMARY_COUNT)
    validate(events,PRIMARY_COUNT)
    return events


def generate(directory):
    out=Path(directory); out.mkdir(parents=True,exist_ok=True)
    bank,bank_metadata=make_bank(out/'bank')
    events=plan(); stems,mix,measured=render(bank,events,PRIMARY_COUNT)
    signals={**stems,'ensemble':mix}
    files=[write_wav(out/f'three-pipe-line1-{name}-24s.wav',2 if name=='ensemble' else 1,[signal])
           for name,signal in signals.items()]
    second,_=make_bank(out/'regeneration-bank')
    regenerated,regen_mix,_=render(second,plan(),PRIMARY_COUNT)
    regenerated['ensemble']=regen_mix
    for name,entry in zip(signals,files):
        check=write_wav(out/f'.regen-{name}.wav',entry['channels'],[regenerated[name]])
        if check['sha256']!=entry['sha256']:
            raise ValueError('independent PCM regeneration differs')
        (out/f'.regen-{name}.wav').unlink()
        with wave.open(str(out/entry['file'])) as wav:
            pcm=array('h',wav.readframes(wav.getnframes()))
            if sys.byteorder!='little': pcm.byteswap()
            if (wav.getframerate(),wav.getnframes(),wav.getnchannels(),wav.getsampwidth())!=(FS,1152000,entry['channels'],2):
                raise ValueError('wrong delivered WAV shape')
            if max(map(abs,pcm))>=32767 or any(pcm[-entry['channels']:]):
                raise ValueError('clipped PCM or nonzero excerpt endpoint')
    # Record the settled active pitches at every primary-cell midpoint.
    coverage=[]
    for primary in range(1,PRIMARY_COUNT+1):
        time=(primary-.5)*3
        coverage.append({'primary_point':primary,'time':time,
                         'active':{name:[e['id'] for e in events if e['instrument']==name and e['start']<=time<e['end']]
                                   for name in INSTRUMENTS}})
    if any(not row['active'][name] for row in coverage for name in INSTRUMENTS):
        raise ValueError('uncovered primary point')
    inputs=[Path(__file__),ROOT/'three_pipe_prefix.py',ROOT/'score-fixture.json',ROOT/'sho-continuous-v1.json',
            ROOT/'sho_continuous.py',ROOT/'sho_adoption.py',ROOT/'sho-adoption-v1.json',ROOT/'audio.py',ROOT/'models.py',
            ROOT.parent/'evaluate.py',ROOT.parent/'sho_one_pipe.py',ROOT/'three-pipe-line1-player.html',
            ROOT.parents[2]/'docs/tasks/three-pipe-line1-v1/README.md']
    report={'version':'three-pipe-line1-v1','scope':'first eight primary cells of each instrument once, no repeat or tomede',
            'source_commit':subprocess.check_output(['git','-C',str(ROOT.parents[2]),'rev-parse','HEAD'],text=True).strip(),
            'dependency_commit':'edc50061ed2cf06c47737701c9db10bb5550234c','duration_seconds':DURATION,'primary_cells':24,
            'scheduled_voice_spans':len(events),'instrument_voice_spans':{n:sum(e['instrument']==n for e in events) for n in INSTRUMENTS},
            'independent_regeneration_pcm_identical':True,'metrics':measured,'files':files,'physical_bank':bank_metadata,
            'a4_hz':430,'seconds_per_primary_cell':3,'attack_seconds':.15,'release_seconds':.25,
            'exit':{'kind':'author_excerpt_fade','end_seconds':24,'verified_exit':False,'tomede':False,'final_pcm_samples_zero':True},
            'primary_point_coverage':coverage,'source_hashes':{str(p.relative_to(ROOT.parents[2])):digest(p) for p in inputs},
            'mix_coefficients':{'left':{'sho':.7,'ryuteki':.85,'hichiriki':.5},'right':{'sho':.7,'ryuteki':.5,'hichiriki':.85}},
            'sanity_limits':{'peak':.9,'max_channel_sample_step':.4,'minimum_interior_100ms_rms':1e-6,'classification':'author numeric checks, not musical acceptance'},
            'fully_verified_performance_events':0,'required_complete_performance_events':None,
            'strict_reading_status':'BLOCKED_PUBLIC_EVIDENCE','musical_acceptance':'UNEVALUATED; subjective 80 not reached or tested',
            'unverified':'ryuteki pitch/register/ornaments and hichiriki expression inherited candidates; no new independent score reading',
            'rights':'own physical model bank only; no third-party recording or new measurement'}
    (out/'three-pipe-line1-player.html').write_bytes((ROOT/'three-pipe-line1-player.html').read_bytes())
    save_json(out/'three-pipe-line1-events-v1.json',events)
    save_json(out/'three-pipe-line1-inspection-v1.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True,type=Path)
    generate(parser.parse_args().output_dir)
