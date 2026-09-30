"""Deterministic offline bank, real-audio blocks and fail-closed player adapter."""
import argparse
from array import array
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import wave

from features.gagaku.player import Player, BoundaryError
from features.gagaku.sho_one_pipe import render as sho_render
from features.gagaku.evaluate import _fft_magnitude_spectrum, _estimate_f0
from .models import FS, reed, jet

ROOT = Path(__file__).parent
INSTRUMENTS = ('sho', 'ryuteki', 'hichiriki')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def inspect(samples):
    if not samples or not all(math.isfinite(x) for x in samples):
        raise ValueError('empty/nonfinite voice')
    if not any(x != 0 for x in samples):
        raise ValueError('silent voice')
    return {'frames': len(samples), 'peak': max(abs(x) for x in samples),
            'rms': math.sqrt(sum(x*x for x in samples) / len(samples))}


def pcm(samples):
    if not all(math.isfinite(x) and abs(x) < 1 for x in samples):
        raise ValueError('nonfinite/full-scale PCM')
    values = array('h', (round(x * 32767) for x in samples))
    if sys.byteorder != 'little':
        values.byteswap()
    return values.tobytes()


def write_wav(path, channels, chunks):
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((channels, 2, FS, 0, 'NONE', 'not compressed'))
        for chunk in chunks:
            wav.writeframes(pcm(chunk))
    with wave.open(str(path)) as wav:
        return {'file': Path(path).name, 'sha256': digest(path), 'frames': wav.getnframes(),
                'channels': channels, 'sample_rate_hz': FS, 'sample_width_bytes': 2}


def make_bank(directory):
    directory.mkdir(parents=True, exist_ok=True)
    generators = {'sho': lambda: sho_render(seconds=2.0),
                  'ryuteki': lambda: jet(440, 2.0),
                  'hichiriki': lambda: reed(440, 2.0)}
    bank, metadata = {}, {}
    for name, generate in generators.items():
        raw = generate()
        metrics = inspect(raw)
        data = array('d', raw)
        if sys.byteorder != 'little':
            data.byteswap()
        with gzip.GzipFile(filename=str(directory / f'{name}.raw-f64le.gz'), mode='wb', mtime=0) as f:
            f.write(data.tobytes())
        stable = raw[FS:]
        mean = sum(stable) / len(stable)
        stable = [x - mean for x in stable]
        if name == 'ryuteki':
            frequencies, amplitudes = _fft_magnitude_spectrum(stable[-32768:], FS)
            peak = max(range(1, len(amplitudes)-1), key=amplitudes.__getitem__)
            left, center, right = [math.log(max(1e-30, amplitudes[i])) for i in (peak-1, peak, peak+1)]
            offset = 0.5 * (left-right)/(left-2*center+right)
            fundamental = (peak+offset)*FS/65536 if len(frequencies)==32769 else frequencies[peak]+offset*(frequencies[1]-frequencies[0])
        else:
            fundamental = _estimate_f0(stable, FS, 470 if name == 'sho' else 440)
        # Fold 32 periods of our own steady model output into a periodic bank.
        # This is disclosed signal processing, not an instrument measurement.
        period = FS / fundamental
        loop = []
        for phase in range(1024):
            values = []
            for cycle in range(32):
                position = (cycle + phase / 1024) * period
                j = int(position)
                f = position - j
                values.append(stable[j] * (1-f) + stable[j+1] * f)
            loop.append(sum(values) / len(values))
        rms = inspect(loop)['rms']
        gain = {'sho': 0.035, 'ryuteki': 0.11, 'hichiriki': 0.10}[name] / rms
        bank[name] = {'loop': loop, 'reference_hz': fundamental, 'gain': gain}
        metadata[name] = {'raw': f'{name}.raw-f64le.gz', 'raw_sha256': digest(directory/f'{name}.raw-f64le.gz'),
                          'raw_metrics': metrics, 'observed_reference_hz': fundamental,
                          'loop_frames': len(loop), 'gain_per_Pa': gain,
                          'classification': 'timbre_design', 'validation': 'generic physical proxy; not measured instrument identification'}
        metadata[name]['listening_reference'] = write_wav(directory/f'{name}-reference.wav',1,[[x*gain for x in raw]])
    save_json(directory/'bank.json', metadata)
    return bank, metadata


