"""Correct the ryuteki source-column adoption; preserve frozen sho and hichiriki."""
import argparse
from array import array
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import wave

from .audio import ROOT, digest, make_bank, save_json, voice, write_wav
from .models import FS
from . import three_pipe_body as body
from .three_pipe_prefix import INSTRUMENTS, metrics

SPEC = ROOT / 'ryuteki-source-adoption-v1.json'
BASE_COMMIT = '85915cdb056c554db5b8688f785335f47d9212e3'
IMAGE_URL = 'https://dl.ndl.go.jp/api/iiif/1194354/R0000015/full/full/0/default.jpg'
IMAGE_SHA256 = '1c1e63c6f4fe314d93c9e24f6bd51c3c94d45d790638e22a16cb122e280a6f6b'
COLUMNS = {1: [.84, .895], 2: [.765, .83], 3: [.69, .755], 4: [.62, .68]}
ROWS = [.13, .23, .323, .419, .51, .61, .706, .801, .895]
LAST_CELLS = [('タア', ['テ']), ('ロホ', ['六', 'く']), ('チイイヤ', ['五', '上', '五']),
              ('タア', ['テ']), ('ハア', ['く']), ('タア', ['テ']),
              ('引様+ア', ['continuation']), ('引様二記号+二返', ['continuation'])]
SOURCE_PARTITION = {'source_id': '1194354', 'canvas': 15, 'page': 18, 'image_url': 'https://dl.ndl.go.jp/api/iiif/1194354/R0000015/full/full/0/default.jpg', 'image_sha256': '1c1e63c6f4fe314d93c9e24f6bd51c3c94d45d790638e22a16cb122e280a6f6b', 'finding': 'legacy ryuteki L1 on canvas14 is the preceding piece final column; all four adopted target body columns are on canvas15', 'removed_legacy_cells': ['ryuteki.L1.P1', 'ryuteki.L1.P2', 'ryuteki.L1.P3', 'ryuteki.L1.P4', 'ryuteki.L1.P5', 'ryuteki.L1.P6', 'ryuteki.L1.P7', 'ryuteki.L1.P8'], 'remapping': 'legacy L2→actual L1, L3→actual L2, L4→actual L3; actual L4 added', 'verification_scope': 'independent visual source-partition review; glyph readings, pitch, timing and realization remain candidates'}
DEPENDENCIES = (
    'three_pipe_body.py', 'three-pipe-body-v1.json', 'three_pipe_prefix.py',
    'sho_continuous.py', 'sho-adoption-v1.json', 'sho-continuous-v1.json',
    'score-fixture.json', 'audio.py', 'models.py', 'sho_adoption.py', 'score-sources.json')


def adopted_cells():
    old = json.loads(body.SPEC.read_text())
    result = []
    for line in range(1, 5):
        for point in range(1, 9):
            ident = f'ryuteki.L{line}.P{point}'
            if line < 4:
                original = next(c for c in old['cells'] if c['id'] == f'ryuteki.L{line + 1}.P{point}')
                cell = copy.deepcopy(original)
                cell['legacy_cell_id'] = original['id']
                cell['legacy_source'] = original['source']
                if line == point == 1:
                    cell['legacy_chant_candidate'] = cell['chant_candidate']
                    cell['chant_candidate'] = 'チラハ'
                    cell['initial_only_annotation'] = {'chant_candidate': 'トロホ',
                        'execution': 'not separately executed; ornament/timing unconfirmed'}
            else:
                chant, fingers = LAST_CELLS[point - 1]
                cell = {'instrument': 'ryuteki', 'chant_candidate': chant,
                        'finger_candidates': fingers, 'legacy_cell_id': None,
                        'glyph_status': 'image_transcription_candidate', 'performance_verified': False}
            x0, x1 = COLUMNS[line]
            cell.update(id=ident, line=line, primary=point,
                        source={'id': '1194354', 'canvas': 15, 'page': 18,
                                'url': IMAGE_URL, 'sha256': IMAGE_SHA256,
                                'column': f'right-page body column {line}', 'row': point,
                                'bbox_normalized': [x0, ROWS[point - 1], x1, ROWS[point]],
                                'bbox_note': 'Approximate manual full-canvas region, normalized top-left origin'},
                        reading_status='source_partition_corrected_candidate')
            result.append(cell)
    return result


