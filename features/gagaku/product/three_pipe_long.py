"""384-second physical three-pipe candidate with authored, unverified exits."""
import argparse
from array import array
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import wave

from .audio import ROOT, digest, make_bank, save_json, voice, write_wav
from .models import FS
from .three_pipe_body import sounding_spans as body_spans
from .three_pipe_pass import plan as pass_plan
from .three_pipe_prefix import INSTRUMENTS, metrics

SPEC = ROOT / 'three-pipe-long-v1.json'
BODY = 96
PASSES = 4
DURATION = BODY * PASSES
RELEASE = .25
EXIT_SECONDS = tuple(BODY * i for i in range(1, PASSES + 1))


def _policy():
    spec = json.loads(SPEC.read_text())
    if (spec['body_seconds'] != BODY or spec['passes'] != PASSES or
            spec['duration_seconds'] != DURATION or spec['a4_hz'] != 430 or
            spec['attack_seconds'] != .15 or spec['release_seconds'] != RELEASE or
            spec['exit_adoption']['eligible_seconds'] != list(EXIT_SECONDS) or
            spec['exit_adoption']['deadline_seconds'] != [t - RELEASE for t in EXIT_SECONDS] or
            spec['exit_adoption']['verified_exit'] is not False or
            spec['exit_adoption']['tomede'] is not False or
            spec['repeat_adoption']['traditional_nihen_verified'] is not False or
            spec['fully_verified_performance_events'] != 0 or
            spec['strict_reading_status'] != 'BLOCKED_PUBLIC_EVIDENCE' or
            spec['musical_acceptance'] != 'UNEVALUATED'):
        raise ValueError('changed or promoted long candidate policy')
    for name, expected in spec['dependency_hashes'].items():
        if digest(ROOT.parents[2] / name) != expected:
            raise ValueError(f'pinned long dependency changed: {name}')
    return spec


def finish_plan(seconds):
    """Select the next deadline still allowing the authored 250ms release.

    After the last deadline, the bounded performance completes its already
    scheduled terminal release. This does not claim a new full release can
    start after a late request, or that any candidate exit is source verified.
    """
    if (type(seconds) not in (int, float) or not math.isfinite(seconds) or
            not 0 <= seconds <= DURATION):
        raise ValueError('request outside bounded candidate performance')
    boundary = next((t for t in EXIT_SECONDS if seconds <= t - RELEASE), DURATION)
    deadline = boundary - RELEASE
    return {'request_seconds': seconds, 'request_frame': math.floor(seconds * FS),
            'end_frame': boundary * FS, 'release_start_frame': round(deadline * FS),
            'full_release_after_request': seconds <= deadline,
            'request_status': ('candidate_release_scheduled' if seconds <= deadline else
                               'bounded_terminal_completion_release_already_scheduled'),
            'verified_exit': False, 'tomede': False, 'kind': 'author_body_boundary_release'}


def _compile():
    _policy()
    base = pass_plan()
    result = []
    for index in range(PASSES):
        template_pass = 1 if index == 0 else 2
        offset = (index + 1 - template_pass) * BODY
        for event in base:
            if event['pass_number'] != template_pass:
                continue
            e = copy.deepcopy(event)
            e.update(id=f"pass{index + 1}.{event['source_event_id']}",
                     start=event['start'] + offset, end=event['end'] + offset,
                     pass_number=index + 1, canonical_pass_event_id=event['id'])
            result.append(e)
    return result


def validate(events):
    canonical = {e['id']: e for e in _compile()}
    if (not isinstance(events, list) or len(events) != len(canonical) or
            any(not isinstance(e, dict) or not isinstance(e.get('id'), str) or
                e != canonical.get(e['id']) for e in events) or
            len({e['id'] for e in events}) != len(events)):
        raise ValueError('events differ from pinned four-pass adoption')
    for index in range(1, PASSES + 1):
        for inst in INSTRUMENTS:
            expected = {f'{inst}.L{line}.P{point}' for line in range(1, 5) for point in range(1, 9)}
            actual = {c for e in events if e['pass_number'] == index and e['instrument'] == inst
                      for c in e['cell_ids']}
            if actual != expected:
                raise ValueError('missing pass coverage')


def plan():
    events = _compile()
    validate(events)
    return events


