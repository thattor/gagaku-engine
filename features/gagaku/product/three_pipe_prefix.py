"""15-second three-pipe integration candidate; no complete musical certification."""
import argparse
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys
import wave

from .audio import ROOT, digest, inspect, make_bank, save_json, voice, write_wav
from .models import FS
from .sho_adoption import BASELINE_SHA
from .sho_continuous import checkpoints, controls, spans

DURATION=15.0
CELL_SECONDS=3.0
INSTRUMENTS=('sho','ryuteki','hichiriki')


def _compile_plan(primary_count=5):
    if type(primary_count) is not int or primary_count not in (5,8):
        raise ValueError("only frozen prefix or first-line candidate supported")
    cutoff=primary_count*1.5
    if digest(ROOT/'score-fixture.json')!=BASELINE_SHA:
        raise ValueError('frozen baseline changed')
    fixture=json.loads((ROOT/'score-fixture.json').read_text())
    prefixes=[[p for p in checkpoints(edition) if p['cell_id'].startswith('sho.L1.') and int(p['cell_id'].split('.P')[1])<=primary_count]
              for edition in ('1932','1894')]
    if prefixes[0]!=prefixes[1]:
        raise ValueError('prefix now depends on unselected edition')
    points=prefixes[0]; result=[]
    # Clip the existing continuous design at the selected cell, then disclose 2x time scaling.
    complete=checkpoints('1932')
    for event in spans(complete,controls(complete)):
        if event['start']>=cutoff: continue
        cell_ids=[p['cell_id'] for p in points if p['id'] in event['checkpoint_ids']]
        if not cell_ids: raise ValueError('sho prefix missing source context')
        pitch=json.loads((ROOT/'sho-adoption-v1.json').read_text())['pipe_midi'][event['pipe']]
        result.append({'id':f'sho.prefix.N{len(result)+1}','instrument':'sho','pipe':event['pipe'],
                       'midi':pitch,'start':event['start']*2,'end':min(cutoff,event['end'])*2,
                       'cell_ids':cell_ids,'reading_evidence':[p for p in points if p['cell_id'] in cell_ids],
                       'reading_status':'sho_continuous_candidate_time_scaled',
                       'timing_status':'author_design','performance_verified':False})
    for instrument in ('ryuteki','hichiriki'):
        for primary in range(1,primary_count+1):
            cell_id=f'{instrument}.L1.P{primary}'
            cell=next(c for c in fixture['cells'] if c['id']==cell_id)
            if not cell.get('source') or not cell.get('midi') or cell['pitch_status']=='unresolved':
                raise ValueError('unknown melody cannot silently fill candidate')
            offsets=cell['offset_pulses']
            if len(offsets)!=len(cell['midi']) or offsets[0]!=0 or offsets!=sorted(set(offsets)) or any(not 0<=o<4 for o in offsets):
                raise ValueError('invalid inherited melody schedule')
            for index,(midi,offset) in enumerate(zip(cell['midi'],offsets)):
                start=(primary-1)*CELL_SECONDS+offset*CELL_SECONDS/4
                end=(primary-1)*CELL_SECONDS+(offsets[index+1] if index+1<len(offsets) else 4)*CELL_SECONDS/4
                result.append({'id':f'{cell_id}.N{index+1}','instrument':instrument,'midi':midi,
                               'start':start,'end':end,'cell_ids':[cell_id],
                               'source':cell['source'],'comparison_source':cell.get('comparison_source'),
                               'symbol':cell['symbol'],'finger_sign':cell['finger_signs'][index],
                               'legacy_claims':{k:cell[k] for k in ('notation_status','pitch_status','technique_status')},
                               'reading_status':'legacy_melody_candidate_unrechecked',
                               'timing_status':'author_design','performance_verified':False})
    return result


def plan():
    result=_compile_plan()
    validate(result)
    return result


def validate(events,primary_count=5):
    canonical_plan=_compile_plan(primary_count)
    duration=primary_count*CELL_SECONDS
    if not events or len({e['id'] for e in events})!=len(events):
        raise ValueError('empty or duplicate note IDs')
    expected={f'{instrument}.L1.P{primary}' for instrument in INSTRUMENTS for primary in range(1,primary_count+1)}
    observed={cell for event in events for cell in event['cell_ids']}
    if observed!=expected or len(events)!={5:29,8:39}[primary_count]:
        raise ValueError('prefix note/cell coverage changed')
    for event in events:
        if event['instrument'] not in INSTRUMENTS or type(event['midi']) is not int or not 0<=event['midi']<=127:
            raise ValueError('invalid instrument or MIDI')
        if event['performance_verified'] is not False or event['timing_status']!='author_design':
            raise ValueError('candidate cannot be promoted')
        if not event.get('source') and not event.get('reading_evidence'):
            raise ValueError('missing source evidence')
        if not all(type(event[k]) in (int,float) and math.isfinite(event[k]) for k in ('start','end')) or not 0<=event['start']<event['end']<=duration:
            raise ValueError('nonfinite/outside prefix timing')
    canonical={e['id']:e for e in canonical_plan}
    if any(e != canonical.get(e['id']) for e in events):
        raise ValueError('candidate ledger differs from pinned source/design')
    for instrument in INSTRUMENTS:
        selected=[e for e in events if e['instrument']==instrument]
        if not selected: raise ValueError('missing instrument')
        # A melody is monophonic; sho permits chords but not duplicate overlapping pipes.
        groups=({e.get('pipe') for e in selected} if instrument=='sho' else {None})
        for pipe in groups:
            ordered=sorted((e for e in selected if instrument!='sho' or e['pipe']==pipe),key=lambda e:e['start'])
            if any(a['end']>b['start'] for a,b in zip(ordered,ordered[1:])):
                raise ValueError('duplicate/overlapping voice')
        if instrument!='sho':
            ordered=sorted(selected,key=lambda e:e['start'])
            if ordered[0]['start']!=0 or ordered[-1]['end']!=duration or any(a['end']!=b['start'] for a,b in zip(ordered,ordered[1:])):
                raise ValueError('melody has unplanned gap')


