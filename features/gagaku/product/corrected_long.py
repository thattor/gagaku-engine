"""Corrected 384-second three-pipe candidate with inherited finish/cancel/restart."""
import argparse
from array import array
import copy
import json
import math
from pathlib import Path
import subprocess

from .audio import ROOT, digest, make_bank, save_json, voice, write_wav
from .models import FS
from . import three_pipe_long as inherited
from . import ryuteki_source_adoption as corrected
from .three_pipe_body import sounding_spans as body_spans
from .three_pipe_prefix import INSTRUMENTS, metrics

SPEC = ROOT / 'corrected-long-v1.json'
BODY, PASSES, DURATION, RELEASE = 96, 4, 384, .25
DEPENDENCY_COMMIT = '2f80f858b921f5b3627bba2ddd1e486a1f21643c'
PLAYER_COMMIT = 'da1af67ac4e99a24ce233a7d75f50aa3dfc6b394'
PLAYER_SHA256 = '7bc994a90fecd1870ac7113554a1fedfcb643557f0c68a1e353c578cdfeb1702'


def policy():
    spec = json.loads(SPEC.read_text())
    old, adoption = inherited._policy(), corrected.policy()
    required = set(old['dependency_hashes']) | set(adoption['dependency_hashes']) | {
        'features/gagaku/product/three_pipe_long.py', 'features/gagaku/product/three-pipe-long-v1.json',
        'features/gagaku/product/ryuteki_source_adoption.py',
        'features/gagaku/product/ryuteki-source-adoption-v1.json'}
    if (spec.get('version') != 'corrected-long-v1' or spec.get('dependency_commit') != DEPENDENCY_COMMIT or
            spec.get('player_commit') != PLAYER_COMMIT or spec.get('controller_sha256') != PLAYER_SHA256 or
            spec.get('body_seconds') != BODY or spec.get('passes') != PASSES or
            spec.get('duration_seconds') != DURATION or spec.get('a4_hz') != 430 or
            spec.get('attack_seconds') != .15 or spec.get('release_seconds') != RELEASE or
            spec.get('eligible_exit_seconds') != [96, 192, 288, 384] or
            spec.get('deadline_seconds') != [95.75, 191.75, 287.75, 383.75] or
            spec.get('source_partition') != adoption['source_partition'] or
            set(spec.get('dependency_hashes', {})) != required or
            spec.get('verified_exit') is not False or spec.get('tomede') is not False or
            spec.get('traditional_nihen_verified') is not False or
            spec.get('fully_verified_performance_events') != 0 or
            spec.get('strict_reading_status') != 'BLOCKED_PUBLIC_EVIDENCE' or
            spec.get('musical_acceptance') != 'UNEVALUATED' or
            digest(ROOT / 'corrected-long-player.js') != PLAYER_SHA256):
        raise ValueError('changed or promoted corrected long candidate policy')
    for name, expected in spec['dependency_hashes'].items():
        if digest(ROOT.parents[2] / name) != expected:
            raise ValueError(f'pinned corrected long dependency changed: {name}')
    return spec


def _compile():
    policy()
    result = [copy.deepcopy(e) for e in inherited.plan() if e['instrument'] != 'ryuteki']
    melody = [e for e in corrected.plan() if e['instrument'] == 'ryuteki']
    for index in range(PASSES):
        for event in melody:
            e = copy.deepcopy(event)
            e.update(id=f"pass{index + 1}.{event['id']}", source_event_id=event['id'],
                     canonical_corrected_event_id=event['id'], pass_number=index + 1,
                     start=event['start'] + index * BODY, end=event['end'] + index * BODY)
            result.append(e)
    return result