def sounding_spans(events):
    validate(events)
    # Keep inherited melodic continuation semantics, then merge common sho
    # pipes before generating any samples. No pre-rendered body WAV is joined.
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
    for e in sounding_spans(events):
        start, end = round(e['start'] * FS), round(e['end'] * FS)
        sound = voice(bank, e['instrument'], e['midi'] + 12 * math.log2(430 / 440),
                      (end - start) / FS, .15, RELEASE)
        if len(sound) != end - start:
            raise ValueError('voice length differs from authored span')
        for i, value in enumerate(sound):
            stems[e['instrument']][start + i] += value
    mix = array('f')
    for sho, ryuteki, hichiriki in zip(stems['sho'], stems['ryuteki'], stems['hichiriki']):
        mix.extend((sho * .7 + ryuteki * .85 + hichiriki * .5,
                    sho * .7 + ryuteki * .5 + hichiriki * .85))
    return {**stems, 'ensemble': mix}


def boundary_exit(signal, channels, end_frame):
    if (type(channels) is not int or channels not in (1, 2) or type(end_frame) is not int or
            end_frame not in [t * FS for t in EXIT_SECONDS] or
            len(signal) < end_frame * channels):
        raise ValueError('exit must use an available authored body boundary')
    result = array('f', signal[:end_frame * channels])
    start = end_frame - round(RELEASE * FS)
    for frame in range(start, end_frame):
        gain = (end_frame - 1 - frame) / (end_frame - 1 - start)
        for ch in range(channels):
            result[frame * channels + ch] *= gain
    return result


def _float_hash(signal):
    data = array('f', signal)
    if sys.byteorder != 'little':
        data.byteswap()
    return hashlib.sha256(data.tobytes()).hexdigest()


