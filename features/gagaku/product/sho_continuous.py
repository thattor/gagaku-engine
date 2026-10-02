"""Continuous sho candidate with edition alternatives and disclosed controls."""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import subprocess
import wave

from .audio import ROOT, digest, inspect, save_json, voice, write_wav
from .models import FS
from .sho_adoption import build_body, load_spec
from .sho_listening import make_sho_bank

CONTROL=ROOT/'sho-continuous-v1.json'
DURATION=48.0
EXTRA_SOURCES=[{'url': 'https://dl.ndl.go.jp/api/iiif/1192407/R0000014/full/full/0/default.jpg', 'sha256': '0834112950911f3a96f943050982d517821f0dd58e535f8bebb86b0feaaa5144', 'location': 'c14 left p17, leftmost score column second primary point after 十'}, {'url': 'https://dl.ndl.go.jp/api/iiif/855853/R0000030/full/full/0/default.jpg', 'sha256': '7f599455c4b552dcc2f48097f54a86ddad9eed76a4a9294f0a8f76fe69b0f1fb', 'location': 'c30 right p21, first music column after title, second primary point after 十'}]


def load_control():
    return validate_control(json.loads(CONTROL.read_text()))


def validate_control(control):
    if (control['version']!='sho-continuous-v1' or control['adoption_version']!='sho-adoption-v1'
            or control['performance_verified'] is not False or control['listening_acceptance']!='UNEVALUATED'):
        raise ValueError('wrong candidate version or promoted acceptance')
    expected={'seconds_per_primary_cell':1.5,'attack_seconds':.15,'release_seconds':.25,
              'early_release_seconds':.10,'kigae_add_delay_seconds':.10}
    if any(type(control[k]) not in (float,int) or control[k]!=v for k,v in expected.items()):
        raise ValueError('v1 author controls changed')
    extra=control['extra_reading']
    if (extra['cell_id'],extra['legacy_symbol'],extra['read_symbol'],extra['adopted_chord'],extra['predecessor_id'])!=('sho.L1.P2','行','引','十','sho.L1.P1'):
        raise ValueError('extra interpretation changed')
    if (control['ko_variants']!=['1932','1894'] or control['scope']!='sho.L1.P1..sho.L4.P8 once, no repeat or tomede'
            or control['source_operation_pairs']!=['一→乞','十→下']):
        raise ValueError('scope, edition variants or adopted operation pairs changed')
    if extra['sources']!=EXTRA_SOURCES:
        raise ValueError('extra reading source registry changed')
    if any(len(entry.get('sha256',''))!=64 or not entry.get('location') for entry in extra['sources']):
        raise ValueError('missing image hash or location')
    if extra['glyph_status']!='image_checked' or extra['meaning_status']!='continuation_hypothesis':
        raise ValueError('missing evidence or inappropriate verification')
    return control


def reading_evidence(row,control):
    if row['cell_id']==control['extra_reading']['cell_id']:
        return control['extra_reading']
    if row['candidate_status']=='adopted_modern_hypothesis':
        return row['correction']
    if row['candidate_status']=='edition_selection_required':
        return row['edition_conflict']
    return {'kind':'legacy_unrechecked','fixture':'features/gagaku/product/score-fixture.json',
            'baseline_sha256':load_spec()['baseline_sha256']}


def checkpoints(edition):
    control=load_control(); spec=load_spec(); body=build_body(spec)
    if edition not in control['ko_variants'] or edition not in ('1932','1894'):
        raise ValueError('must explicitly choose a ko edition alternative')
    output=[]
    for i,row in enumerate(body['cells']):
        start=i*control['seconds_per_primary_cell']
        cell=row['cell_id']; status=row['candidate_status']
        if cell==control['extra_reading']['cell_id']:
            path=['十']; fractions=[[1,1]]; status='extra_continuation_hypothesis'
        elif row['chord_path']:
            path=row['chord_path']; fractions=row['nominal_fractions']
        else:
            path=[row['legacy_symbol']]; fractions=[[1,1]]
        time=start
        for part,(symbol,(num,den)) in enumerate(zip(path,fractions)):
            if symbol=='工':
                pipes=spec['edition_conflicts']['工'][edition]
                status='edition_alternative_unverified'
            elif status=='inherited_legacy_not_rechecked':
                pipes=row['legacy_pipes']
            else:
                pipes=spec['chords'][symbol]
            if not pipes or len(set(pipes))!=len(pipes) or any(p not in spec['pipe_midi'] for p in pipes):
                raise ValueError('missing or invalid pipes')
            seconds=control['seconds_per_primary_cell']*num/den
            output.append({'id':f'{cell}.C{part+1}','cell_id':cell,'part':part+1,
                           'start':time,'end':time+seconds,'symbol':symbol,'pipes':list(pipes),
                           'reading_status':status,'source':row['source'],
                           'reading_evidence':reading_evidence(row,control),
                           'performance_verified':False,'timing_status':'author_design',
                           'ko_edition':edition if symbol=='工' else None})
            time+=seconds
    validate_checkpoints(output)
    return output


