"""Editable listening balance from pinned, self-generated 192-second PCM stems."""
import argparse
from array import array
import json
from pathlib import Path
import shutil
import subprocess
import sys
import wave
from .audio import ROOT, digest, save_json
from .models import FS
from .three_pipe_prefix import INSTRUMENTS

FRAMES = 192 * FS
COEFFICIENTS = {'sho': (70, 70), 'ryuteki': (85, 50), 'hichiriki': (50, 85)}
DEFAULT_LEVELS = dict.fromkeys(INSTRUMENTS, 100)
SOURCE_INPUTS = {
    *(f'features/gagaku/product/{n}' for n in (
        'three-pipe-pass-v1.json', 'three_pipe_pass.py', 'three_pipe_body.py', 'three-pipe-body-v1.json',
        'pass-player.html', 'pass-player.js', 'audio.py', 'models.py', 'three_pipe_prefix.py',
        'sho_continuous.py', 'sho_adoption.py', 'sho-adoption-v1.json', 'sho-continuous-v1.json', 'score-fixture.json')),
    'features/gagaku/evaluate.py', 'features/gagaku/sho_one_pipe.py', 'docs/tasks/three-pipe-pass-v1/README.md',
}
# Approved PR9/main physical render hashes; allow the verified <=1 LSB Linux/macOS variants only.
APPROVED_AUDIO = {
    'sho': {'1de66405c3897d7aa875f37a9881aae80994bb36a4d8483cbfc02d6bc7eefa49'},
    'ryuteki': {'86149bac95ec7696d74e7b21d33d51cdfe8692d6d33e013de650148974813c6d',
                '00a8a6db19a3aafa3eedc64daf00cffea449117a17445578b69cdfc391da4c80'},
    'hichiriki': {'b9d61c8e22ff9003d94c0743ae4ce9f5c3154a99d3af969924bc9111bb7d6605'},
    'ensemble': {'bf7009a0b35f3d150fd013d7c0fe795884aa621b32f78951d2bbda0d13179ada',
                 '71378ef8ccb45b326c58a0e97d70263cd30d42c950076e6ad82151b1b06eb90f'},
}


def validate_levels(levels):
    if not isinstance(levels, dict) or set(levels) != set(INSTRUMENTS):
        raise ValueError('levels must name exactly the three generated pipes')
    if any(type(v) is not int or not 0 <= v <= 150 for v in levels.values()):
        raise ValueError('levels must be integer percentages from 0 to 150')
    if not any(levels.values()):
        raise ValueError('at least one pipe must be audible')
    return dict(levels)


def mix_pcm(stems, levels):
    levels = validate_levels(levels)
    if set(stems) != set(INSTRUMENTS) or not all(isinstance(v, array) and v.typecode == 'h' for v in stems.values()) or not stems['sho'] or len({len(v) for v in stems.values()}) != 1:
        raise ValueError('three equal nonempty mono stems required')
    peaks = {name: max(map(abs, values)) for name, values in stems.items()}
    bounds = [sum(peaks[n] * COEFFICIENTS[n][c] * levels[n] for n in INSTRUMENTS) / 10000 for c in (0, 1)]
    if max(bounds) >= 32766.5:
        raise ValueError('balance exceeds conservative PCM headroom')
    weights = [[COEFFICIENTS[n][c] * levels[n] for n in INSTRUMENTS] for c in (0, 1)]
    result = array('h')
    for samples in zip(*(stems[n] for n in INSTRUMENTS)):
        for row in weights:
            numerator = sum(sample * weight for sample, weight in zip(samples, row))
            magnitude = (abs(numerator) + 5000) // 10000
            result.append(-magnitude if numerator < 0 else magnitude)
    return result, {'conservative_peak_pcm': bounds, 'maximum_absolute_pcm': max(map(abs, result)),
                    'full_scale_count': sum(abs(v) >= 32767 for v in result)}


def read_pcm(path, channels, frames=FRAMES):
    with wave.open(str(path)) as wav:
        if (wav.getnchannels(), wav.getnframes(), wav.getframerate(), wav.getsampwidth(), wav.getcomptype()) != (channels, frames, FS, 2, 'NONE'):
            raise ValueError('wrong generated PCM format')
        result = array('h', wav.readframes(frames))
    if sys.byteorder != 'little':
        result.byteswap()
    return result


def write_pcm(path, values):
    data = array('h', values)
    if sys.byteorder != 'little':
        data.byteswap()
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((2, 2, FS, 0, 'NONE', 'not compressed'))
        wav.writeframes(data.tobytes())


