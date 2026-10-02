"""96-second adopted body candidate. No initial/return variant or tomede."""
import argparse
from array import array
import json
import math
from pathlib import Path
import subprocess
import wave
from .audio import ROOT, digest, make_bank, save_json, voice, write_wav
from .models import FS
from .three_pipe_prefix import _compile_plan, INSTRUMENTS, metrics
from .sho_continuous import checkpoints, controls, spans

SPEC=ROOT/'three-pipe-body-v1.json'
DURATION=96.0

def _compile_body():
    spec=json.loads(SPEC.read_text())
    if (spec['sho_edition']!='1932' or spec['seconds_per_primary_cell']!=3 or
        spec['fully_verified_performance_events']!=0 or spec['musical_acceptance']!='UNEVALUATED'):
        raise ValueError('candidate policy changed')
    # Keep the inherited first melodic line unchanged; compile the entire adopted sho body once.
    events=[e for e in _compile_plan(8) if e['instrument']!='sho']
    points=checkpoints('1932')
    pitch=json.loads((ROOT/'sho-adoption-v1.json').read_text())['pipe_midi']
    for event in spans(points,controls(points)):
        evidence=[p for p in points if p['id'] in event['checkpoint_ids']]
        events.append({'id':f'sho.body.N{len(events)}','instrument':'sho','pipe':event['pipe'],
                       'midi':pitch[event['pipe']],'start':event['start']*2,'end':event['end']*2,
                       'cell_ids':list(dict.fromkeys(p['cell_id'] for p in evidence)),
                       'reading_evidence':evidence,'reading_status':'adopted_1932_candidate',
                       'timing_status':'author_design','performance_verified':False})
    expected={f'{inst}.L{line}.P{point}' for inst in ('ryuteki','hichiriki') for line in range(2,5) for point in range(1,9)}
    if len(spec['cells'])!=48 or {c['id'] for c in spec['cells']}!=expected:
        raise ValueError('missing or duplicate transcribed body cell')
    for inst in ('ryuteki','hichiriki'):
        previous=next(e['midi'] for e in reversed(events) if e['instrument']==inst)
        rows=sorted((c for c in spec['cells'] if c['instrument']==inst),key=lambda c:(c['line'],c['primary']))
        for cell in rows:
            signs=cell['finger_candidates']
            if not signs or cell['performance_verified'] is not False or len(cell['source']['sha256'])!=64:
                raise ValueError('bad source/candidate policy')
            start=((cell['line']-1)*8+cell['primary']-1)*3
            for index,sign in enumerate(signs):
                midi=spec['midi_adoption'][inst].get(sign)
                if midi is None:
                    if sign not in spec['special_adoption']:raise ValueError('unknown sign without adoption')
                    midi=previous
                events.append({'id':f"{cell['id']}.N{index+1}",'instrument':inst,'midi':midi,
                               'start':start+3*index/len(signs),'end':start+3*(index+1)/len(signs),
                               'cell_ids':[cell['id']],'source':cell['source'],'finger_candidate':sign,
                               'chant_candidate':cell['chant_candidate'],'glyph_status':cell['glyph_status'],
                               'reading_status':'explicit_adopted_hypothesis','timing_status':'author_design',
                               'special_adoption':spec['special_adoption'].get(sign),'performance_verified':False})
                previous=midi
    return events

def plan():
    events=_compile_body()
    validate(events)
    return events

def validate(events):
    expected={f'{inst}.L{line}.P{point}' for inst in INSTRUMENTS for line in range(1,5) for point in range(1,9)}
    if {c for e in events for c in e['cell_ids']}!=expected or len({e['id'] for e in events})!=len(events):
        raise ValueError('body coverage/identities')
    for e in events:
        if (e['performance_verified'] is not False or e['timing_status']!='author_design' or
            type(e['midi']) is not int or not 0<=e['midi']<=127 or
            not all(math.isfinite(e[k]) for k in ('start','end')) or not 0<=e['start']<e['end']<=DURATION):
            raise ValueError('invalid or promoted event')
    canonical={e['id']:e for e in _compile_body()}
    if any(e!=canonical.get(e['id']) for e in events):raise ValueError('schedule differs from pinned adoption')
    for inst in INSTRUMENTS:
        selected=[e for e in events if e['instrument']==inst]
        for pipe in ({e['pipe'] for e in selected} if inst=='sho' else {None}):
            ordered=sorted((e for e in selected if inst!='sho' or e['pipe']==pipe),key=lambda e:e['start'])
            if any(a['end']>b['start']+1e-9 for a,b in zip(ordered,ordered[1:])):raise ValueError('overlap')
            if inst!='sho' and (ordered[0]['start']!=0 or ordered[-1]['end']!=DURATION or any(abs(a['end']-b['start'])>1e-9 for a,b in zip(ordered,ordered[1:]))):
                raise ValueError('melody gap')

