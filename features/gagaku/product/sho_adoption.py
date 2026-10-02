"""Versioned sho reading overlay: checked glyphs, candidate meanings, explicit gaps."""
import argparse
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from .audio import ROOT, save_json

SPEC = ROOT/'sho-adoption-v1.json'
FROZEN = ROOT/'score-fixture.json'
BASELINE_SHA = 'cc9b7b9422b838a16dac18afef630bcbbcffda90658e7f5dd13cf3202b31238a'
EVIDENCE = 'https://github.com/thattor/gagaku-engine/issues/1#issuecomment-5941780473'
PRIMARY = ['https://dl.ndl.go.jp/api/iiif/1192407/R0000015/full/full/0/default.jpg',
           'https://dl.ndl.go.jp/api/iiif/855853/R0000030/full/full/0/default.jpg']
APPROVED = {'sho.L3.P6':('compound','一/乞',['一','乞'],None),
            'sho.L4.P3':('compound','十/下',['十','下'],None),
            'sho.L2.P6':('hold','引',['一'],'sho.L2.P5'),
            'sho.L2.P8':('hold','引',['一'],'sho.L2.P7'),
            'sho.L4.P6':('hold','引',['乙'],'sho.L4.P5'),
            'sho.L4.P8':('hold','引',['乙'],'sho.L4.P7')}


def load_spec(path=SPEC):
    return validate_spec(json.loads(Path(path).read_text()))


def validate_spec(spec):
    if (spec['version']!='sho-adoption-v1' or spec['performance_verified'] is not False
            or spec['reading_status']!='BLOCKED_PUBLIC_EVIDENCE'
            or spec['listening_acceptance']!='UNEVALUATED'):
        raise ValueError('candidate cannot be promoted to verified/accepted')
    if spec['baseline_sha256']!=BASELINE_SHA or spec['source_record']!='docs/tasks/sho-listening-v1/sources.json':
        raise ValueError('baseline/source version changed')
    midi=spec['pipe_midi']
    if not midi or any(type(v) is not int or not 0<=v<=127 for v in midi.values()):
        raise ValueError('invalid MIDI mapping')
    corrections=spec['corrections']
    ids=[c['cell_id'] for c in corrections]
    required={'sho.L3.P6','sho.L4.P3','sho.L2.P6','sho.L2.P8','sho.L4.P6','sho.L4.P8'}
    if len(ids)!=6 or set(ids)!=required:
        raise ValueError('correction scope changed or duplicated')
    for correction in corrections:
        if correction['glyph_status']!='image_checked' or correction['realization_status']!='modern_hypothesis':
            raise ValueError('glyph check is not performance verification')
        if not correction.get('primary_sources') or not correction.get('evidence'):
            raise ValueError('missing evidence')
        approved=APPROVED[correction['cell_id']]
        if (correction['kind'],correction['read_symbol'],correction['chord_path'],correction.get('predecessor_id'))!=approved:
            raise ValueError('v1 interpretation changed; requires explicit new version')
        if correction['primary_sources']!=PRIMARY or correction['evidence']!=EVIDENCE:
            raise ValueError('v1 evidence changed')
        path=correction['chord_path']
        fractions=correction['nominal_fractions']
        if len(path)!=len(fractions) or any(ch not in spec['chords'] for ch in path):
            raise ValueError('unknown chord or duration')
        try:
            weights=[Fraction(*f) for f in fractions]
        except (TypeError,ZeroDivisionError) as exc:
            raise ValueError('invalid fraction') from exc
        if sum(weights)!=1 or any(f<=0 for f in weights):
            raise ValueError('invalid nominal division')
        if correction['kind']=='compound':
            if (correction.get('operation_evidence')!='https://www.chatorishimizu.com/composingforsho'
                    or correction.get('duration_evidence')!='https://mtosmt.org/issues/mto.20.26.4/mto.20.26.4.momii.html'
                    or correction.get('duration_location')!='§8 note32'):
                raise ValueError('modern operation/duration evidence changed')
            if len(path)!=2 or weights!=[Fraction(1,2)]*2:
                raise ValueError('compound must preserve two nominally equal chords')
        elif correction['kind']=='hold':
            if len(path)!=1 or not correction.get('predecessor_id'):
                raise ValueError('hold must identify preceding chord')
        else:
            raise ValueError('unsupported correction')
    for pipes in spec['chords'].values():
        if len(pipes)!=len(set(pipes)) or not pipes or any(p not in spec['pipe_midi'] for p in pipes):
            raise ValueError('unknown or duplicate pipe')
    conflict=spec['edition_conflicts']['工']
    if conflict['decision']!='unselected; require explicit adoption before synthesis':
        raise ValueError('edition choice requires a new explicit adoption version')
    frozen=json.loads(FROZEN.read_text())
    baseline_cells=[c for c in frozen['cells'] if c['id'].startswith('sho.')]
    legacy_pitch={p:m for c in baseline_cells for p,m in zip(c.get('pipes') or [],c.get('midi') or [])}
    if midi!=legacy_pitch:
        raise ValueError('pitch mapping changed; requires explicit new version')
    legacy_chords={c['symbol']:c['pipes'] for c in baseline_cells if c.get('pipes')}
    expected={k:legacy_chords['九' if k=='乞' else k] for k in ('一','乞','十','下','乙')}
    if set(spec['chords'])!=set(expected) or any(set(spec['chords'][k])!=set(v) for k,v in expected.items()):
        raise ValueError('adopted chord pipes changed; requires explicit review')
    old_ku=set(legacy_chords['工'])
    if set(conflict['1894'])!=old_ku or set(conflict['1932'])!=(old_ku-{'乙'}|{'下'}):
        raise ValueError('edition alternatives changed')
    if conflict['sources']!=['https://dl.ndl.go.jp/api/iiif/1192407/R0000007/full/full/0/default.jpg',
                             'https://dl.ndl.go.jp/api/iiif/855853/R0000011/full/full/0/default.jpg']:
        raise ValueError('edition evidence changed')
    return spec