def voice(bank, name, midi, seconds, attack=0.08, release=0.08):
    count = round(seconds * FS)
    item = bank[name]
    signal, gain = item['loop'], item['gain']
    frequency = 440*2**((midi-69)/12)
    # Own-bank linear resampling; no reference recording enters this route.
    step = frequency * len(signal) / FS
    result = array('f')
    for i in range(count):
        position = (i*step) % len(signal)
        j = int(position)
        f = position-j
        value = signal[j]*(1-f)+signal[(j+1)%len(signal)]*f
        a = min(1, i/max(1, round(attack*FS)))
        r = min(1, (count-1-i)/max(1, round(release*FS)))
        envelope = (0.5-0.5*math.cos(math.pi*a))*(0.5-0.5*math.cos(math.pi*r))
        result.append(value * gain * envelope)
    inspect(result)
    return result


def block(bank, fixture, line, variant='first_pass', ending=False):
    seconds = 6 if ending else 10
    stems = {name: array('f', [0.0])*round(seconds*FS) for name in INSTRUMENTS}
    events = []
    if ending:
        groups = {'sho': fixture['ending']['sho'], 'ryuteki': [fixture['ending']['ryuteki']],
                  'hichiriki': [fixture['ending']['hichiriki']]}
        for name, notes in groups.items():
            for midi in notes:
                signal = voice(bank,name,midi,seconds,0.8,2)
                for i,v in enumerate(signal): stems[name][i] += v
                events.append({'instrument':name,'midi':midi,'start':0,'seconds':seconds})
    else:
        pattern = fixture[variant][line]
        for midi in fixture['sho_chords'][pattern]:
            signal = voice(bank,'sho',midi,seconds,0.8,0.8)
            for i,v in enumerate(signal): stems['sho'][i] += v
            events.append({'instrument':'sho','midi':midi,'start':0,'seconds':seconds})
        for name in ('ryuteki','hichiriki'):
            for index,midi in enumerate(fixture['melody'][pattern]):
                midi += 12 if name == 'ryuteki' else 0
                start, duration = index*2.5, 2.5
                signal = voice(bank,name,midi,duration,0.10,0.20)
                for i,v in enumerate(signal): stems[name][round(start*FS)+i] += v
                events.append({'instrument':name,'midi':midi,'start':start,'seconds':duration})
    for signal in stems.values(): inspect(signal)
    # Direct mix, deliberately no reverberation to hide connection defects.
    mix = array('f')
    for a,b,c in zip(stems['sho'],stems['ryuteki'],stems['hichiriki']):
        mix.extend((a*0.7+b*0.85+c*0.5, a*0.7+b*0.5+c*0.85))
    pcm(mix)
    return stems,mix,events


def diagnostic_structure():
    return {'lines':[f'line_{i+1}' for i in range(4)],
            'pass_variants':[{'id':'first_pass','applies_to':'pass_1'}, {'id':'return_pass','applies_to':'pass_2_and_later'}],
            'exit_boundaries':[{'id':'diagnostic_exit','after_line':'line_4','validation_status':'verified'}],
            'tomede':{'content_status':'verified','entry_status':'verified'}}