def validate_checkpoints(points):
    required={f'sho.L{line}.P{point}' for line in range(1,5) for point in range(1,9)}
    if len(points)!=34 or len({p['id'] for p in points})!=34 or {p['cell_id'] for p in points}!=required:
        raise ValueError('missing/duplicate checkpoints')
    expected_ids=[f'sho.L{line}.P{primary}.C{part}' for line in range(1,5) for primary in range(1,9)
                  for part in (range(1,3) if (line,primary) in ((3,6),(4,3)) else range(1,2))]
    if [p['id'] for p in points]!=expected_ids:
        raise ValueError('wrong primary order or compound partition')
    spec=load_spec(); pitch=spec['pipe_midi']; settings=load_control()
    rows={r['cell_id']:r for r in build_body(spec)['cells']}
    previous=0
    for point in points:
        row=rows[point['cell_id']]
        status=('extra_continuation_hypothesis' if point['cell_id']=='sho.L1.P2' else
                'edition_alternative_unverified' if point['cell_id']=='sho.L2.P3' else row['candidate_status'])
        part=point['part']
        if type(part) is not int or point['id']!=f"{point['cell_id']}.C{part}":
            raise ValueError('checkpoint identity/part mismatch')
        path=(['十'] if point['cell_id']=='sho.L1.P2' else row['chord_path'] or [row['legacy_symbol']])
        if not 1<=part<=len(path) or point['symbol']!=path[part-1]:
            raise ValueError('checkpoint symbol/path mismatch')
        index=list(rows).index(point['cell_id'])
        seconds=settings['seconds_per_primary_cell']/len(path)
        if point['start']!=index*settings['seconds_per_primary_cell']+(part-1)*seconds or point['end']!=point['start']+seconds:
            raise ValueError('checkpoint nominal timing mismatch')
        expected_pipes=(spec['chords'][point['symbol']] if status in ('extra_continuation_hypothesis','adopted_modern_hypothesis') else row['legacy_pipes'])
        if point['cell_id']!='sho.L2.P3' and set(point['pipes'])!=set(expected_pipes):
            raise ValueError('checkpoint pipe set mismatch')
        if point['reading_status']!=status or point.get('source')!=row['source'] or point.get('reading_evidence')!=reading_evidence(row,settings):
            raise ValueError('reading status or provenance changed')
        if point['cell_id']=='sho.L2.P3':
            if point['ko_edition'] not in ('1932','1894') or set(point['pipes'])!=set(row['edition_conflict'][point['ko_edition']]):
                raise ValueError('edition alternative mismatch')
        elif point['ko_edition'] is not None:
            raise ValueError('edition marker outside 工')
        if not point['pipes'] or len(point['pipes'])!=len(set(point['pipes'])) or any(p not in pitch for p in point['pipes']):
            raise ValueError('invalid checkpoint pipes')
        if point['performance_verified'] is not False or point['timing_status']!='author_design' or not point.get('source'):
            raise ValueError('missing provenance or verification promotion')
        if not all(math.isfinite(point[k]) for k in ('start','end')) or point['start']!=previous or point['end']<=previous:
            raise ValueError('gap, overlap or nonfinite checkpoint')
        previous=point['end']
    if previous!=DURATION:
        raise ValueError('wrong duration')