def validate(events):
    canonical = _compile()
    if not isinstance(events, list) or events != canonical or len({e['id'] for e in events}) != len(events):
        raise ValueError('events differ from pinned corrected four-pass adoption')
    for number in range(1, PASSES + 1):
        for instrument in INSTRUMENTS:
            actual = {c for e in events if e['pass_number'] == number and e['instrument'] == instrument
                      for c in e['cell_ids']}
            expected = {f'{instrument}.L{line}.P{point}' for line in range(1, 5) for point in range(1, 9)}
            if actual != expected:
                raise ValueError('missing corrected pass coverage')
    for e in events:
        if (e['performance_verified'] is not False or e['timing_status'] != 'author_design' or
                type(e['midi']) is not int or not 0 <= e['midi'] <= 127 or
                not all(math.isfinite(e[k]) for k in ('start', 'end')) or
                not 0 <= e['start'] < e['end'] <= DURATION):
            raise ValueError('invalid or promoted corrected event')


def plan():
    events = _compile()
    validate(events)
    return events


def sounding_spans(events):
    validate(events)
    result = body_spans(events)
    joined = [e for e in result if e['instrument'] != 'sho']
    for pipe in sorted({e['pipe'] for e in result if e['instrument'] == 'sho'}):
        current = None
        for span in sorted((e for e in result if e['instrument'] == 'sho' and e['pipe'] == pipe),
                           key=lambda e: e['start']):
            if current and current['midi'] == span['midi'] and current['end'] == span['start']:
                current['end'] = span['end']
                current['ledger_ids'].extend(span['ledger_ids'])
            else:
                current = copy.deepcopy(span)
                joined.append(current)
    return sorted(joined, key=lambda e: (e['start'], e['instrument'], e.get('pipe', '')))


def render(bank, events):
    stems = {n: array('f', [0]) * (DURATION * FS) for n in INSTRUMENTS}
    for span in sounding_spans(events):
        start, end = round(span['start'] * FS), round(span['end'] * FS)
        signal = voice(bank, span['instrument'], span['midi'] + 12 * math.log2(430 / 440),
                       (end - start) / FS, .15, RELEASE)
        if len(signal) != end - start:
            raise ValueError('voice length differs from corrected span')
        for i, value in enumerate(signal):
            stems[span['instrument']][start + i] += value
    mix = array('f')
    for sho, ryuteki, hichiriki in zip(stems['sho'], stems['ryuteki'], stems['hichiriki']):
        mix.extend((sho * .7 + ryuteki * .85 + hichiriki * .5,
                    sho * .7 + ryuteki * .5 + hichiriki * .85))
    return {**stems, 'ensemble': mix}


def finish_plan(seconds):
    policy()
    return inherited.finish_plan(seconds)