def sounding_spans(events):
    """Continue waveform across explicitly adopted non-pitch marks; retain ledger IDs."""
    result=[dict(e,ledger_ids=[e['id']]) for e in events if e['instrument']=='sho']
    for inst in ('ryuteki','hichiriki'):
        current=None
        for event in sorted((e for e in events if e['instrument']==inst),key=lambda e:e['start']):
            continued=event.get('finger_candidate') in ('く','ノ','continuation','セ候補')
            if continued and current and current['midi']==event['midi'] and abs(current['end']-event['start'])<1e-9:
                current['end']=event['end'];current['ledger_ids'].append(event['id'])
            else:
                current=dict(event,ledger_ids=[event['id']]);result.append(current)
    return result

def render(bank,events):
    validate(events)
    stems={n:array('f',[0])*round(DURATION*FS) for n in INSTRUMENTS}
    for e in sounding_spans(events):
        # Rounded sample boundaries prevent fractional partitions from overrunning the destination.
        start,end=round(e['start']*FS),round(e['end']*FS)
        signal=voice(bank,e['instrument'],e['midi']+12*math.log2(430/440),(end-start)/FS,.15,.25)
        if len(signal)!=end-start:raise ValueError('voice length')
        for i,v in enumerate(signal):stems[e['instrument']][start+i]+=v
    mix=array('f')
    for a,b,c in zip(stems['sho'],stems['ryuteki'],stems['hichiriki']):mix.extend((a*.7+b*.85+c*.5,a*.7+b*.5+c*.85))
    measured={n:metrics(s) for n,s in stems.items()};measured['ensemble']=metrics(mix,2)
    if any(m['nonfinite_count'] or m['full_scale_count'] for m in measured.values()):raise ValueError('invalid audio')
    return {**stems,'ensemble':mix},measured

def generate(directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    bank,metadata=make_bank(out/'bank');events=plan();signals,measured=render(bank,events)
    files=[write_wav(out/f'three-pipe-body-{n}-96s.wav',2 if n=='ensemble' else 1,[s]) for n,s in signals.items()]
    second,_=make_bank(out/'regeneration-bank');regenerated,_=render(second,plan())
    for (n,s),entry in zip(regenerated.items(),files):
        check=write_wav(out/f'.regen-{n}.wav',entry['channels'],[s])
        if check['sha256']!=entry['sha256']:raise ValueError('independent regeneration mismatch')
        (out/f'.regen-{n}.wav').unlink()
        with wave.open(str(out/entry['file'])) as w:
            pcm=array('h',w.readframes(w.getnframes()))
            if (w.getframerate(),w.getnframes(),w.getnchannels(),w.getsampwidth())!=(FS,4608000,entry['channels'],2) or max(map(abs,pcm))>=32767 or any(pcm[-entry['channels']:]):raise ValueError('invalid delivered PCM')
    coverage=[{'primary':i+1,'time':(i+.5)*3,'active':{n:[e['id'] for e in events if e['instrument']==n and e['start']<=(i+.5)*3<e['end']] for n in INSTRUMENTS}} for i in range(32)]
    if any(not r['active'][n] for r in coverage for n in INSTRUMENTS):raise ValueError('uncovered primary midpoint')
    sources=[SPEC,Path(__file__),ROOT/'three_pipe_prefix.py',ROOT/'sho_continuous.py',ROOT/'sho-adoption-v1.json',ROOT/'sho-continuous-v1.json',ROOT/'score-fixture.json',ROOT/'audio.py',ROOT/'models.py',ROOT/'sho_adoption.py',ROOT/'body-player.html',ROOT/'score-sources.json',ROOT.parent/'evaluate.py',ROOT.parent/'sho_one_pipe.py',ROOT.parents[2]/'docs/tasks/three-pipe-body-v1/README.md']
    report={'version':'three-pipe-body-v1','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'dependency_commit':'ed6d51afbab1a5c7a68ce766c0e9b3110d4f673b','duration_seconds':DURATION,'primary_cells':96,
            'new_melodic_cells':48,'primary_midpoint_coverage':coverage,'event_count':len(events),'rendered_spans':len(sounding_spans(events)),'metrics':measured,'files':files,'physical_bank':metadata,
            'independent_regeneration_pcm_identical':True,'source_hashes':{str(p.relative_to(ROOT.parents[2])):digest(p) for p in sources},
            'sho_edition':'1932','a4_hz':430,'seconds_per_cell':3,'division':'author equal segment timing',
            'exit':{'kind':'author_excerpt_release','tomede':False,'verified_exit':False},
            'fully_verified_performance_events':0,'strict_reading_status':'BLOCKED_PUBLIC_EVIDENCE','musical_acceptance':'UNEVALUATED',
            'scope':'four body lines once; initial-only column and 二返 repetition omitted','unknowns':json.loads(SPEC.read_text())['unknowns'],
            'rights':'own model generated signals only; no recordings or new measurements'}
    save_json(out/'body-events.json',events);save_json(out/'body-sounding-spans.json',sounding_spans(events));save_json(out/'body-inspection.json',report)
    (out/'body-player.html').write_bytes((ROOT/'body-player.html').read_bytes())
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',required=True,type=Path)
    generate(parser.parse_args().output_dir)