def controls(points):
    validate_checkpoints(points)
    settings=load_control()
    changes=[{'time':0,'remove':[],'add':points[0]['pipes'],
              'checkpoint_ids':[points[0]['id']],'kind':'author_start','performance_verified':False}]
    for a,b in zip(points,points[1:]):
        old,new=set(a['pipes']),set(b['pipes']); t=b['start']
        context=[a['id'],b['id']]
        if a['cell_id']==b['cell_id'] and (a['symbol'],b['symbol'])==('一','乞'):
            steps=[(t-settings['early_release_seconds'],['凢'],[]),
                   (t,['一'],['乞']),(t+settings['kigae_add_delay_seconds'],[],['八'])]
            kind='modern_ichi_kotsu_sequence_with_author_seconds'
        elif a['cell_id']==b['cell_id'] and (a['symbol'],b['symbol'])==('十','下'):
            steps=[(t-settings['early_release_seconds'],['八'],[]),
                   (t,['十'],['千','美'])]
            kind='modern_ju_ge_sequence_with_author_seconds'
        else:
            steps=[(t,sorted(old-new),sorted(new-old))]
            kind='author_set_difference_shared_pipes_held'
        for time,remove,add in steps:
            changes.append({'time':time,'remove':remove,'add':add,'checkpoint_ids':context,
                            'kind':kind,'performance_verified':False})
    changes.append({'time':DURATION,'remove':points[-1]['pipes'],'add':[],
                    'checkpoint_ids':[points[-1]['id']],'kind':'author_excerpt_cutoff_not_tomede','performance_verified':False})
    return changes


def spans(points,changes):
    open_pipes={}; result=[]; last=-1
    for change in changes:
        time=change['time']
        if not math.isfinite(time) or not 0<=time<=DURATION or time<last or change['performance_verified'] is not False:
            raise ValueError('invalid control timing or status')
        last=time
        for pipe in change['remove']:
            if pipe not in open_pipes: raise ValueError('remove inactive pipe')
            start=open_pipes.pop(pipe)
            if time<=start: raise ValueError('nonpositive pipe duration')
            result.append({'pipe':pipe,'start':start,'end':time,'performance_verified':False,
                           'timing_status':'author_design'})
        for pipe in change['add']:
            if pipe in open_pipes: raise ValueError('duplicate active pipe')
            open_pipes[pipe]=time
    if open_pipes: raise ValueError('unclosed pipe')
    for event in result:
        event['checkpoint_ids']=[p['id'] for p in points if p['start']<event['end'] and p['end']>event['start'] and event['pipe'] in p['pipes']]
        if not event['checkpoint_ids']: raise ValueError('untraced note')
    # Inspect settled middle of every nominal checkpoint, beyond 100ms design shift.
    for point in points:
        middle=(point['start']+point['end'])/2
        sounding={e['pipe'] for e in result if e['start']<=middle<e['end']}
        if sounding!=set(point['pipes']): raise ValueError('missing or extra settled pipe')
    validate_spans(result)
    return sorted(result,key=lambda e:(e['start'],e['pipe']))


def validate_spans(events):
    pitch=load_spec()['pipe_midi']
    for event in events:
        if (event['performance_verified'] is not False or event['timing_status']!='author_design'
                or event['pipe'] not in pitch or not event.get('checkpoint_ids')):
            raise ValueError('invalid pipe/status/provenance')
        if not all(type(event[k]) in (float,int) and math.isfinite(event[k]) for k in ('start','end')) or not 0<=event['start']<event['end']<=DURATION:
            raise ValueError('invalid note timing')
    for pipe in pitch:
        ordered=sorted((e for e in events if e['pipe']==pipe),key=lambda e:e['start'])
        if any(a['end']>b['start'] for a,b in zip(ordered,ordered[1:])):
            raise ValueError('duplicate overlapping pipe span')


def render(bank,events):
    validate_spans(events)
    settings=load_control(); spec=load_spec()
    signal=array('f',[0])*round(DURATION*FS)
    offset=12*math.log2(430/440)
    for event in events:
        if event['performance_verified'] is not False or event['pipe'] not in spec['pipe_midi']:
            raise ValueError('invalid pipe/verification')
        start,end=event['start'],event['end']
        if not all(math.isfinite(x) for x in (start,end)) or not 0<=start<end<=DURATION:
            raise ValueError('invalid voice timing')
        note=voice(bank,'sho',spec['pipe_midi'][event['pipe']]+offset,end-start,
                   settings['attack_seconds'],settings['release_seconds'])
        at=round(start*FS)
        for i,value in enumerate(note): signal[at+i]+=value
    metrics=inspect(signal)
    metrics.update({'dc_mean':sum(signal)/len(signal),
                    'max_sample_step':max(abs(b-a) for a,b in zip(signal,signal[1:])),
                    'nonfinite_count':sum(not math.isfinite(x) for x in signal),
                    'full_scale_count':sum(abs(x)>=1 for x in signal)})
    if metrics['peak']>.6 or abs(metrics['dc_mean'])>.005 or metrics['max_sample_step']>.2:
        raise ValueError('author numeric sanity bound exceeded; not auditory acceptance')
    # No silent windows in this chosen sustained-body preview; intentional edge fades excluded.
    window=FS//10
    windows=[math.sqrt(sum(x*x for x in signal[i:i+window])/window) for i in range(window,len(signal)-window,window)]
    metrics['minimum_interior_100ms_rms']=min(windows)
    if metrics['minimum_interior_100ms_rms']<1e-5:
        raise ValueError('unexpected silent window')
    return signal,metrics


