'use strict';
const LongOperation=(()=>{
const FS=48000, DURATION=384, LOOKAHEAD=.1;
function finishPlan(seconds){
 if(!Number.isFinite(seconds)||seconds<0||seconds>DURATION)throw Error('request outside bounded candidate performance');
 const requestFrame=Math.floor(seconds*FS),endFrame=(([96,192,288,384].find(t=>seconds<=t-.25)??384))*FS;
 return {request_seconds:seconds,full_release_after_request:seconds<=endFrame/FS-.25,request_status:seconds<=endFrame/FS-.25?"candidate_release_scheduled":"bounded_terminal_completion_release_already_scheduled",request_frame:requestFrame,end_frame:endFrame,release_start_frame:endFrame-.25*FS,verified_exit:false,tomede:false,kind:'author_body_boundary_release'};
}
class Controller{
 constructor(context,onState=()=>{}){this.context=context;this.onState=onState;this.state='ready';this.log=[];}
 emit(state,entry={}){this.state=state;this.log.push({state,...entry});this.onState(state,this.log);}
 start(buffer){
  if(!['ready','ended'].includes(this.state))throw Error('already playing');
  if(buffer.sampleRate!==FS||buffer.numberOfChannels!==2||buffer.length!==384*FS)throw Error('wrong generated candidate audio');
  this.log=[];this.origin=this.context.currentTime+.08;this.source=this.context.createBufferSource();this.source.buffer=buffer;
  this.gain=this.context.createGain();this.gain.gain.setValueAtTime(1,this.origin);this.source.connect(this.gain);this.gain.connect(this.context.destination);
  this.source.onended=()=>{this.source.disconnect?.();this.gain.disconnect?.();this.emit('ended',{end_frame:this.endFrame,verified_exit:false,tomede:false});};
  this.endFrame=384*FS;this.source.start(this.origin);this.source.stop(this.origin+384);
  this.emit('playing',{source_frames:buffer.length,repeat_frames:[96,192,288].map(t=>t*FS),default_end_frame:this.endFrame,origin:this.origin,base_latency:this.context.baseLatency??null,output_latency:this.context.outputLatency??null,terminal_release:"embedded_voice_envelopes"});
 }
 canCancelFinish(){
  return this.state==='exit_pending'&&this.context.currentTime<this.origin+this.endFrame/FS-.25-LOOKAHEAD;
 }
 cancelFinish(){
  if(this.state!=='exit_pending')return false;
  const now=this.context.currentTime,previousEndFrame=this.endFrame;
  const entry={operation:'cancel_finish',previous_end_frame:previousEndFrame,context_time:now,origin:this.origin,cancel_deadline_seconds:previousEndFrame/FS-.25-LOOKAHEAD,scheduling_lookahead_seconds:LOOKAHEAD,clock:'audio_context_render_time',verified_exit:false,tomede:false};
  if(!this.canCancelFinish()){this.emit('exit_pending',{...entry,cancel_status:'rejected_release_too_close_or_started'});return false;}
  if(previousEndFrame<DURATION*FS){
   this.gain.gain.cancelScheduledValues(now);
   this.gain.gain.setValueAtTime(1,now);
   this.source.stop(this.origin+DURATION);
  }
  this.endFrame=DURATION*FS;
  this.emit('playing',{...entry,cancel_status:'cancelled',end_frame:this.endFrame,terminal_release:'embedded_voice_envelopes'});
  return true;
 }
 finish(){
  if(this.state!=='playing')return;
  const elapsed=Math.min(384,Math.max(0,this.context.currentTime-this.origin));if(elapsed>=384)return;const choice=finishPlan(Math.min(384,elapsed+LOOKAHEAD));this.endFrame=choice.end_frame;
  if(this.endFrame<384*FS){
   this.gain.gain.setValueAtTime(1,this.origin+choice.release_start_frame/FS);
   this.gain.gain.linearRampToValueAtTime(0,this.origin+(this.endFrame-1)/FS);
   this.source.stop(this.origin+this.endFrame/FS);
  }
  this.emit('exit_pending',{...choice,actual_request_seconds:elapsed,context_time:this.context.currentTime,origin:this.origin,scheduling_lookahead_seconds:LOOKAHEAD,clock:'audio_context_render_time',terminal_release:this.endFrame===384*FS?'embedded_voice_envelopes':'scheduled_gain_ramp',base_latency:this.context.baseLatency??null,output_latency:this.context.outputLatency??null});
 }
}
return {finishPlan,Controller};
})();
if(typeof module!=='undefined')module.exports=LongOperation;
