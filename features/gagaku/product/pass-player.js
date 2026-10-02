'use strict';
const PassOperation=(()=>{
const FS=48000, DURATION=192;
function finishPlan(seconds){
 if(!Number.isFinite(seconds)||seconds<0||seconds>DURATION)throw Error('request outside bounded candidate performance');
 const requestFrame=Math.floor(seconds*FS+1e-7),endFrame=(seconds<=95.75?96:192)*FS;
 return {request_frame:requestFrame,end_frame:endFrame,release_start_frame:endFrame-.25*FS,verified_exit:false,tomede:false,kind:'author_body_boundary_release'};
}
class Controller{
 constructor(context,onState=()=>{}){this.context=context;this.onState=onState;this.state='ready';this.log=[];}
 emit(state,entry={}){this.state=state;this.log.push({state,...entry});this.onState(state,this.log);}
 start(buffer){
  if(!['ready','ended'].includes(this.state))throw Error('already playing');
  if(buffer.sampleRate!==FS||buffer.numberOfChannels!==2||buffer.length!==192*FS)throw Error('wrong generated candidate audio');
  this.log=[];this.origin=this.context.currentTime+.08;this.source=this.context.createBufferSource();this.source.buffer=buffer;
  this.gain=this.context.createGain();this.gain.gain.setValueAtTime(1,this.origin);this.source.connect(this.gain);this.gain.connect(this.context.destination);
  this.source.onended=()=>this.emit('ended',{end_frame:this.endFrame,verified_exit:false,tomede:false});
  this.endFrame=192*FS;this.source.start(this.origin);this.source.stop(this.origin+192);
  this.emit('playing',{source_frames:buffer.length,repeat_frame:96*FS,default_end_frame:this.endFrame});
 }
 finish(){
  if(this.state!=='playing')return;
  const elapsed=Math.min(192,Math.max(0,this.context.currentTime-this.origin));const choice=finishPlan(elapsed);this.endFrame=choice.end_frame;
  if(this.endFrame===96*FS){
   this.gain.gain.setValueAtTime(1,this.origin+choice.release_start_frame/FS);
   this.gain.gain.linearRampToValueAtTime(0,this.origin+(this.endFrame-1)/FS);
   this.source.stop(this.origin+this.endFrame/FS);
  }
  this.emit('exit_pending',choice);
 }
}
return {finishPlan,Controller};
})();
if(typeof module!=='undefined')module.exports=PassOperation;