def generate(directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    bank=make_sho_bank(); signals={}; files=[]; reports={}
    for edition in ('1932','1894'):
        points=checkpoints(edition); changes=controls(points); events=spans(points,changes)
        signal,metrics=render(bank,events);signals[edition]=signal
        files.append(write_wav(out/f'sho-continuous-ko-{edition}-48s.wav',1,[signal]))
        reports[edition]={'checkpoint_count':len(points),'primary_cell_count':32,'pipe_span_count':len(events),'metrics':metrics}
        save_json(out/f'ko-{edition}.events.json',{'checkpoints':points,'controls':changes,'pipe_spans':events})
    # Independently regenerate the physical model and both resulting PCM files.
    second=make_sho_bank()
    for edition in signals:
        points=checkpoints(edition); regen,_=render(second,spans(points,controls(points)))
        check=write_wav(out/f'.regen-{edition}.wav',1,[regen])
        expected=next(f['sha256'] for f in files if f['file']==f'sho-continuous-ko-{edition}-48s.wav')
        if check['sha256']!=expected: raise ValueError('independent PCM regeneration differs')
        (out/f'.regen-{edition}.wav').unlink()
    difference=math.sqrt(sum((a-b)**2 for a,b in zip(signals['1932'],signals['1894']))/(DURATION*FS))
    if difference<=0: raise ValueError('edition alternatives should differ')
    for f in files:
        with wave.open(str(out/f['file'])) as wav:
            pcm=array('h',wav.readframes(wav.getnframes()))
            if __import__('sys').byteorder!='little': pcm.byteswap()
            if wav.getnframes()!=2304000 or wav.getnchannels()!=1 or wav.getsampwidth()!=2 or max(map(abs,pcm))>=32767:
                raise ValueError('invalid delivered PCM')
    report={'version':'sho-continuous-v1','scope':'32 primary cells once; no repeats, other instruments or tomede',
            'duration_seconds':DURATION,'source_commit':subprocess.check_output(['git','-C',str(ROOT.parents[2]),'rev-parse','HEAD'],text=True).strip(),
            'files':files,'variants':reports,'difference_rms':difference,'independent_regeneration_pcm_identical':True,
            'inputs_sha256':{str(p.relative_to(ROOT.parents[2])):digest(p) for p in [CONTROL,ROOT/'sho-adoption-v1.json',ROOT/'score-fixture.json',Path(__file__),ROOT/'sho_adoption.py',ROOT/'sho_listening.py',ROOT/'audio.py',ROOT.parent/'sho_one_pipe.py',ROOT.parents[2]/'docs/tasks/sho-listening-v1/sources.json',ROOT/'sho-continuous-player.html',ROOT.parents[2]/'docs/tasks/sho-continuous-v1/README.md']},
            'source_ledger_counts':{'adoption_v1_corrected':6,'extra_glyph_checked_continuation_hypothesis':1,'legacy_unrechecked':24,'ko_edition_alternative_unverified':1},
            'fully_verified_performance_events':0,'required_complete_performance_events':None,
            'strict_reading_status':'BLOCKED_PUBLIC_EVIDENCE','listening_acceptance':'UNEVALUATED; 80 target not evaluated or achieved',
            'rights':'own physical model bank only; no third-party recording or new measurement',
            'sanity_limits':{'peak':.6,'absolute_dc_mean':.005,'max_sample_step':.2,'minimum_interior_100ms_rms':1e-5,'classification':'author numeric checks, not musical acceptance'}}
    (out/'player.html').write_bytes((ROOT/'sho-continuous-player.html').read_bytes())
    report['player']={'file':'player.html','sha256':digest(out/'player.html')}
    save_json(out/'sho-continuous-inspection-v1.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True,type=Path)
    generate(parser.parse_args().output_dir)
