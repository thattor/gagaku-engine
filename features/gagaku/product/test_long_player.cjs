'use strict';
const assert=require('node:assert/strict'),cp=require('node:child_process');const {Controller,finishPlan}=require('./long-player.js');
const values=[0,95.75,95.75-1/48000,95.75+1/48000,95.75-.25/48000,95.75+.25/48000,95.75-.75/48000,95.75+.75/48000,96,191.75,192,287.75,288,383.75,384];for(const d of [95.75,191.75,287.75,383.75])for(const offset of [-1,-.75,-.25,0,.25,.75,1])values.push(d+offset/48000);let seed=430;for(let i=0;i<1000;i++){seed=(Math.imul(seed,1664525)+1013904223)>>>0;values.push(seed/4294967296*384);}
const python=cp.execFileSync(process.env.PYTHON||'python3',['-c','import json,sys;from features.gagaku.product.three_pipe_long import finish_plan;print(json.dumps([finish_plan(t) for t in json.load(sys.stdin)]))'],{input:JSON.stringify(values),encoding:'utf8'});assert.deepEqual(values.map(finishPlan),JSON.parse(python));
function fake(){const calls=[];const ctx={currentTime:0,destination:{},createGain:()=>({gain:{setValueAtTime:(...x)=>calls.push(['set',...x]),linearRampToValueAtTime:(...x)=>calls.push(['ramp',...x])},connect:()=>{}}),createBufferSource:()=>({connect:()=>{},start:(t)=>calls.push(['start',t]),stop:(t)=>calls.push(['stop',t])})};return {ctx,calls};}
for(const origin of [0,1234,100000])for(const t of [0,1,95.6,95.65,95.75,96,191.6,192,287.6,288,383.9]){
 const {ctx,calls}=fake();ctx.currentTime=origin;const c=new Controller(ctx);c.start({sampleRate:48000,numberOfChannels:2,length:384*48000});
 ctx.currentTime=c.origin+t;const elapsed=ctx.currentTime-c.origin;const choice=finishPlan(Math.min(384,elapsed+.1));c.finish();assert.equal(c.endFrame,choice.end_frame);assert.equal(c.state,'exit_pending');
 if(c.endFrame<384*48000){assert.deepEqual(calls.slice(-3),[['set',1,c.origin+choice.release_start_frame/48000],['ramp',0,c.origin+(c.endFrame-1)/48000],['stop',c.origin+c.endFrame/48000]]);assert.ok(c.origin+choice.release_start_frame/48000>=ctx.currentTime+.1-1e-8);}
 const count=calls.length;c.finish();assert.equal(calls.length,count);assert.throws(()=>c.start({sampleRate:48000,numberOfChannels:2,length:384*48000}));
 c.source.onended();assert.equal(c.state,'ended');c.start({sampleRate:48000,numberOfChannels:2,length:384*48000});assert.equal(c.state,'playing');
}
for(const t of [-.04,384,385]){const {ctx}=fake(),c=new Controller(ctx);c.start({sampleRate:48000,numberOfChannels:2,length:384*48000});ctx.currentTime=c.origin+t;c.finish();assert.equal(c.state,t>=384?'playing':'exit_pending');}
for(const buffer of [{sampleRate:44100,numberOfChannels:2,length:384*48000},{sampleRate:48000,numberOfChannels:1,length:384*48000},{sampleRate:48000,numberOfChannels:2,length:1}])assert.throws(()=>new Controller(fake().ctx).start(buffer));
console.log(`Long controller and ${values.length} Python/JS exit decisions PASS`);