def generate(directory):
    out = Path(directory)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError('output directory must be fresh or empty; existing artifacts are preserved')
    spec = policy()
    out.mkdir(parents=True, exist_ok=True)
    inputs = [SPEC, Path(__file__), ROOT / 'test_corrected_long.py',
              ROOT / 'corrected-long-player.html', ROOT / 'corrected-long-player.js',
              ROOT / 'test_corrected_long_player.cjs',
              ROOT.parents[2] / 'docs/tasks/corrected-long-v1/README.md',
              ROOT.parents[2] / '.github/workflows/corrected-long.yml']
    inputs.extend(ROOT.parents[2] / name for name in spec['dependency_hashes'])
    input_hashes = {str(p.relative_to(ROOT.parents[2])): digest(p) for p in inputs}
    events = plan()
    spans = sounding_spans(events)
    bank, bank_meta = make_bank(out / 'bank')
    signals = render(bank, events)
    baseline = inherited.render(bank, inherited.plan())
    baseline_checks = {}
    for name in ('sho', 'hichiriki'):
        if signals[name] != baseline[name]:
            raise ValueError('frozen non-ryuteki float stem changed')
        baseline_checks[name] = {'float_identical': True,
                                'baseline_float_sha256': inherited._float_hash(baseline[name])}
    if signals['ryuteki'] == baseline['ryuteki'] or signals['ensemble'] == baseline['ensemble']:
        raise ValueError('ryuteki correction did not change melody and mix')
    signals['early'] = inherited.boundary_exit(signals['ensemble'], 2, BODY * FS)
    measured, hashes, boundaries, files, pcm_checks = {}, {}, {}, [], {}
    for name, signal in signals.items():
        channels = 2 if name in ('ensemble', 'early') else 1
        duration = BODY if name == 'early' else DURATION
        measured[name] = metrics(signal, channels)
        if measured[name]['nonfinite_count'] or measured[name]['full_scale_count']:
            raise ValueError('invalid corrected long float audio')
        hashes[name] = inherited._float_hash(signal)
        if name != 'early':
            boundaries[name] = inherited._boundaries(signal, channels)
        entry = write_wav(out / f'corrected-long-{name}-{duration}s.wav', channels, [signal])
        entry.update(instrument=name, duration_seconds=duration)
        files.append(entry)
        pcm_checks[name] = inherited._inspect_pcm(out / entry['file'], duration, channels)
        if name in baseline_checks:
            temporary = out / f'.baseline-{name}.wav'
            check = write_wav(temporary, 1, [baseline[name]])
            if check['sha256'] != entry['sha256']:
                raise ValueError('frozen non-ryuteki PCM stem changed')
            baseline_checks[name].update(pcm_identical=True, baseline_wav_sha256=check['sha256'])
            temporary.unlink()
    del baseline, signal, signals
    if any(digest(ROOT.parents[2] / name) != expected for name, expected in input_hashes.items()):
        raise ValueError('source inputs changed before first-pass inspection')
    logs = inherited.exit_requests()
    save_json(out / 'corrected-long-events.json', events)
    save_json(out / 'corrected-long-sounding-spans.json', spans)
    save_json(out / 'corrected-long-exit-requests.json', logs)
    for name in ('corrected-long-player.html', 'corrected-long-player.js'):
        (out / name).write_bytes((ROOT / name).read_bytes())
    first_pass = {
        'version': spec['version'], 'generation_status': 'IN_PROGRESS',
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'dependency_commit': DEPENDENCY_COMMIT, 'player_dependency_commit': PLAYER_COMMIT,
        'controller_sha256': PLAYER_SHA256, 'source_hashes': input_hashes,
        'duration_seconds': DURATION, 'files': files, 'physical_bank': bank_meta,
        'metrics': measured, 'pcm_inspection': pcm_checks,
        'baseline_non_ryuteki_checks': baseline_checks,
        'independent_regeneration_float_identical': False,
        'independent_regeneration_pcm_identical': False,
        'verified_exit': False, 'tomede': False, 'traditional_nihen_verified': False,
        'fully_verified_performance_events': 0, 'strict_reading_status': 'BLOCKED_PUBLIC_EVIDENCE',
        'musical_acceptance': 'UNEVALUATED', 'unknowns': spec['unknowns']}
    save_json(out / 'corrected-long-first-pass-inspection.json', first_pass)
    save_json(out / 'corrected-long-inspection.json', first_pass)
    print(json.dumps({'first_pass_player_ready': str(out / 'corrected-long-player.html'),
                      'generation_status': 'IN_PROGRESS'}), flush=True)
    second, second_meta = make_bank(out / 'regeneration-bank')
    if bank_meta != second_meta:
        raise ValueError('independent physical bank regeneration mismatch')
    regenerated = render(second, plan())
    regenerated['early'] = inherited.boundary_exit(regenerated['ensemble'], 2, BODY * FS)
    for name, signal in regenerated.items():
        entry = next(f for f in files if f['instrument'] == name)
        temporary = out / f'.regen-{name}.wav'
        check = write_wav(temporary, entry['channels'], [signal])
        if inherited._float_hash(signal) != hashes[name] or check['sha256'] != entry['sha256']:
            raise ValueError('independent corrected float/PCM regeneration mismatch')
        temporary.unlink()
    del regenerated, signal
    coverage = [{'pass_number': index // 32 + 1, 'primary': index % 32 + 1,
                 'seconds': (index + .5) * 3,
                 'active': {n: [e['id'] for e in events if e['instrument'] == n and
                               e['start'] <= (index + .5) * 3 < e['end']] for n in INSTRUMENTS}}
                for index in range(32 * PASSES)]
    if any(not row['active'][n] for row in coverage for n in INSTRUMENTS):
        raise ValueError('missing corrected primary midpoint sound')
    if any(digest(ROOT.parents[2] / name) != expected for name, expected in input_hashes.items()):
        raise ValueError('source inputs changed during corrected audio generation')
    save_json(out / 'corrected-long-events.json', events)
    save_json(out / 'corrected-long-sounding-spans.json', spans)
    save_json(out / 'corrected-long-exit-requests.json', logs)
    for name in ('corrected-long-player.html', 'corrected-long-player.js'):
        (out / name).write_bytes((ROOT / name).read_bytes())
    preserved_first_pass = json.loads((out / 'corrected-long-first-pass-inspection.json').read_text())
    if preserved_first_pass['files'] != files or preserved_first_pass['source_hashes'] != input_hashes:
        raise ValueError('first-pass evidence differs from completed artifacts')
    report = {'version': spec['version'], 'generation_status': 'COMPLETE',
              'first_pass_inspection_sha256': digest(out / 'corrected-long-first-pass-inspection.json'),
              'first_pass_source_commit': preserved_first_pass['source_commit'],
              'first_pass_files_and_source_hashes_identical': True,
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'dependency_commit': DEPENDENCY_COMMIT, 'player_dependency_commit': PLAYER_COMMIT,
              'controller_sha256': PLAYER_SHA256, 'controller_bytes_identical_pr12': True,
              'source_hashes': input_hashes, 'duration_seconds': DURATION, 'body_passes': PASSES,
              'a4_hz': 430, 'attack_seconds': .15, 'release_seconds': RELEASE,
              'primary_cell_visits': 32 * 3 * PASSES, 'ledger_events': len(events),
              'sounding_spans': len(spans), 'primary_midpoint_coverage': coverage,
              'source_partition': spec['source_partition'],
              'ryuteki_source_locations': [c['source'] for c in corrected.policy()['cells']],
              'unique_ryuteki_source_cells': 32, 'ryuteki_source_cell_visits': 32 * PASSES,
              'canonical_non_ryuteki_events_unchanged': True,
              'baseline_non_ryuteki_checks': baseline_checks, 'only_ryuteki_and_mix_audio_changed': True,
              'physical_bank': bank_meta, 'metrics': measured, 'float_f32le_sha256': hashes,
              'repeat_boundary_float_metrics': boundaries, 'pcm_inspection': pcm_checks, 'files': files,
              'independent_regeneration_float_identical': True,
              'independent_regeneration_pcm_identical': True,
              'exit_request_checks': len(logs), 'exit_request_seed': 430,
              'eligible_exit_seconds': [96, 192, 288, 384],
              'exit_deadline_seconds': [95.75, 191.75, 287.75, 383.75],
              'exit_kind': 'author_body_boundary_release', 'verified_exit': False, 'tomede': False,
              'traditional_nihen_verified': False, 'fully_verified_performance_events': 0,
              'strict_reading_status': 'BLOCKED_PUBLIC_EVIDENCE', 'musical_acceptance': 'UNEVALUATED',
              'operation': 'finish request cancellation and restart after ended; inherited PR12 controller',
              'event_sha256': digest(out / 'corrected-long-events.json'),
              'sounding_spans_sha256': digest(out / 'corrected-long-sounding-spans.json'),
              'exit_requests_sha256': digest(out / 'corrected-long-exit-requests.json'),
              'unknowns': spec['unknowns'],
              'rights': 'own physical model bank only; no recordings or new measurements'}
    save_json(out / 'corrected-long-inspection.json', report)
    print(json.dumps({'inspection': str(out / 'corrected-long-inspection.json'),
                      'files': files, 'exit_request_checks': len(logs)}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    generate(parser.parse_args().output_dir)
