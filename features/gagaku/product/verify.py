"""Verify delivered PCM, physical raw, source hashes and real-audio joins."""
from array import array
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import wave

from .audio import FS, INSTRUMENTS, digest, inspect, save_json


def wav_payload(path):
    with wave.open(str(path),'rb') as wav:
        return wav.readframes(wav.getnframes())


def verify(directory):
    manifest=json.loads((directory/'manifest.json').read_text())
    errors=[]
    checks=[]
    for source,expected in manifest['source_files'].items():
        if digest(source)!=expected: errors.append(f'source hash mismatch: {source}')
    for entry in manifest['artifacts']:
        path=directory/entry['file']
        if digest(path)!=entry['sha256']: errors.append(f'artifact hash mismatch: {path.name}')
        clipping=sounding=frames=0
        with wave.open(str(path)) as wav:
            if (wav.getframerate()!=FS or wav.getsampwidth()!=2 or wav.getnframes()!=entry['frames']):
                errors.append(f'PCM format mismatch: {path.name}')
            channels=wav.getnchannels()
            first=last=None
            while data:=wav.readframes(FS):
                values=array('h');values.frombytes(data)
                if sys.byteorder!='little':values.byteswap()
                clipping+=sum(abs(x)>=32767 for x in values)
                sounding+=sum(x!=0 for x in values)
                frames+=len(values)//channels
                first=values[:channels] if first is None else first
                last=values[-channels:]
        if not sounding or clipping:errors.append(f'silent/clipped artifact: {path.name}')
        if any(first) or any(last):errors.append(f'nonzero endpoint: {path.name}')
        checks.append({'file':path.name,'frames':frames,'clipping_samples':clipping,'nonzero_samples':sounding})
    for name,entry in manifest['bank'].items():
        path=directory/'bank'/entry['raw']
        if digest(path)!=entry['raw_sha256']:errors.append(f'raw hash mismatch: {name}')
        raw=array('d');raw.frombytes(gzip.decompress(path.read_bytes()))
        if sys.byteorder!='little':raw.byteswap()
        inspect(raw)
        reference = entry['listening_reference']
        if digest(directory/'bank'/reference['file']) != reference['sha256']:
            errors.append(f'bank listening reference hash mismatch: {name}')
    # Each long WAV's byte stream must equal the exact scheduled rendered blocks.
    # This detects omission, duplication, reordering and a hard cut before ending.
    join_checks=[]
    for seconds in (300,600,1200):
        control_path=directory/f'diagnostic-{seconds}s.control.json'
        if not control_path.exists():continue
        control=json.loads(control_path.read_text())
        names=['ending' if item.get('ending') else f"{item['variant']}-{item['line']}" for item in control['timeline']]
        with wave.open(str(directory/f'diagnostic-{seconds}s.wav')) as wav:
            for name in names:
                expected=wav_payload(directory/f'{name}.wav')
                actual=wav.readframes(len(expected)//4)
                if actual!=expected:errors.append(f'long schedule byte mismatch: {seconds}/{name}')
            if wav.readframes(1):errors.append(f'extra frames: {seconds}')
            if wav.getnframes()!=round(control['end_seconds']*FS):errors.append(f'duration mismatch: {seconds}')
        if control['ended_phase']!='ended' or control['timeline'][-2]['line']!=3:
            errors.append(f'exit schedule error: {seconds}')
        join_checks.append({'request_seconds':seconds,'end_seconds':control['end_seconds'],
                            'audio_block_sequence_byte_equal':True,'scope':'diagnostic_only'})
    requests=json.loads((directory/'finish-requests.json').read_text())
    if requests['count']<1000:errors.append('fewer than 1000 requests')
    for result in requests['results']:
        if (result['ended_phase']!='ended' or result['end_seconds']-6<result['request_seconds']
            or result['timeline'][-2]['line']!=3 or not result['timeline'][-1].get('ending')):
            errors.append('request scheduling failure')
    result={'version':'diagnostic-inspection-v1','manifest_sha256':digest(directory/'manifest.json'),
            'scope':'diagnostic_only','status':'PASS' if not errors else 'FAIL','errors':errors,
            'wav_checks':checks,'long_audio_connections':join_checks,'symbolic_requests':requests['count'],
            'limits':['PCM endpoint/byte checks detect implementation discontinuities and schedule errors; not perceived naturalness',
                      '1000 requests are scheduler tests, not 1000 full real-audio E2E runs',
                      'Goshouraku-kyu score, exit and tomede remain unverified; product M/E are blocked']}
    save_json(directory/'inspection.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    args=parser.parse_args();result=verify(args.directory)
    print(json.dumps({'status':result['status'],'errors':result['errors'],'wav_count':len(result['wav_checks'])}))
    raise SystemExit(bool(result['errors']))

if __name__=='__main__':main()