def policy():
    spec = json.loads(SPEC.read_text())
    required = {f'features/gagaku/product/{p}' for p in DEPENDENCIES} | {
        'features/gagaku/evaluate.py', 'features/gagaku/sho_one_pipe.py', 'docs/PRODUCT_GOAL_V1.md'}
    old = json.loads(body.SPEC.read_text())
    if (spec.get('version') != 'ryuteki-source-adoption-v1' or spec.get('dependency_commit') != BASE_COMMIT or
            spec.get('duration_seconds') != 96 or spec.get('seconds_per_primary_cell') != 3 or
            spec.get('a4_hz') != 430 or spec.get('attack_seconds') != .15 or spec.get('release_seconds') != .25 or
            spec.get('midi_adoption') != old['midi_adoption']['ryuteki'] or
            spec.get('special_adoption') != old['special_adoption'] or
            spec.get('cells') != adopted_cells() or spec.get('source_partition') != SOURCE_PARTITION or
            set(spec.get('dependency_hashes', {})) != required or
            spec.get('verified_exit') is not False or spec.get('tomede') is not False or
            spec.get('traditional_nihen_verified') is not False or
            spec.get('fully_verified_performance_events') != 0 or
            spec.get('strict_reading_status') != 'BLOCKED_PUBLIC_EVIDENCE' or
            spec.get('musical_acceptance') != 'UNEVALUATED'):
        raise ValueError('changed or promoted source adoption policy')
    for name, expected in spec['dependency_hashes'].items():
        if digest(ROOT.parents[2] / name) != expected:
            raise ValueError(f'pinned source-adoption dependency changed: {name}')
    return spec


def _compile():
    spec = policy()
    old = body.plan()
    result = [copy.deepcopy(e) for e in old if e['instrument'] != 'ryuteki']
    previous = None
    for cell in spec['cells']:
        start = ((cell['line'] - 1) * 8 + cell['primary'] - 1) * 3
        fingers = cell['finger_candidates']
        for index, sign in enumerate(fingers):
            midi = spec['midi_adoption'].get(sign)
            if midi is None:
                if sign not in spec['special_adoption'] or previous is None:
                    raise ValueError('unknown or unseeded retained pitch')
                midi = previous
            legacy_id = f"{cell['legacy_cell_id']}.N{index + 1}" if cell['legacy_cell_id'] else None
            if legacy_id:
                event = copy.deepcopy(next(e for e in old if e['id'] == legacy_id))
                event.update(start=event['start'] - 24, end=event['end'] - 24)
                if event['midi'] != midi:
                    raise ValueError('remapped pitch differs from frozen adoption')
            else:
                event = {'instrument': 'ryuteki', 'midi': midi,
                         'start': start + 3 * index / len(fingers),
                         'end': start + 3 * (index + 1) / len(fingers),
                         'finger_candidate': sign, 'glyph_status': cell['glyph_status'],
                         'timing_status': 'author_design', 'performance_verified': False,
                         'special_adoption': spec['special_adoption'].get(sign)}
            event.update(id=f"{cell['id']}.N{index + 1}", cell_ids=[cell['id']],
                         source=cell['source'], chant_candidate=cell['chant_candidate'],
                         reading_status='explicit_source_partition_adoption_hypothesis',
                         legacy_event_id=legacy_id)
            if 'initial_only_annotation' in cell:
                event['initial_only_annotation'] = cell['initial_only_annotation']
            result.append(event)
            previous = midi
    return result


def validate(events):
    canonical = _compile()
    if not isinstance(events, list) or events != canonical:
        raise ValueError('events differ from canonical source adoption')
    if len({e['id'] for e in events}) != len(events):
        raise ValueError('duplicate source adoption event')
    for instrument in INSTRUMENTS:
        actual = {c for e in events if e['instrument'] == instrument for c in e['cell_ids']}
        expected = {f'{instrument}.L{line}.P{point}' for line in range(1, 5) for point in range(1, 9)}
        if actual != expected:
            raise ValueError('missing source-adoption cell coverage')
    for e in events:
        if (e['performance_verified'] is not False or e['timing_status'] != 'author_design' or
                type(e['midi']) is not int or not 0 <= e['midi'] <= 127 or
                not all(math.isfinite(e[k]) for k in ('start', 'end')) or not 0 <= e['start'] < e['end'] <= 96):
            raise ValueError('invalid or promoted source-adoption event')


def plan():
    events = _compile()
    validate(events)
    return events


