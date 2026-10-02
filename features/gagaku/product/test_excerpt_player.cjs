const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {finishPlan,ExcerptController,CLIP,validateSourceHash} = require('./excerpt-player.js');
assert.throws(()=>validateSourceHash('0'.repeat(64)));
validateSourceHash('f691ef4781bbcbf61faf09e22d03c822c9e46132d38cadcbc3082bc4d88b8170');
global.setInterval = () => 1; global.clearInterval = () => {};
function fixture() {
  const nodes = [];
  const context = {currentTime:0,destination:{},createBufferSource() {
    const n = {connect(){},disconnect(){},start(t){this.startTime=t;},stop(){this.stopped=true;}};nodes.push(n);return n;
  },createGain() {return {connect(){},disconnect(){},gain:{events:[],setValueAtTime(v,t){this.events.push(['set',v,t]);},linearRampToValueAtTime(v,t){this.events.push(['ramp',v,t]);},cancelScheduledValues(t){this.events=this.events.filter(e=>e[2]<t);}}};}};
  const buffer={sampleRate:48000,length:CLIP,numberOfChannels:2,getChannelData(){return new Float32Array(CLIP);}};
  return {context,nodes,controller:new ExcerptController(context,buffer)};
}
// Requests just before a stitch must cancel a queued, not-started clip.
{
  const {context,nodes,controller:c}=fixture();c.start();context.currentTime=c.origin+23.5;c.pump();
  assert.equal(nodes.length,2);const plan=c.requestFinish();assert.equal(plan.cycles,1);assert.equal(nodes[1].stopped,true);
  assert.equal(c.phase,'finish_pending');assert.equal(c.requestFinish(),plan);
  context.currentTime=c.origin+24;c.pump();assert.equal(c.phase,'ended');
  assert.equal(c.log.at(-1).verifiedMusicalExit,false);assert.equal(c.log.at(-1).tomede,false);
}
{
  const {context,nodes,controller:c}=fixture();c.start();context.currentTime=c.origin+23.6-.25/48000;c.pump();
  assert.equal(c.requestFinish().cycles,1);assert.equal(nodes[1].stopped,true);
}
// A request during overlap finishes the active second clip without a third.
{
  const {context,nodes,controller:c}=fixture();c.start();context.currentTime=c.origin+23.7;c.pump();
  assert.equal(c.requestFinish().endFrame,47.6*48000);assert.equal(c.finish.cycles,2);
  context.currentTime=c.origin+47.6;c.pump();assert.equal(c.phase,'ended');assert.equal(nodes.length,2);
}
{
  const {context,controller:c}=fixture();c.start();
  for(let i=1;i<=25;i++){context.currentTime=c.origin+i*23.6;c.pump();}
  context.currentTime=c.origin+600;c.pump();assert.equal(c.phase,'finish_pending');assert.equal(c.finish.endFrame,614*48000);
}
// Timer lookahead and automatic 10-minute request use the same integer-frame contract.
const python=process.env.GAGAKU_PYTHON || 'python3';
const rows=JSON.parse(execFileSync(python,['-c','import json;from features.gagaku.product.excerpt_operation import request_checks;print(json.dumps(request_checks()))'],{encoding:'utf8'}));
for(const row of rows){const p=finishPlan(row.request_seconds);assert.equal(p.cycles,row.cycles);assert.equal(p.endFrame,row.end_frame);}
for(const x of [-1,NaN,Infinity,601])assert.throws(()=>finishPlan(x));
console.log('Browser scheduler: lookahead cancellation, overlap exit, state log and 1083 Python/JS plans PASS');
