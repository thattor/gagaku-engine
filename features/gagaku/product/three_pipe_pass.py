"""Two full-body passes with explicit initial glyph adoption and candidate exits."""
import argparse
from array import array
import json
import math
from pathlib import Path
import random
import subprocess
import wave
from .audio import ROOT,digest,make_bank,save_json,voice,write_wav
from .models import FS
from .three_pipe_body import plan as body_plan,sounding_spans as body_spans
from .three_pipe_prefix import INSTRUMENTS,metrics
SPEC=ROOT/'three-pipe-pass-v1.json'
DURATION=192
BODY=96
RELEASE=.25

def finish_plan(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<=seconds<=DURATION:
        raise ValueError('request outside bounded candidate performance')
    frame=math.floor(seconds*FS+1e-7)
    boundary=BODY if seconds<=BODY-RELEASE else DURATION
    return {'request_frame':frame,'end_frame':boundary*FS,'release_start_frame':round((boundary-RELEASE)*FS),
            'verified_exit':False,'tomede':False,'kind':'author_body_boundary_release'}

def _compile():
    spec=json.loads(SPEC.read_text())
    if spec['passes']!=2 or spec['body_seconds']!=96 or spec['fully_verified_performance_events']!=0 or spec['exit_adoption']['verified_exit'] is not False or spec['exit_adoption']['tomede'] is not False or spec['initial_adoption']['performance_verified'] is not False or spec['repeat_adoption']['traditional_nihen_verified'] is not False or spec['strict_reading_status']!='BLOCKED_PUBLIC_EVIDENCE' or spec['musical_acceptance']!='UNEVALUATED':
        raise ValueError('wrong or promoted pass policy')
    base=body_plan();result=[]
    for index in range(2):
        for event in base:
            e=dict(event,id=f"pass{index+1}.{event['id']}",start=event['start']+index*BODY,end=event['end']+index*BODY,
                   source_event_id=event['id'],pass_number=index+1,pass_kind='initial_candidate' if index==0 else 'later_candidate',
                   repeat_status='author_full_body_repeat_not_verified_nihen')
            if e['instrument']=='ryuteki' and len(e['cell_ids'])==1 and e['cell_ids'][0] in spec['initial_adoption']['cells']:
                cell=spec['initial_adoption']['cells'].index(e['cell_ids'][0]);e['chant_candidate']=spec['initial_adoption']['first_pass_chant' if index==0 else 'later_pass_chant'][cell]
                e['initial_adoption']=spec['initial_adoption'];e['initial_status']='glyph_adoption_only_same_pitch_and_time'
            result.append(e)
    return result

def validate(events):
    canonical={e['id']:e for e in _compile()}
    if len(events)!=len(canonical) or len({e['id'] for e in events})!=len(events) or any(e!=canonical.get(e['id']) for e in events):
        raise ValueError('events differ from pinned body/pass adoption')
    for e in events:
        if e['performance_verified'] is not False or not 0<=e['start']<e['end']<=DURATION:raise ValueError('invalid event')
    for index in (1,2):
        for inst in INSTRUMENTS:
            if len({c for e in events if e['pass_number']==index and e['instrument']==inst for c in e['cell_ids']})!=32:raise ValueError('missing pass coverage')

def plan():
    events=_compile();validate(events);return events

def sounding_spans(events):
    validate(events)
    # The body merger handles melodic continuation; preserve trace IDs for every event.
    spans=body_spans(events);result=[]
    for inst in INSTRUMENTS:
        groups={e['pipe'] for e in spans if e['instrument']==inst} if inst=='sho' else {None}
        for pipe in groups:
            current=None
            for e in sorted((s for s in spans if s['instrument']==inst and (inst!='sho' or s['pipe']==pipe)),key=lambda s:s['start']):
                if inst=='sho' and current and current['midi']==e['midi'] and abs(current['end']-e['start'])<1e-9:
                    current['end']=e['end'];current['ledger_ids']+=e['ledger_ids']
                else:
                    current=dict(e);result.append(current)
    return sorted(result,key=lambda e:(e['start'],e['instrument'],e.get('pipe','')))

def render(bank,events):
    stems={n:array('f',[0])*(DURATION*FS) for n in INSTRUMENTS}
    for e in sounding_spans(events):
        start,end=round(e['start']*FS),round(e['end']*FS)
        sound=voice(bank,e['instrument'],e['midi']+12*math.log2(430/440),(end-start)/FS,.15,RELEASE)
        if len(sound)!=end-start:raise ValueError('voice length')
        for i,v in enumerate(sound):stems[e['instrument']][start+i]+=v
    mix=array('f')
    for a,b,c in zip(stems['sho'],stems['ryuteki'],stems['hichiriki']):mix.extend((a*.7+b*.85+c*.5,a*.7+b*.5+c*.85))
    return {**stems,'ensemble':mix}

def boundary_exit(signal,channels,end_frame):
    # Used only for the predeclared early candidate exit; original full performance remains separate.
    signal=array('f',signal[:end_frame*channels]);start=end_frame-round(RELEASE*FS)
    for frame in range(start,end_frame):
        gain=(end_frame-1-frame)/(end_frame-1-start)
        for ch in range(channels):signal[frame*channels+ch]*=gain
    return signal

def generate(directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    events=plan();bank,meta=make_bank(out/'bank');signals=render(bank,events)
    measured={n:metrics(s,2 if n=='ensemble' else 1) for n,s in signals.items()}
    if any(m['nonfinite_count'] or m['full_scale_count'] for m in measured.values()):raise ValueError('invalid generated float signal')
    files=[write_wav(out/f'three-pipe-pass-{n}-192s.wav',2 if n=='ensemble' else 1,[s]) for n,s in signals.items()]
    early=boundary_exit(signals['ensemble'],2,96*FS)
    files.append(write_wav(out/'three-pipe-pass-early-96s.wav',2,[early]))
    second,_=make_bank(out/'regeneration-bank');regen=render(second,plan());regen['early']=boundary_exit(regen['ensemble'],2,96*FS)
    for name,entry in zip([*signals,'early'],files):
        c=write_wav(out/f'.regen-{name}.wav',entry['channels'],[regen[name]])
        if c['sha256']!=entry['sha256']:raise ValueError('independent PCM regeneration mismatch')
        (out/f'.regen-{name}.wav').unlink()
        with wave.open(str(out/entry['file'])) as w:
            pcm=array('h',w.readframes(w.getnframes()))
            expected=96 if name=='early' else DURATION
            if (w.getframerate(),w.getnframes(),w.getnchannels(),w.getsampwidth())!=(FS,expected*FS,entry['channels'],2) or max(map(abs,pcm))>=32767 or any(pcm[-entry['channels']:]):raise ValueError('invalid delivered WAV')
    rng=random.Random(430);requests=[0,95.75,95.75-1/FS,95.75+1/FS,95.75-.25/FS,95.75+.25/FS,95.75-.75/FS,95.75+.75/FS,96,191.75,192]+[rng.uniform(0,192) for _ in range(1000)]
    logs=[finish_plan(t) for t in requests]
    if any(r['end_frame'] not in (96*FS,192*FS) or r['end_frame']<r['request_frame'] or r['verified_exit'] is not False or r['tomede'] is not False for r in logs):raise ValueError('unsafe or promoted candidate exit')
    # Check the actual repeat vicinity with the same author step/RMS bounds as the body.
    at=96*FS*2;window=FS//2*2
    boundary_metrics=metrics(array('f',signals['ensemble'][at-window:at+window]),2)
    inputs=[SPEC,Path(__file__),ROOT/'three_pipe_body.py',ROOT/'three-pipe-body-v1.json',ROOT/'pass-player.html',ROOT/'pass-player.js',ROOT/'audio.py',ROOT/'models.py',ROOT/'three_pipe_prefix.py',ROOT/'sho_continuous.py',ROOT/'sho_adoption.py',ROOT/'sho-adoption-v1.json',ROOT/'sho-continuous-v1.json',ROOT/'score-fixture.json',ROOT.parent/'evaluate.py',ROOT.parent/'sho_one_pipe.py',ROOT.parents[2]/'docs/tasks/three-pipe-pass-v1/README.md']
    report={'version':'three-pipe-pass-v1','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'dependency_commit':json.loads(SPEC.read_text())['dependency_commit'],
            'duration_seconds':192,'body_passes':2,'primary_cell_visits':192,'ledger_events':len(events),'sounding_spans':len(sounding_spans(events)),
            'initial_pitch_difference':False,'initial_timing_difference':False,'metrics':measured,'repeat_boundary_metrics':boundary_metrics,'files':files,'physical_bank':meta,
            'independent_regeneration_pcm_identical':True,'source_hashes':{str(p.relative_to(ROOT.parents[2])):digest(p) for p in inputs},'exit_request_checks':len(logs),
            'eligible_exit_seconds':[96,192],'exit_kind':'author_body_boundary_release','verified_exit':False,'tomede':False,'traditional_nihen_verified':False,
            'fully_verified_performance_events':0,'strict_reading_status':'BLOCKED_PUBLIC_EVIDENCE','musical_acceptance':'UNEVALUATED','rights':'own physical model bank only; no reference recording or new measurement',
            'remaining':json.loads(SPEC.read_text())['remaining']}
    for name in ('pass-player.html','pass-player.js'):(out/name).write_bytes((ROOT/name).read_bytes())
    save_json(out/'pass-events.json',events);save_json(out/'pass-sounding-spans.json',sounding_spans(events));save_json(out/'pass-inspection.json',report);save_json(out/'pass-exit-requests.json',logs)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True,type=Path);generate(p.parse_args().output_dir)
