'use strict';
const assert=require('node:assert/strict'),cp=require('node:child_process'),fs=require('node:fs');
const B=require('./balance-player.js');
const stems={sho:new Int16Array([1000,5,-5,0]),ryuteki:new Int16Array([2000,0,0,0]),hichiriki:new Int16Array([-3000,0,0,0])};
assert.deepEqual([...B.mixPCM(stems,{sho:100,ryuteki:100,hichiriki:100})],[900,-850,4,4,-4,-4,0,0]);
for(const value of [NaN,Infinity,true,1.5,-1,151])assert.throws(()=>B.validateLevels({sho:value,ryuteki:100,hichiriki:100}));
assert.throws(()=>B.validateLevels({sho:0,ryuteki:0,hichiriki:0}));assert.throws(()=>B.validateLevels({sho:100,ryuteki:100,hichiriki:100,unknown:1}));
assert.throws(()=>B.mixPCM({sho:new Int16Array([30000]),ryuteki:new Int16Array([30000]),hichiriki:new Int16Array([30000])},{sho:150,ryuteki:150,hichiriki:150}));
assert.throws(()=>B.mixPCM({sho:new Int16Array([1]),ryuteki:new Int16Array([25699]),hichiriki:new Int16Array([0])},{sho:100,ryuteki:150,hichiriki:0}));
assert.equal(B.approved('sho','0'.repeat(64)),false);
let seed=430;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
const cases=[];for(let i=0;i<1000;i++){const levels={sho:random()%151,ryuteki:random()%151,hichiriki:random()%151};if(!Object.values(levels).some(v=>v))levels.sho=1;const values=Array.from({length:3},()=>Array.from({length:7},()=>random()%16001-8000));cases.push({levels,values});}
const expected=JSON.parse(cp.execFileSync(process.env.PYTHON||'python3',['-c',"import sys,json;from array import array;from features.gagaku.product.three_pipe_balance import mix_pcm;print(json.dumps([list(mix_pcm(dict(zip(('sho','ryuteki','hichiriki'),map(lambda a:array('h',a),v['values']))),v['levels'])[0]) for v in json.load(sys.stdin)]))"],{input:JSON.stringify(cases),encoding:'utf8'}));
for(let i=0;i<cases.length;i++)assert.deepEqual([...B.mixPCM(Object.fromEntries(['sho','ryuteki','hichiriki'].map((n,j)=>[n,new Int16Array(cases[i].values[j])])),cases[i].levels)],expected[i]);
if(process.argv[2]){
 const directory=process.argv[2],manifest=JSON.parse(fs.readFileSync(directory+'/balance-inspection.json'));const source={};
 for(const e of manifest.source_files){const bytes=fs.readFileSync(directory+'/'+e.file);source[e.instrument]=B.stemPCM(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));}
 const wav=Buffer.from(B.wavBytes(B.mixPCM(source,manifest.levels_percent)));
 assert.deepEqual(wav,fs.readFileSync(directory+'/balance-192s.wav'));
 fs.writeFileSync(directory+'/node-parity.json',JSON.stringify({full_192s_wav_byte_identical:true,random_mix_cases:1000})+'\n');
 console.log('Full 192-second browser renderer/CLI WAV byte-identical');
}
console.log('Integer balance/headroom/rejection and 1000 Python/JS PCM cases PASS');
