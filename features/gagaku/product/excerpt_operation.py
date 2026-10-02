"""Real-audio audition loops; artificial excerpt exits, never product E."""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
import wave

from .audio import ROOT, digest, save_json, write_wav
from .models import FS
from .three_pipe_line1 import generate as generate_source

CLIP_FRAMES=24*FS
OVERLAP_FRAMES=round(.4*FS)
STRIDE_FRAMES=CLIP_FRAMES-OVERLAP_FRAMES
MAX_SECONDS=600


def finish_plan(request_seconds):
    if type(request_seconds) not in (int,float) or not math.isfinite(request_seconds) or not 0<=request_seconds<=MAX_SECONDS:
        raise ValueError('request must be finite in 0..600 seconds')
    request_frame=math.floor(request_seconds*FS+1e-7)
    cycles=request_frame//STRIDE_FRAMES+1
    end_frame=(cycles-1)*STRIDE_FRAMES+CLIP_FRAMES
    return {'request_seconds':request_seconds,'request_frame':request_frame,'cycles':cycles,
            'stride_frames':STRIDE_FRAMES,'overlap_frames':OVERLAP_FRAMES,'end_frame':end_frame,
            'end_seconds':end_frame/FS,'wait_seconds':(end_frame-request_frame)/FS,
            'exit_kind':'author_excerpt_fade','verified_musical_exit':False,'tomede':False,
            'states':['playing','finish_pending','ended']}


def read_pcm(path,channels):
    with wave.open(str(path)) as wav:
        if (wav.getframerate(),wav.getnframes(),wav.getnchannels(),wav.getsampwidth())!=(FS,CLIP_FRAMES,channels,2):
            raise ValueError('source PCM format changed')
        data=array('h',wav.readframes(CLIP_FRAMES))
    if sys.byteorder!='little':data.byteswap()
    if max(map(abs,data))>=32767:raise ValueError('source PCM clipped')
    return array('f',(x/32768 for x in data))


def chunks(source,channels,cycles):
    """Overlap PCM audition clips, matching the browser's linear gain schedule."""
    if type(cycles) is not int or cycles<1 or len(source)!=CLIP_FRAMES*channels:
        raise ValueError('invalid cycle count or source shape')
    overlap=OVERLAP_FRAMES*channels
    stride=STRIDE_FRAMES*channels
    for cycle in range(cycles):
        if cycle==0:
            yield source[:stride] if cycles>1 else source
        else:
            # Last .4s of previous clip and first .4s of current clip overlap.
            join=array('f')
            for i in range(overlap):
                frame=i//channels
                gain=frame/OVERLAP_FRAMES
                join.append(source[stride+i]*(1-gain)+source[i]*gain)
            yield join
            yield source[overlap:stride] if cycle<cycles-1 else source[overlap:]


def inspection(path,channels,control):
    peak=0;clipped=0;step=0;previous=[0]*channels;frames=0;minimum_rms=1
    sumsq=0;count=0;window=FS//10*channels;first=None;last=None
    boundary_peaks={str(i):0 for i in range(1,control['cycles'])}
    with wave.open(str(path)) as wav:
        if (wav.getframerate(),wav.getnchannels(),wav.getsampwidth(),wav.getnframes())!=(FS,channels,2,control['end_frame']):
            raise ValueError('wrong operational WAV shape')
        while True:
            data=array('h',wav.readframes(FS))
            if not data:break
            if sys.byteorder!='little':data.byteswap()
            if first is None:first=list(data[:channels])
            for index,x in enumerate(data):
                channel=index%channels
                delta=abs(x-previous[channel])/32767
                peak=max(peak,abs(x)/32767);clipped+=abs(x)>=32767;step=max(step,delta)
                previous[channel]=x
                frame=frames+index//channels
                # Track +/- one sample at exact stitch boundaries.
                cycle=round(frame/STRIDE_FRAMES)
                if 1<=cycle<control['cycles'] and abs(frame-cycle*STRIDE_FRAMES)<=1:
                    boundary_peaks[str(cycle)]=max(boundary_peaks[str(cycle)],delta)
                sumsq+=(x/32767)**2;count+=1
                if count==window:
                    if frame>=FS//10 and frame<control['end_frame']-FS//10:
                        minimum_rms=min(minimum_rms,math.sqrt(sumsq/count))
                    sumsq=0;count=0
            frames+=len(data)//channels
            last=list(data[-channels:])
    if clipped or peak>.9 or step>.4 or minimum_rms<1e-6 or any(first+last):
        raise ValueError('PCM clipping, gap, discontinuity bound or edge failure')
    return {'frames':frames,'channels':channels,'peak':peak,'full_scale_count':clipped,
            'nonfinite_count':0,'max_channel_sample_step':step,'minimum_interior_100ms_rms':minimum_rms,
            'boundary_sample_steps':boundary_peaks,'first_pcm_samples':first,'last_pcm_samples':last,
            'classification':'author engineering checks; does not certify naturalness'}


