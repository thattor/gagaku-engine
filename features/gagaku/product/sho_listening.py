"""SHO_LISTENING_V1: bounded listening hypotheses, never verified score events."""
import argparse
from array import array
import json
import math
from pathlib import Path
from .audio import ROOT, digest, inspect, save_json, voice, write_wav
from .models import FS
from features.gagaku.sho_one_pipe import render as physical_render
from features.gagaku.evaluate import _estimate_f0

DURATION = 18
from .sho_adoption import load_spec, build_body

# Use the explicit adoption version; preserve the frozen baseline's 行 only
# in the baseline comparison branch, not as an adopted continuation symbol.
ADOPTION = load_spec()
PITCH = ADOPTION['pipe_midi']
CHORD = {**ADOPTION['chords'], '行':list('行七上八千')}


def make_sho_bank():
    # Same physical generator/folding/gain as frozen audio.make_bank, sho only.
    raw = physical_render(seconds=2)
    inspect(raw)
    stable = raw[FS:]
    mean = sum(stable)/len(stable)
    stable = [x-mean for x in stable]
    f0 = _estimate_f0(stable, FS, 470)
    period = FS/f0
    loop=[]
    for phase in range(1024):
        values=[]
        for cycle in range(32):
            position=(cycle+phase/1024)*period
            i=int(position); fraction=position-i
            values.append(stable[i]*(1-fraction)+stable[i+1]*fraction)
        loop.append(sum(values)/32)
    return {'sho':{'loop':loop,'reference_hz':f0,'gain':.035/inspect(loop)['rms']}}


def span(pipe, start, end, cell):
    return {'pipe':pipe,'midi':PITCH[pipe],'start':start,'end':end,'cell_id':cell,
            'timing_status':'author_design','technique_status':'listening_hypothesis',
            'source': {'score_cell_ids': [cell.split('+')[0]] + ([cell.split('+')[0].rsplit('.',1)[0]+'.'+cell.split('+')[1]] if '+' in cell else []),
                       'adoption_record':'docs/tasks/sho-listening-v1/README.md',
                       'sources':'docs/tasks/sho-listening-v1/sources.json',
                       'adoption_version':'sho-adoption-v1'}}


def chord(symbol,start,end,cell):
    return [span(p,start,end,cell) for p in CHORD[symbol]]


def schedule(corrected):
    # Refuse baseline drift and invalid adoption before using the corrected path.
    if corrected:
        build_body()
    # Four noncontiguous excerpts, each original preceding cell included.
    events=chord('一',0,3,'sho.L3.P5')+chord('乞',6,9,'sho.L4.P2')
    if corrected:
        # Common pipes held across compound; no whole-chord crossfade.
        events=[]
        for p in CHORD['一']:
            end=4.3 if p=='凢' else 4.5 if p=='一' else 6
            events.append(span(p,0,end,'sho.L3.P5+P6'))
        events += [span('乞',4.5,6,'sho.L3.P6'),span('八',4.7,6,'sho.L3.P6')]
        events += chord('乞',6,9,'sho.L4.P2')
        for p in CHORD['十']:
            end=10.3 if p=='八' else 10.5 if p=='十' else 12
            events.append(span(p,9,end,'sho.L4.P3'))
        events += [span('千',10.5,12,'sho.L4.P3'),span('美',10.5,12,'sho.L4.P3')]
        events += chord('一',12,15,'sho.L2.P5+P6')
        events += chord('乙',15,18,'sho.L4.P5+P6')
    else:
        # Frozen fixture has unresolved compounds => 3..6 and 9..12 silence.
        events += chord('一',12,13.5,'sho.L2.P5')+chord('行',13.5,15,'sho.L2.P6')
        events += chord('乙',15,16.5,'sho.L4.P5')+chord('行',16.5,18,'sho.L4.P6')
    for event in events:
        event['source']['interpretation_role']='corrected_candidate' if corrected else 'frozen_baseline_comparison'
        if not corrected:
            event['source']['adoption_version']='frozen-score-fixture'
            event['source']['adoption_record']='features/gagaku/product/score-fixture.json'
    return events