def _boundaries(signal, channels):
    result = []
    for seconds in EXIT_SECONDS[:-1]:
        frame = seconds * FS
        window = signal[(frame - FS // 2) * channels:(frame + FS // 2) * channels]
        measured = metrics(window, channels)
        measured['boundary_channel_steps'] = [abs(signal[frame * channels + ch] -
                                                   signal[(frame - 1) * channels + ch])
                                              for ch in range(channels)]
        result.append({'seconds': seconds, 'metrics': measured})
    return result


def _inspect_pcm(path, expected_seconds, channels):
    peak = 0
    with wave.open(str(path)) as wav:
        if (wav.getframerate(), wav.getnframes(), wav.getnchannels(), wav.getsampwidth()) != (
                FS, expected_seconds * FS, channels, 2):
            raise ValueError('wrong delivered PCM format or length')
        while True:
            raw = wav.readframes(FS)
            if not raw:
                break
            samples = array('h', raw)
            if sys.byteorder != 'little':
                samples.byteswap()
            peak = max(peak, max(map(abs, samples)))
        wav.setpos(wav.getnframes() - 1)
        last = array('h', wav.readframes(1))
        if peak >= 32767 or any(last):
            raise ValueError('full-scale or nonzero final delivered PCM frame')
        boundaries = []
        for seconds in EXIT_SECONDS[:-1] if expected_seconds == DURATION else ():
            wav.setpos(seconds * FS - FS // 2)
            samples = array('h', wav.readframes(FS))
            if sys.byteorder != 'little':
                samples.byteswap()
            normalized = array('f', (x / 32767 for x in samples))
            measured = metrics(normalized, channels)
            at = FS // 2
            measured['boundary_channel_steps'] = [abs(normalized[at * channels + ch] -
                                                       normalized[(at - 1) * channels + ch])
                                                  for ch in range(channels)]
            boundaries.append({'seconds': seconds, 'metrics': measured})
    return {'peak_pcm': peak, 'final_frame_zero': True, 'boundary_metrics': boundaries}


def exit_requests():
    requests = [0, DURATION]
    for boundary in EXIT_SECONDS:
        deadline = boundary - RELEASE
        requests.extend(deadline + offset / FS for offset in (-1, -.75, -.25, 0, .25, .75, 1))
        requests.append(boundary)
    rng = random.Random(430)
    requests.extend(rng.uniform(0, DURATION) for _ in range(1000))
    logs = [finish_plan(t) for t in requests]
    for entry in logs:
        eligible = [b for b in EXIT_SECONDS if entry['request_seconds'] <= b - RELEASE]
        expected = eligible[0] if eligible else DURATION
        if (entry['end_frame'] != expected * FS or entry['end_frame'] < entry['request_frame'] or
                entry['verified_exit'] is not False or entry['tomede'] is not False):
            raise ValueError('unsafe or promoted candidate exit')
    return logs


def generate(directory):
    spec = _policy()
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    events = plan()
    spans = sounding_spans(events)
    bank, bank_meta = make_bank(out / 'bank')
    signals = render(bank, events)
    signals['early'] = boundary_exit(signals['ensemble'], 2, BODY * FS)
    measured, float_hashes, boundaries, files, pcm_checks = {}, {}, {}, [], {}
    for name, signal in signals.items():
        channels = 2 if name in ('ensemble', 'early') else 1
        duration = BODY if name == 'early' else DURATION
        measured[name] = metrics(signal, channels)
        if measured[name]['nonfinite_count'] or measured[name]['full_scale_count']:
            raise ValueError('invalid generated float signal')
        float_hashes[name] = _float_hash(signal)
        if name != 'early':
            boundaries[name] = _boundaries(signal, channels)
        entry = write_wav(out / f'three-pipe-long-{name}-{duration}s.wav', channels, [signal])
        files.append(entry)
        pcm_checks[name] = _inspect_pcm(out / entry['file'], duration, channels)
    del signal, signals
    second, second_meta = make_bank(out / 'regeneration-bank')
    regenerated = render(second, plan())
    regenerated['early'] = boundary_exit(regenerated['ensemble'], 2, BODY * FS)
    for name, entry in zip(regenerated, files):
        if _float_hash(regenerated[name]) != float_hashes[name]:
            raise ValueError('independent float regeneration mismatch')
        temporary = out / f'.regen-{name}.wav'
        check = write_wav(temporary, entry['channels'], [regenerated[name]])
        if check['sha256'] != entry['sha256']:
            raise ValueError('independent PCM regeneration mismatch')
        temporary.unlink()
    if bank_meta != second_meta:
        raise ValueError('independent physical bank regeneration mismatch')
    logs = exit_requests()
    inputs = [SPEC, Path(__file__), ROOT / 'test_three_pipe_long.py',
              ROOT / 'long-player.html', ROOT / 'long-player.js', ROOT / 'test_long_player.cjs',
              ROOT.parents[2] / 'docs/tasks/three-pipe-long-v1/README.md',
              ROOT.parents[2] / '.github/workflows/three-pipe-long.yml',
              ROOT.parents[2] / 'docs/PRODUCT_GOAL_V1.md']
    inputs.extend(ROOT.parents[2] / name for name in spec['dependency_hashes'])
    report = {'version': 'three-pipe-long-v1',
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'dependency_commit': spec['dependency_commit'], 'duration_seconds': DURATION,
              'body_passes': PASSES, 'primary_cell_visits': 32 * 3 * PASSES,
              'ledger_events': len(events), 'sounding_spans': len(spans),
              'initial_pitch_difference': False, 'initial_timing_difference': False,
              'metrics': measured, 'float_f32le_sha256': float_hashes,
              'repeat_boundary_float_metrics': boundaries, 'pcm_inspection': pcm_checks,
              'files': files, 'physical_bank': bank_meta,
              'independent_regeneration_float_identical': True,
              'independent_regeneration_pcm_identical': True,
              'source_hashes': {str(p.relative_to(ROOT.parents[2])): digest(p) for p in inputs},
              'exit_request_checks': len(logs), 'exit_request_seed': 430,
              'eligible_exit_seconds': list(EXIT_SECONDS),
              'exit_deadline_seconds': [b - RELEASE for b in EXIT_SECONDS],
              'exit_kind': 'author_body_boundary_release', 'verified_exit': False, 'tomede': False,
              'traditional_nihen_verified': False, 'fully_verified_performance_events': 0,
              'strict_reading_status': 'BLOCKED_PUBLIC_EVIDENCE', 'musical_acceptance': 'UNEVALUATED',
              'rights': 'own physical model bank only; no reference recording or new measurement',
              'remaining': spec['remaining']}
    save_json(out / 'long-events.json', events)
    save_json(out / 'long-sounding-spans.json', spans)
    save_json(out / 'long-exit-requests.json', logs)
    save_json(out / 'long-inspection.json', report)
    for name in ('long-player.html', 'long-player.js'):
        (out / name).write_bytes((ROOT / name).read_bytes())
    print(json.dumps({'inspection': str(out / 'long-inspection.json'),
                      'files': files, 'exit_request_checks': len(logs)}, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    generate(parser.parse_args().output_dir)