def plan(request_seconds, *, structure, diagnostic=False):
    if not math.isfinite(request_seconds) or request_seconds < 0:
        raise ValueError('finish request must be finite and nonnegative')
    if not diagnostic:
        raise BoundaryError('Production score, exit and tomede must be verified; diagnostic fixture cannot substitute')
    player = Player(structure)
    player.start()
    timeline=[]
    time=0
    while player.phase in ('program','finish_pending'):
        variant,line = player.current_variant,player.line_index
        if time+10 >= request_seconds and player.phase == 'program': player.request_finish()
        entry={'start_seconds':time,'variant':variant,'line':line,'phase':player.phase,'pass':player.pass_number}
        can_exit = player.phase=='finish_pending' and line==3
        player.complete_line('diagnostic_exit' if can_exit else None)
        time +=10
        entry['end_phase']=player.phase
        timeline.append(entry)
    if player.phase != 'tomede': raise AssertionError('no ending')
    timeline.append({'start_seconds':time,'ending':True,'seconds':6,'phase':'tomede'})
    player.complete_tomede()
    return {'scope':'diagnostic_only','request_seconds':request_seconds, 'end_seconds':time+6,
            'ended_phase':player.phase,'timeline':timeline}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--diagnostic',action='store_true')
    parser.add_argument('--long',action='store_true')
    args=parser.parse_args()
    if not args.diagnostic: parser.error('Production M is unverified. Use --diagnostic for explicit engineering stimuli only.')
    out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    fixture=json.loads((ROOT/'fixture.json').read_text())
    bank,metadata=make_bank(out/'bank')
    blocks={}
    files=[]
    for variant in ('first_pass','return_pass','holdout'):
        for line in range(4):
            key=f'{variant}-{line}'
            stems,mix,events=block(bank,fixture,line,variant)
            blocks[key]=(stems,mix)
            files.append(write_wav(out/f'{key}.wav',2,[mix]))
            save_json(out/f'{key}.events.json',events)
    stems,mix,events=block(bank,fixture,0,ending=True)
    blocks['ending']=(stems,mix)
    files.append(write_wav(out/'ending.wav',2,[mix]));save_json(out/'ending.events.json',events)
    development=[f'first_pass-{i}' for i in range(4)]+['ending']
    holdout=[f'holdout-{i}' for i in range(4)]+['ending']
    for title,sequence in [('development',development),('holdout',holdout)]:
        files.append(write_wav(out/f'{title}.wav',2,(blocks[key][1] for key in sequence)))
        for name in INSTRUMENTS:
            files.append(write_wav(out/f'{title}-{name}.wav',1,(blocks[key][0][name] for key in sequence)))
    randomizer=random.Random(5901)
    requests=[randomizer.uniform(0,1200) for _ in range(1000)]
    logs=[plan(x,structure=diagnostic_structure(),diagnostic=True) for x in requests]
    save_json(out/'finish-requests.json',{'seed':5901,'scope':'symbolic_diagnostic_only','count':1000,'results':logs})
    if args.long:
        for seconds in (300,600,1200):
            control=plan(seconds,structure=diagnostic_structure(),diagnostic=True)
            sequence=['ending' if item.get('ending') else f"{item['variant']}-{item['line']}" for item in control['timeline']]
            files.append(write_wav(out/f'diagnostic-{seconds}s.wav',2,(blocks[key][1] for key in sequence)))
            for name in INSTRUMENTS:
                files.append(write_wav(out/f'diagnostic-{seconds}s-{name}.wav',1,(blocks[key][0][name] for key in sequence)))
            save_json(out/f'diagnostic-{seconds}s.control.json',control)
    source_files=sorted(p for p in Path('features/gagaku').rglob('*') if p.is_file() and p.suffix in ('.py','.json','.md','.html'))
    sources={str(p):digest(p) for p in source_files}
    source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    manifest={'version':'diagnostic-audio-v1','scope':'diagnostic_only','goal':'PRODUCT_GOAL_V1',
              'parameters':json.loads((ROOT/'parameters.json').read_text()),
              'source_commit':source_commit,'source_files':sources,'goal_sha256':digest(ROOT/'PRODUCT_GOAL_V1.md'),
              'fixture_sha256':digest(ROOT/'fixture.json'),'protocol_sha256':digest(ROOT/'protocol.json'),
              'rights_sha256':digest(ROOT/'rights.json'),'bank':metadata,'artifacts':files,
              'research_status':'#52 unchanged; historical FAIL/UNVALIDATED/UNVERIFIED retained',
              'product_acceptance':{'R':'UNVERIFIED','M':'BLOCKED','A':'UNVERIFIED','E':'BLOCKED','P':'PARTIAL','U':'UNEVALUATED'},
              'runtime':sys.version,'dependencies':['Python standard library'],
              'diagnostic_checks':{'finite_and_nonzero_stems':'PASS','pcm_no_full_scale':'PASS','random_requests':1000,
                                   'long_audio':args.long,'product_exit':'UNVERIFIED'}}
    for name in ('player.html','README.md','rights.json'):
        (out/name).write_bytes((ROOT/name).read_bytes())
    save_json(out/'manifest.json',manifest)
    print(json.dumps({'output':str(out),'files':len(files),'scope':'diagnostic_only'},ensure_ascii=False))

if __name__=='__main__': main()