def render(bank, events):
    validate(events)
    stems = {n: array('f', [0]) * (96 * FS) for n in INSTRUMENTS}
    for span in body.sounding_spans(events):
        start, end = round(span['start'] * FS), round(span['end'] * FS)
        sound = voice(bank, span['instrument'], span['midi'] + 12 * math.log2(430 / 440),
                      (end - start) / FS, .15, .25)
        if len(sound) != end - start:
            raise ValueError('voice length differs from source-adoption span')
        for i, value in enumerate(sound):
            stems[span['instrument']][start + i] += value
    mix = array('f')
    for sho, ryuteki, hichiriki in zip(stems['sho'], stems['ryuteki'], stems['hichiriki']):
        mix.extend((sho * .7 + ryuteki * .85 + hichiriki * .5,
                    sho * .7 + ryuteki * .5 + hichiriki * .85))
    return {**stems, 'ensemble': mix}


def float_hash(signal):
    data = array('f', signal)
    if sys.byteorder != 'little':
        data.byteswap()
    return hashlib.sha256(data.tobytes()).hexdigest()


def inspect_pcm(path, duration, channels, require_terminal_zero=True):
    with wave.open(str(path)) as wav:
        if (wav.getnframes(), wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (
                duration * FS, FS, channels, 2):
            raise ValueError('unexpected delivered PCM framing')
        values = array('h', wav.readframes(wav.getnframes()))
        if sys.byteorder != 'little':
            values.byteswap()
    peak = max(map(abs, values))
    if peak >= 32767 or (require_terminal_zero and any(values[-channels:])):
        raise ValueError('full scale or nonzero final PCM frame')
    return {'peak_pcm': peak, 'final_frame_zero': not any(values[-channels:]),
            'terminal_zero_required': require_terminal_zero, 'frames': duration * FS}


def generate(directory):
    spec = policy()
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    events = plan()
    bank, bank_meta = make_bank(out / 'bank')
    signals = render(bank, events)
    baseline, _ = body.render(bank, body.plan())
    for name in ('sho', 'hichiriki'):
        if signals[name] != baseline[name]:
            raise ValueError('frozen non-ryuteki stem changed')
    if signals['ryuteki'] == baseline['ryuteki'] or signals['ensemble'] == baseline['ensemble']:
        raise ValueError('source correction did not affect ryuteki and mix')
    measured, files, hashes, pcm_checks, baseline_checks = {}, [], {}, {}, {}
    for name, signal in signals.items():
        measured[name] = metrics(signal, 2 if name == 'ensemble' else 1)
        hashes[name] = float_hash(signal)
        channels = 2 if name == 'ensemble' else 1
        entry = write_wav(out / f'ryuteki-source-adoption-{name}-96s.wav', channels, [signal])
        entry.update(instrument=name, duration_seconds=96)
        files.append(entry)
        pcm_checks[name] = inspect_pcm(out / entry['file'], 96, channels)
        if name in ('sho', 'hichiriki'):
            temporary = out / f'.baseline-{name}.wav'
            check = write_wav(temporary, 1, [baseline[name]])
            if check['sha256'] != entry['sha256']:
                raise ValueError('frozen non-ryuteki PCM stem changed')
            baseline_checks[name] = {'float_identical': True, 'pcm_identical': True,
                                     'baseline_float_sha256': float_hash(baseline[name]),
                                     'baseline_wav_sha256': check['sha256']}
            temporary.unlink()
    clips = []
    for label, start, end in (('first', 0, 24), ('last', 72, 96)):
        entry = write_wav(out / f'ryuteki-source-adoption-{label}-ensemble-24s.wav', 2,
                          [signals['ensemble'][start * FS * 2:end * FS * 2]])
        entry.update(global_seconds=[start, end],
                     boundary_status=('raw excerpt; continuous phrase cut at24s, final zero not required'
                                      if label == 'first' else 'raw excerpt onset at72s; full candidate ending at96s'),
                     pcm_inspection=inspect_pcm(out / entry['file'], 24, 2, label == 'last'))
        clips.append(entry)
    comparison = write_wav(out / 'ryuteki-source-before-after-49s.wav', 2,
                           [baseline['ensemble'][72 * FS * 2:], array('f', [0]) * FS * 2,
                            signals['ensemble'][72 * FS * 2:]])
    comparison['boundary_status'] = 'hard raw excerpt onsets at0s and25s; zero-only intentional gap24..25s; final candidate release ends at49s'
    comparison['pcm_inspection'] = inspect_pcm(out / comparison['file'], 49, 2)
    with wave.open(str(out / comparison['file'])) as wav:
        wav.setpos(24 * FS)
        if any(wav.readframes(FS)):
            raise ValueError('comparison gap not PCM zero')
    comparison['intentional_gap_pcm_zero'] = True
    del baseline, signals
    second, second_meta = make_bank(out / 'regeneration-bank')
    if bank_meta != second_meta:
        raise ValueError('independent own physical bank differs')
    regenerated = render(second, plan())
    for name, signal in regenerated.items():
        entry = next(f for f in files if f['instrument'] == name)
        temporary = out / f'.regen-{name}.wav'
        check = write_wav(temporary, entry['channels'], [signal])
        if float_hash(signal) != hashes[name] or check['sha256'] != entry['sha256']:
            raise ValueError('independent float/PCM regeneration mismatch')
        temporary.unlink()
    for entry in clips:
        start, end = entry['global_seconds']
        temporary = out / '.regen-clip.wav'
        check = write_wav(temporary, 2, [regenerated['ensemble'][start * FS * 2:end * FS * 2]])
        if check['sha256'] != entry['sha256']:
            raise ValueError('independent clip regeneration mismatch')
        temporary.unlink()
    repeated_baseline, _ = body.render(second, body.plan())
    temporary = out / '.regen-comparison.wav'
    check = write_wav(temporary, 2,
                      [repeated_baseline['ensemble'][72 * FS * 2:], array('f', [0]) * FS * 2,
                       regenerated['ensemble'][72 * FS * 2:]])
    if check['sha256'] != comparison['sha256']:
        raise ValueError('independent before-after comparison regeneration mismatch')
    temporary.unlink()
    del repeated_baseline, regenerated
    spans = body.sounding_spans(events)
    coverage = [{'primary': i + 1, 'seconds': (i + .5) * 3,
                 'active': {n: [e['id'] for e in events if e['instrument'] == n and
                               e['start'] <= (i + .5) * 3 < e['end']] for n in INSTRUMENTS}}
                for i in range(32)]
    if any(not row['active'][n] for row in coverage for n in INSTRUMENTS):
        raise ValueError('missing primary midpoint sound')
    save_json(out / 'source-adoption-events.json', events)
    save_json(out / 'source-adoption-sounding-spans.json', spans)
    inputs = [SPEC, Path(__file__), ROOT / 'test_ryuteki_source_adoption.py',
              ROOT.parents[2] / 'docs/tasks/ryuteki-source-adoption-v1/README.md',
              ROOT.parents[2] / '.github/workflows/ryuteki-source-adoption.yml']
    inputs.extend(ROOT.parents[2] / name for name in spec['dependency_hashes'])
    report = {'version': spec['version'],
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'dependency_commit': BASE_COMMIT, 'duration_seconds': 96, 'a4_hz': 430,
              'source_partition': spec['source_partition'], 'source_refs': [c['source'] for c in spec['cells']],
              'source_cell_mapping': [{'cell_id': c['id'], 'legacy_cell_id': c['legacy_cell_id']} for c in spec['cells']],
              'ryuteki_primary_cells': 32, 'source_locations': 32, 'remapped_cells': 24, 'new_final_cells': 8,
              'event_count': len(events), 'ryuteki_event_count': sum(e['instrument'] == 'ryuteki' for e in events),
              'sounding_spans': len(spans), 'primary_midpoint_coverage': coverage,
              'baseline_non_ryuteki_checks': baseline_checks, 'only_ryuteki_and_mix_audio_changed': True,
              'metrics': measured, 'float_f32le_sha256': hashes, 'pcm_inspection': pcm_checks,
              'files': files, 'clips': clips, 'comparison_file': comparison,
              'comparison_timing_seconds': {'before_last24': [0, 24], 'intentional_silence': [24, 25], 'after_last24': [25, 49]},
              'physical_bank': bank_meta, 'independent_regeneration_float_identical': True,
              'independent_regeneration_pcm_identical': True,
              'source_hashes': {str(p.relative_to(ROOT.parents[2])): digest(p) for p in inputs},
              'event_sha256': digest(out / 'source-adoption-events.json'),
              'sounding_spans_sha256': digest(out / 'source-adoption-sounding-spans.json'),
              'verified_exit': False, 'tomede': False, 'traditional_nihen_verified': False,
              'fully_verified_performance_events': 0, 'strict_reading_status': 'BLOCKED_PUBLIC_EVIDENCE',
              'musical_acceptance': 'UNEVALUATED', 'unknowns': spec['unknowns'],
              'rights': 'own physical model bank only; no recordings or new measurements'}
    save_json(out / 'source-adoption-inspection.json', report)
    print(json.dumps({'inspection': str(out / 'source-adoption-inspection.json'),
                      'files': files, 'clips': clips, 'comparison_file': comparison}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    generate(parser.parse_args().output_dir)
