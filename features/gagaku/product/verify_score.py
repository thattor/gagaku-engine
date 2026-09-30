"""Verify delivered preview bytes/coverage, without certifying score interpretation."""
from array import array
import json
from pathlib import Path
import sys
import wave

from .audio import digest, save_json


def verify(directory):
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    if manifest['source_fixture_sha256'] != digest(directory/'score-fixture.json'):
        raise ValueError('fixture digest mismatch')
    for field, filename in (('source_inventory_sha256', 'score-sources.json'), ('rights_sha256', 'rights.json')):
        if manifest[field] != digest(directory/filename):
            raise ValueError('source/rights digest mismatch')
    results = []
    for entry in manifest['files']:
        path = directory/entry['file']
        if digest(path) != entry['sha256']:
            raise ValueError('audio digest mismatch')
        with wave.open(str(path)) as wav:
            if (wav.getnframes(), wav.getnchannels(), wav.getframerate(), wav.getsampwidth()) != (
                    entry['frames'], entry['channels'], 48000, 2):
                raise ValueError('WAV contract mismatch')
            samples = array('h', wav.readframes(wav.getnframes()))
        if sys.byteorder != 'little':
            samples.byteswap()
        if not any(samples) or max(abs(x) for x in samples) >= 32767:
            raise ValueError('silent or clipped artifact')
        results.append({'file': path.name, 'peak_pcm': max(abs(x) for x in samples), 'sha256': entry['sha256']})
    events = json.loads((directory/'events.json').read_text())
    fixture = json.loads((directory/'score-fixture.json').read_text())
    source = {c['id']: c for c in fixture['cells']}
    for group in ('prefix', 'sho_body'):
        ids = [e['id'] for e in events[group]]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate realization')
        for event in events[group]:
            cell = source[event['cell_id']]
            if event['source'] != cell['source'] or event['midi'] not in cell['midi']:
                raise ValueError('untraced event')
        selected = [c for c in fixture['cells'] if (c['id'].startswith('sho.') if group == 'sho_body' else
                    '.L1.' in c['id'] and int(c['id'].split('.P')[1]) <= manifest['prefix_cells'])]
        expected = {f"{c['id']}.N{j+1}" for c in selected
                    if c['notation_status'] == 'verified' and c['pitch_status'] != 'unresolved'
                    for j in range(len(c.get('midi') or []))}
        if set(ids) != expected:
            raise ValueError('missing or extra realization')
    if len(events['prefix']) != manifest['events']:
        raise ValueError('coverage count mismatch')
    result = {'engineering_checks': 'PASS', 'musical_acceptance': 'UNVERIFIED',
              'product_E': 'BLOCKED', 'user_listening': 'UNEVALUATED', 'files': results,
              'prefix_rendered_events': len(events['prefix']), 'explicit_unknown_gaps': events['gaps']}
    save_json(directory/'inspection.json', result)
    return result


if __name__ == '__main__':
    print(json.dumps(verify(sys.argv[1]), ensure_ascii=False))
