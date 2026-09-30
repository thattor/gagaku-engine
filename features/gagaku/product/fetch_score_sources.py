"""Retrieve only the PD images needed for review, checking pinned byte digests."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

from .audio import ROOT

REQUIRED = {'1192407': (7, 14, 15), '1194354': (14, 15), '1192011': (14, 15),
            '855851': (10, 11, 14, 15), '855852': (9, 10, 11, 14),
            '855853': (11, 12, 13, 14, 30)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    inventory = json.loads((ROOT/'score-sources.json').read_text())
    for source in inventory['sources']:
        pid = source['id']
        for canvas in REQUIRED[pid]:
            entry = source['images'][str(canvas)]
            target = args.output_dir/f'{pid}-{canvas}.jpg'
            data = target.read_bytes() if target.exists() else urllib.request.urlopen(entry['url'], timeout=60).read()
            if hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError(f'{target}: source bytes changed; review required, existing file preserved')
            if not target.exists():
                with target.open('xb') as stream:
                    stream.write(data)
            print(f'{pid} canvas {canvas}: SHA256 OK')


if __name__ == '__main__':
    main()