def load_source(directory):
    source = Path(directory)
    report = json.loads((source / 'pass-inspection.json').read_text())
    if (report.get('version') != 'three-pipe-pass-v1' or report.get('duration_seconds') != 192 or
        report.get('verified_exit') is not False or report.get('tomede') is not False or
        report.get('traditional_nihen_verified') is not False or report.get('fully_verified_performance_events') != 0 or
        report.get('strict_reading_status') != 'BLOCKED_PUBLIC_EVIDENCE' or report.get('musical_acceptance') != 'UNEVALUATED'):
        raise ValueError('wrong or promoted source candidate')
    expected_files = [f'three-pipe-pass-{n}-192s.wav' for n in (*INSTRUMENTS, 'ensemble')]
    entries = {v['file']: v for v in report['files']}
    for instrument, name in zip((*INSTRUMENTS, 'ensemble'), expected_files):
        if name not in entries or entries[name]['sha256'] not in APPROVED_AUDIO[instrument] or digest(source / name) != entries[name]['sha256']:
            raise ValueError('source audio hash mismatch')
    if set(report.get('source_hashes', {})) != SOURCE_INPUTS:
        raise ValueError('missing pinned source hashes')
    for path, sha in report['source_hashes'].items():
        if Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('source path outside the repository')
        if digest(ROOT.parents[2] / path) != sha:
            raise ValueError('source implementation or adoption differs')
    stems = {n: read_pcm(source / f'three-pipe-pass-{n}-192s.wav', 1) for n in INSTRUMENTS}
    for values in stems.values():
        if max(map(abs, values)) >= 32767 or values[-1] != 0:
            raise ValueError('invalid source PCM')
    return report, stems


def generate(source_dir, directory, levels=None):
    source, out = Path(source_dir).resolve(), Path(directory).resolve()
    if source == out or source in out.parents:
        raise ValueError('keep the source performance directory separate')
    levels = validate_levels(DEFAULT_LEVELS if levels is None else levels)
    report, stems = load_source(source)
    samples, metrics = mix_pcm(stems, levels)
    default, _ = mix_pcm(stems, DEFAULT_LEVELS)
    reference = read_pcm(source / 'three-pipe-pass-ensemble-192s.wav', 2)
    deviation = max(abs(a-b) for a, b in zip(default, reference))
    if deviation > 2:
        raise ValueError('default reconstructed mix differs by more than 2 LSB')
    out.mkdir(parents=True, exist_ok=True)
    audio = out / 'balance-192s.wav'
    write_pcm(audio, samples)
    write_pcm(out / '.regeneration.wav', mix_pcm(stems, levels)[0])
    if digest(audio) != digest(out / '.regeneration.wav'):
        raise ValueError('balance regeneration differs')
    (out / '.regeneration.wav').unlink()
    if any(samples[-2:]) or metrics['full_scale_count']:
        raise ValueError('invalid final balance')
    files = []
    for name in INSTRUMENTS:
        filename = f'three-pipe-pass-{name}-192s.wav'
        shutil.copyfile(source / filename, out / filename)
        files.append({'instrument': name, 'file': filename, 'sha256': digest(out / filename),
                      'frames': FRAMES, 'sample_rate_hz': FS, 'channels': 1})
    for filename in ('balance-player.html', 'balance-player.js', 'pass-player.js'):
        shutil.copyfile(ROOT / filename, out / filename)
    config = {'version': 'three-pipe-balance-settings-v1', 'levels_percent': levels,
              'timing_and_pitch_unchanged': True, 'verified_exit': False, 'tomede': False}
    save_json(out / 'balance-settings.json', config)
    manifest = {'version': 'three-pipe-balance-v1', 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                'performance_source_commit': report['source_commit'], 'source_inspection_sha256': digest(source / 'pass-inspection.json'),
                'performance_source_hashes': report['source_hashes'], 'source_files': files, 'sample_rate_hz': FS,
                'frames': FRAMES, 'duration_seconds': 192, 'levels_percent': levels, 'coefficients_percent': COEFFICIENTS,
                'allowed_level_percent': [0, 150], 'pcm_rule': 'integer numerator / 10000; nearest, ties away from zero',
                'default_vs_original_maximum_lsb': deviation, 'metrics': metrics, 'repeated_generation_identical': True,
                'file': audio.name, 'sha256': digest(audio), 'verified_exit': False, 'tomede': False,
                'traditional_nihen_verified': False, 'strict_reading_status': 'BLOCKED_PUBLIC_EVIDENCE',
                'musical_acceptance': 'UNEVALUATED', 'controls_status': 'author_listening_balance_not_measured_performance',
                'implementation_hashes': {n: digest(ROOT/n) for n in ('three_pipe_balance.py', 'balance-player.js', 'balance-player.html', 'pass-player.js')}}
    save_json(out / 'balance-inspection.json', manifest)
    print(json.dumps({'files': len(files)+1, 'sha256': manifest['sha256'], 'metrics': metrics, 'default_vs_original_maximum_lsb': deviation}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--settings', type=Path, help='saved player settings JSON')
    args = parser.parse_args()
    levels = None
    if args.settings:
        saved = json.loads(args.settings.read_text())
        if saved.get('version') != 'three-pipe-balance-settings-v1' or saved.get('verified_exit') is not False or saved.get('tomede') is not False or saved.get('timing_and_pitch_unchanged') is not True:
            raise ValueError('wrong or promoted settings')
        levels = saved['levels_percent']
    generate(args.source_dir, args.output_dir, levels)