def validate(events):
    for event in events:
        if event['pipe'] not in PITCH or event['midi'] != PITCH[event['pipe']]:
            raise ValueError('unknown/mismatched pipe')
        if not event.get('cell_id') or not all(math.isfinite(event[k]) for k in ('start','end')):
            raise ValueError('missing provenance or nonfinite time')
        if not 0 <= event['start'] < event['end'] <= DURATION:
            raise ValueError('out of excerpt')
        if event['timing_status'] != 'author_design' or event['technique_status'] != 'listening_hypothesis':
            raise ValueError('cannot promote listening events to verified')
    for pipe in PITCH:
        ordered=sorted((e for e in events if e['pipe']==pipe),key=lambda e:e['start'])
        if any(a['end']>b['start'] for a,b in zip(ordered,ordered[1:])):
            raise ValueError('duplicate overlapping pipe')


def render(bank,events):
    validate(events)
    signal=array('f',[0])*round(DURATION*FS)
    offset=12*math.log2(430/440)
    for event in events:
        sample=voice(bank,'sho',event['midi']+offset,event['end']-event['start'],.15,.25)
        pos=round(event['start']*FS)
        for i,value in enumerate(sample): signal[pos+i]+=value
    inspect(signal)
    return signal


def generate(out):
    out.mkdir(parents=True,exist_ok=True)
    bank=make_sho_bank()
    samples={name:render(bank,schedule(name=='corrected')) for name in ('baseline','corrected')}
    files=[]
    metrics={}
    for name,signal in samples.items():
        metrics[name]=inspect(signal)
        metrics[name]['nonfinite_count']=sum(not math.isfinite(x) for x in signal)
        metrics[name]['full_scale_count']=sum(abs(x)>=1 for x in signal)
        metrics[name]['max_sample_step']=max(abs(b-a) for a,b in zip(signal,signal[1:]))
        metrics[name]['dc_mean']=sum(signal)/len(signal)
        # Broad numeric sanity guards, author thresholds, not auditory acceptance.
        if metrics[name]['peak'] > .5 or abs(metrics[name]['dc_mean']) > .005 or metrics[name]['max_sample_step'] > .2:
            raise ValueError('abnormal numeric signal; author sanity bound exceeded')
        files.append(write_wav(out/f'sho-{name}-18s.wav',1,[signal]))
        save_json(out/f'{name}.events.json',schedule(name=='corrected'))
    # Rebuild physical bank independently; exact PCM identity, not just event identity.
    second_bank=make_sho_bank()
    for name in samples:
        regen=render(second_bank,schedule(name=='corrected'))
        check=write_wav(out/f'.regen-{name}.wav',1,[regen])
        if check['sha256'] != next(x['sha256'] for x in files if x['file']==f'sho-{name}-18s.wav'):
            raise ValueError('independent regeneration differs')
        (out/f'.regen-{name}.wav').unlink()
    difference=math.sqrt(sum((a-b)**2 for a,b in zip(samples['baseline'],samples['corrected']))/(DURATION*FS))
    if difference <= 0:
        raise ValueError('baseline and corrected audio must differ')
    report={'scope':'SHO_LISTENING_V1 / noncontiguous montage', 'duration_seconds':DURATION,
            'source_commit':__import__('subprocess').check_output(['git','-C',str(ROOT.parents[2]),'rev-parse','HEAD'],text=True).strip(),
            'source_fixture_sha256':digest(ROOT/'score-fixture.json'),
            'adoption_spec_sha256':digest(ROOT/'sho-adoption-v1.json'),
            'adoption_record_sha256':digest(ROOT.parents[2]/'docs/tasks/sho-listening-v1/README.md'),
            'source_evidence_sha256':digest(ROOT.parents[2]/'docs/tasks/sho-listening-v1/sources.json'),
            'code_sha256':{str(p):digest(p) for p in [Path(__file__),ROOT/'sho_adoption.py',ROOT/'audio.py',ROOT.parent/'sho_one_pipe.py']},
            'events':{name:len(schedule(name=='corrected')) for name in samples},
            'files':files,'metrics':metrics,'difference_rms':difference,
            'independent_regeneration_pcm_identical':True,
            'acceptance':'UNEVALUATED; 80 is provisional subjective target, not achieved or calibrated',
            'strict_reading_status':'BLOCKED_PUBLIC_EVIDENCE; zero fully verified performance events; necessary total unknown',
            'rights':'own physical equation output only; no third-party recording or analysis',
            'model':'Hikichi coupled reed/slit/delay one-pipe proxy; own steady-state folding and pitch resampling; not measured multireed/exterior model'}
    save_json(out/'inspection.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True,type=Path)
    generate(parser.parse_args().output_dir)