def build_body(spec=None, frozen=FROZEN):
    spec=load_spec() if spec is None else copy.deepcopy(spec)
    validate_spec(spec)
    raw=Path(frozen).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=spec['baseline_sha256']:
        raise ValueError('frozen baseline changed; rebase requires explicit review')
    legacy=json.loads(raw)
    cells={c['id']:c for c in legacy['cells'] if c['id'].startswith('sho.')}
    ordered=[f'sho.L{line}.P{point}' for line in range(1,5) for point in range(1,9)]
    if set(cells)!=set(ordered):
        raise ValueError('missing or extra body cell')
    corrections={c['cell_id']:c for c in spec['corrections']}
    output=[]
    for identifier in ordered:
        old=cells[identifier]
        row={'cell_id':identifier,'source':copy.deepcopy(old['source']),
             'legacy_symbol':old['symbol'],'legacy_claims':{k:old[k] for k in ('notation_status','pitch_status','technique_status')},
             'performance_verified':False,'timing_status':'not_scheduled',
             'candidate_status':'inherited_legacy_not_rechecked','chord_path':None,
             'legacy_pipes':old.get('pipes'),'legacy_midi':old.get('midi')}
        if identifier in corrections:
            correction=corrections[identifier]
            if old['symbol']!=correction['old_symbol']:
                raise ValueError('correction no longer matches baseline')
            if correction['kind']=='hold':
                previous=correction['predecessor_id']
                if ordered.index(previous)!=ordered.index(identifier)-1 or cells[previous]['symbol']!=correction['chord_path'][0]:
                    raise ValueError('hold does not match immediately preceding chord')
            row.update({'read_symbol':correction['read_symbol'],'candidate_status':'adopted_modern_hypothesis',
                        'chord_path':copy.deepcopy(correction['chord_path']),
                        'nominal_fractions':correction['nominal_fractions'],
                        'correction':copy.deepcopy(correction)})
        elif old['symbol']=='工':
            row.update({'read_symbol':'工','candidate_status':'edition_selection_required',
                        'edition_conflict':copy.deepcopy(spec['edition_conflicts']['工'])})
        output.append(row)
    return {'version':spec['version'],'scope':spec['scope'],'cells':output,
            'counts':{'body_primary_cells':32,'corrected_glyph_cells':6,
                      'compound_chord_checkpoints':sum(len(c['chord_path']) for c in corrections.values() if c['kind']=='compound'),
                      'hold_cells':sum(c['kind']=='hold' for c in corrections.values()),
                      'unselected_edition_cells':sum(c['candidate_status']=='edition_selection_required' for c in output),
                      'inherited_unrechecked_cells':sum(c['candidate_status']=='inherited_legacy_not_rechecked' for c in output),
                      'complete_performance_events_verified':0,'complete_performance_events_required':None},
            'performance_verified':False,'full_body_synthesis_ready':False,
            'reading_status':spec['reading_status'],'listening_acceptance':spec['listening_acceptance'],
            'baseline_sha256':spec['baseline_sha256']}


def export(directory):
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    spec=load_spec(); body=build_body(spec)
    save_json(directory/'sho-body-adoption.json',body)
    save_json(directory/'inspection.json',{
        'scope':'data consistency only; no new audio or musical acceptance',
        'source_commit':__import__('subprocess').check_output(['git','-C',str(ROOT.parents[2]),'rev-parse','HEAD'],text=True).strip(),
        'counts':body['counts'],
        'source_hashes':{str(p.relative_to(ROOT.parents[2])):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [SPEC,FROZEN,Path(__file__),ROOT.parents[2]/spec['source_record']]},
        'output_sha256':hashlib.sha256((directory/'sho-body-adoption.json').read_bytes()).hexdigest(),
        'full_body_synthesis_ready':False,'strict_reading_status':'BLOCKED_PUBLIC_EVIDENCE',
        'listening_acceptance':'UNEVALUATED'})
    print(json.dumps(body['counts']))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True,type=Path)
    export(parser.parse_args().output_dir)