def request_checks():
    rng=random.Random(430)
    requests=[rng.uniform(0,MAX_SECONDS) for _ in range(1000)]
    requests += [0,STRIDE_FRAMES/FS-1/FS,STRIDE_FRAMES/FS,STRIDE_FRAMES/FS+1/FS,STRIDE_FRAMES/FS-.25/FS,24,300,600]
    requests += [i*STRIDE_FRAMES/FS+delta/FS for i in range(1,26) for delta in (-.25,0,.25)]
    rows=[finish_plan(t) for t in requests]
    for row in rows:
        assert row['request_frame']<=row['end_frame']
        assert 0<=row['end_frame']-row['request_frame']<=CLIP_FRAMES
        assert (row['cycles']-1)*STRIDE_FRAMES<=row['request_frame']<row['cycles']*STRIDE_FRAMES
        assert row['end_frame']==(row['cycles']-1)*STRIDE_FRAMES+CLIP_FRAMES
    return rows


def generate(directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    source=out/'source';generate_source(source)
    source_report=json.loads((source/'three-pipe-line1-inspection-v1.json').read_text())
    controls={'early':finish_plan(7),'overlap':finish_plan(23.7),'five-minute':finish_plan(300)}
    files=[];checks={}
    for label,control in controls.items():
        names=('ensemble','sho','ryuteki','hichiriki') if label=='five-minute' else ('ensemble',)
        for name in names:
            channels=2 if name=='ensemble' else 1
            original=read_pcm(source/f'three-pipe-line1-{name}-24s.wav',channels)
            entry=write_wav(out/f'excerpt-{label}-{name}.wav',channels,chunks(original,channels,control['cycles']))
            # Independent second assembly checks the exact PCM stream, avoiding another long WAV on disk.
            h=hashlib.sha256()
            from .audio import pcm
            with wave.open(str(out/entry['file'])) as wav:
                pcm_hash=hashlib.sha256(wav.readframes(wav.getnframes())).hexdigest()
            for chunk in chunks(read_pcm(source/f'three-pipe-line1-{name}-24s.wav',channels),channels,control['cycles']):
                h.update(pcm(chunk))
            if h.hexdigest()!=pcm_hash:raise ValueError('operational PCM regeneration differs')
            entry['pcm_sha256']=pcm_hash;files.append(entry)
            checks[entry['file']]=inspection(out/entry['file'],channels,control)
    save_json(out/'request-checks.json',request_checks())
    for name in ('excerpt-player.html','excerpt-player.js'):
        shutil.copyfile(ROOT/name,out/name)
    inputs=[Path(__file__),ROOT/'excerpt-player.js',ROOT/'excerpt-player.html',
            ROOT.parents[2]/'docs/tasks/excerpt-operation-v1/README.md',ROOT/'three_pipe_line1.py',ROOT/'three_pipe_prefix.py',ROOT/'score-sources.json',ROOT/'rights.json',ROOT.parents[2]/'docs/PRODUCT_GOAL_V1.md']
    report={'version':'excerpt-operation-v1','source_commit':subprocess.check_output(['git','-C',str(ROOT.parents[2]),'rev-parse','HEAD'],text=True).strip(),
            'scope':'first-line audition loop with finish requests; NOT full-song or verified musical repeat/exit',
            'source_inspection':source_report,'source_hashes':{str(p.relative_to(ROOT.parents[2])):digest(p) for p in inputs},
            'controls':controls,'files':files,'pcm_checks':checks,'random_request_count':1000,'edge_request_count':83,
            'independent_source_bank_and_operation_regeneration':True,
            'source_page_audit':{'registry':'features/gagaku/product/score-sources.json','verified_image_count':20,'looked_at':['1194354 canvas15 right p18','1192011 canvas15 right p18'],'performance_verified':False},
            'missing_melody_cells':[f'{name}.L{line}.P{point}' for name in ('ryuteki','hichiriki') for line in range(2,5) for point in range(1,9)],
            'product_E':'BLOCKED; excerpt operation must not substitute verified exit and tomede',
            'strict_reading_status':'BLOCKED_PUBLIC_EVIDENCE','performance_verified':False,'user_acceptance':'UNEVALUATED',
            'rights':'own physics only; no reference recording or new measurement',
            'runtime':sys.version}
    save_json(out/'excerpt-operation-inspection.json',report)
    print(json.dumps({'scope':report['scope'],'files':len(files),'request_checks':1083},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',required=True,type=Path)
    generate(parser.parse_args().output_dir)
