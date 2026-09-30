"""Audible, explicitly provisional score reading; never a product ending."""
import argparse
from array import array
import json
import math
from pathlib import Path
import shutil

from .audio import ROOT, INSTRUMENTS, digest, inspect, make_bank, save_json, voice, write_wav
from .models import FS


def validate(fixture, production=False):
    if production:
        # No replacement of an unread tomede by a fade or diagnostic ending.
        raise ValueError('Complete verified score, repeat route and tomede are unavailable')
    identifiers = [cell['id'] for cell in fixture['cells']]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('duplicate score cell')
    for cell in fixture['cells']:
        if cell['notation_status'] == 'verified' and not cell.get('source'):
            raise ValueError('missing source')
        if cell['pitch_status'] == 'verified' and not cell.get('midi'):
            raise ValueError('missing pitch')
        if cell.get('offset_pulses'):
            offsets = cell['offset_pulses']
            if len(offsets) != len(cell['midi']) or offsets[0] != 0 or any(
                    not 0 <= x < 4 for x in offsets) or offsets != sorted(set(offsets)):
                raise ValueError('invalid within-cell schedule')


def render(bank, fixture, cells, count):
    """Render pitch readings with disclosed design durations, plus explicit unknown gaps."""
    pulse = fixture['design']['seconds_per_pulse']
    seconds = count * 4 * pulse
    stems = {name: array('f', [0.0]) * round(seconds * FS) for name in INSTRUMENTS}
    events, gaps = [], []
    tuning_offset = 12 * math.log2(fixture['design']['a4_hz'] / 440)
    for cell in cells:
        name = cell['id'].split('.')[0]
        row = int(cell['id'].split('.P')[1]) - 1
        line = int(cell['id'].split('.L')[1].split('.')[0]) - 1
        index = line * 8 + row
        if index >= count:
            continue
        if cell['notation_status'] != 'verified' or cell['pitch_status'] == 'unresolved' or not cell.get('midi'):
            gaps.append({'cell_id': cell['id'], 'start_seconds': index * 4 * pulse,
                         'seconds': 4 * pulse, 'reason': 'unread compound chord; not replaced'})
            continue
        offsets = cell.get('offset_pulses', [0] * len(cell['midi']))
        for j, (midi, offset) in enumerate(zip(cell['midi'], offsets)):
            duration = ((offsets[j+1] if j+1 < len(offsets) else 4) - offset) * pulse if name != 'sho' else 4 * pulse
            start = (index * 4 + offset) * pulse
            signal = voice(bank, name, midi + tuning_offset, duration,
                           fixture['design']['attack_seconds'], fixture['design']['release_seconds'])
            position = round(start * FS)
            for k, value in enumerate(signal):
                stems[name][position+k] += value
            events.append({'id': f"{cell['id']}.N{j+1}", 'cell_id': cell['id'],
                           'source': cell['source'], 'symbol': cell['symbol'],
                           'instrument': name, 'midi': midi,
                           'frequency_hz': 430 * 2 ** ((midi-69)/12),
                           'start_seconds': start, 'seconds': duration,
                           'pitch_status': cell['pitch_status'],
                           'timing_status': cell['timing_status'],
                           'technique_status': cell['technique_status']})
    mix = array('f')
    for a, b, c in zip(*(stems[name] for name in INSTRUMENTS)):
        mix.extend((a*.7+b*.85+c*.5, a*.7+b*.5+c*.85))
    return stems, mix, events, gaps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true', help='explicitly accept provisional pitch/register and timing readings')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads((ROOT/'score-fixture.json').read_text())
    validate(fixture, production=not args.preview)
    directory = args.output_dir
    directory.mkdir(parents=True, exist_ok=True)
    bank, metadata = make_bank(directory/'bank')
    # Common five-cell prefix excludes unresolved hichiriki ノ and ryuteki く.
    cells = [c for c in fixture['cells'] if '.L1.' in c['id'] and int(c['id'].split('.P')[1]) <= 5]
    stems, mix, events, gaps = render(bank, fixture, cells, 5)
    files = [write_wav(directory/f'{name}.wav', 1, [signal]) for name, signal in stems.items()]
    files.append(write_wav(directory/'ensemble.wav', 2, [mix]))
    sho_cells = [c for c in fixture['cells'] if c['id'].startswith('sho.')]
    body, _, body_events, body_gaps = render(bank, fixture, sho_cells, 32)
    files.append(write_wav(directory/'sho-body-reading.wav', 1, [body['sho']]))
    save_json(directory/'events.json', {'prefix': events, 'sho_body': body_events, 'gaps': body_gaps})
    save_json(directory/'score-fixture.json', fixture)
    for name in ('score-sources.json', 'score-reading.md', 'rights.json'):
        shutil.copyfile(ROOT/name, directory/name)
    save_json(directory/'manifest.json', {
        'classification': 'score-derived preview, NOT verified complete Goshouraku-kyu',
        'ending': 'excerpt cutoff only; NOT tomede or valid musical exit',
        'prefix_cells': 5, 'prefix_seconds': 30, 'sho_body_seconds': 192,
        'source_fixture_sha256': digest(ROOT/'score-fixture.json'),
        'source_inventory_sha256': digest(ROOT/'score-sources.json'),
        'rights_sha256': digest(ROOT/'rights.json'),
        'goal_sha256': digest(ROOT/'PRODUCT_GOAL_V1.md'),
        'code_sha256': {p.name: digest(p) for p in (ROOT/'score_audio.py', ROOT/'audio.py', ROOT/'models.py', ROOT.parent/'sho_one_pipe.py', ROOT.parent/'evaluate.py')},
        'bank': metadata, 'files': files, 'events': len(events),
        'sho_body_gaps': body_gaps, 'metrics': {n: inspect(s) for n, s in stems.items()},
        'rights': 'PD score reading + own physical bank only; no reference media',
        'product_E': 'BLOCKED; no 5/10/20 min score operations performed'})
    (directory/'player.html').write_text('''<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>五常楽急 原譜読解プレビュー</title>
<style>body{max-width:48rem;margin:2rem auto;padding:0 1rem;font:18px system-ui}audio{width:100%}p{line-height:1.6}</style>
<h1>平調・五常楽急 — 原譜読解プレビュー</h1>
<p>1932年譜の冒頭5拍点を三管で音声化した読解候補。音域・装飾・拍内配置は未検証を含みます。
笙の手移りと息づかいは未実装。途中で終わる抜粋で、止手・正式な終了ではありません。製品試聴Uの対象外です。</p>
<h2>三管合奏（30秒）</h2><audio controls src="ensemble.wav"></audio>
<h2>笙</h2><audio controls src="sho.wav"></audio>
<h2>龍笛</h2><audio controls src="ryuteki.wav"></audio>
<h2>篳篥</h2><audio controls src="hichiriki.wav"></audio>
<h2>笙・本体32拍点の読解（192秒）</h2><p>未読の合成記号2箇所は各6秒の無音として明示。反復・止手を含む演奏ではありません。</p>
<audio controls src="sho-body-reading.wav"></audio>
<p><a href="events.json">音高・時刻・元譜位置</a> / <a href="manifest.json">検査・hash</a></p></html>''')
    print(json.dumps({'directory': str(directory), 'files': len(files), 'prefix_events': len(events), 'body_gaps': body_gaps}, ensure_ascii=False))


if __name__ == '__main__':
    main()