def metrics(signal,channels=1):
    data=inspect(signal)
    data.update({'nonfinite_count':sum(not math.isfinite(x) for x in signal),
                 'full_scale_count':sum(abs(x)>=1 for x in signal),
                 'max_channel_sample_step':max(abs(signal[i]-signal[i-channels]) for i in range(channels,len(signal)))})
    if data['peak']>.9 or data['max_channel_sample_step']>.4:
        raise ValueError('author numeric sanity limit exceeded')
    window=FS//10*channels
    rms=[math.sqrt(sum(x*x for x in signal[i:i+window])/window) for i in range(window,len(signal)-window,window)]
    data['minimum_interior_100ms_rms']=min(rms)
    if min(rms)<1e-6: raise ValueError('unexpected silent interior window')
    return data


def render(bank,events,primary_count=5):
    validate(events,primary_count)
    duration=primary_count*CELL_SECONDS
    stems={name:array('f',[0])*round(duration*FS) for name in INSTRUMENTS}
    offset=12*math.log2(430/440)
    for event in events:
        signal=voice(bank,event['instrument'],event['midi']+offset,event['end']-event['start'],.15,.25)
        start=round(event['start']*FS)
        for i,value in enumerate(signal): stems[event['instrument']][start+i]+=value
    mix=array('f')
    # Existing direct mix coefficients. No normalization, reverb, reference recordings or hidden limiter.
    for a,b,c in zip(stems['sho'],stems['ryuteki'],stems['hichiriki']):
        mix.extend((a*.7+b*.85+c*.5,a*.7+b*.5+c*.85))
    report={name:metrics(signal) for name,signal in stems.items()}
    report['ensemble']=metrics(mix,2)
    return stems,mix,report


def generate(directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    bank,bank_metadata=make_bank(out/'bank')
    events=plan();stems,mix,measured=render(bank,events)
    files=[write_wav(out/f'three-pipe-prefix-{name}-15s.wav',1,[stems[name]]) for name in INSTRUMENTS]
    files.append(write_wav(out/'three-pipe-prefix-ensemble-15s.wav',2,[mix]))
    second,_=make_bank(out/'regeneration-bank')
    regen,regen_mix,_=render(second,plan())
    for entry in files:
        name=entry['file'].split('-')[-2]
        signal=regen_mix if name=='ensemble' else regen[name]
        check=write_wav(out/f'.regen-{name}.wav',entry['channels'],[signal])
        if check['sha256']!=entry['sha256']: raise ValueError('independent PCM regeneration differs')
        (out/f'.regen-{name}.wav').unlink()
    for entry in files:
        with wave.open(str(out/entry['file'])) as wav:
            pcm=array('h',wav.readframes(wav.getnframes()))
            if sys.byteorder!='little': pcm.byteswap()
            if (wav.getframerate(),wav.getnframes(),wav.getnchannels(),wav.getsampwidth())!=(FS,720000,entry['channels'],2) or max(map(abs,pcm))>=32767:
                raise ValueError('delivered WAV invalid')
    (out/'three-pipe-prefix-player.html').write_bytes((ROOT/'three-pipe-prefix-player.html').read_bytes())
    save_json(out/'three-pipe-prefix-events-v1.json',events)
    report={'version':'three-pipe-prefix-v1','scope':'first five primary cells of each instrument only; one 15s excerpt',
            'source_commit':subprocess.check_output(['git','-C',str(ROOT.parents[2]),'rev-parse','HEAD'],text=True).strip(),
            'duration_seconds':DURATION,'primary_cells':15,'scheduled_voice_spans':len(events),
            'instrument_voice_spans':{n:sum(e['instrument']==n for e in events) for n in INSTRUMENTS},
            'independent_regeneration_pcm_identical':True,'metrics':measured,'files':files,
            'physical_bank':bank_metadata,'a4_hz':430,'seconds_per_primary_cell':CELL_SECONDS,
            'mix_coefficients':{'left':{'sho':.7,'ryuteki':.85,'hichiriki':.5},'right':{'sho':.7,'ryuteki':.5,'hichiriki':.85}},
            'source_hashes':{str(p.relative_to(ROOT.parents[2])):digest(p) for p in [Path(__file__),ROOT/'score-fixture.json',ROOT/'sho-continuous-v1.json',ROOT/'sho_continuous.py',ROOT/'sho_adoption.py',ROOT/'sho-adoption-v1.json',ROOT/'audio.py',ROOT/'models.py',ROOT.parent/'evaluate.py',ROOT/'three-pipe-prefix-player.html',ROOT.parents[2]/'docs/tasks/three-pipe-prefix-v1/README.md',ROOT.parent/'sho_one_pipe.py']},
            'fully_verified_performance_events':0,'required_complete_performance_events':None,
            'strict_reading_status':'BLOCKED_PUBLIC_EVIDENCE','musical_acceptance':'UNEVALUATED; subjective 80 not reached or tested',
            'unverified':'ryuteki pitch/register/ornaments and hichiriki expression inherited candidates; no new independent score reading',
            'rights':'own physical model bank only; no third-party recording or new measurement'}
    save_json(out/'three-pipe-prefix-inspection-v1.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True,type=Path)
    generate(parser.parse_args().output_dir)
