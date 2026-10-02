'use strict';
const PipeBalance=(()=>{
const NAMES=['sho','ryuteki','hichiriki'],COEFFICIENTS={sho:[70,70],ryuteki:[85,50],hichiriki:[50,85]},FS=48000,FRAMES=192*FS;
const APPROVED={sho:['1de66405c3897d7aa875f37a9881aae80994bb36a4d8483cbfc02d6bc7eefa49'],ryuteki:['86149bac95ec7696d74e7b21d33d51cdfe8692d6d33e013de650148974813c6d','00a8a6db19a3aafa3eedc64daf00cffea449117a17445578b69cdfc391da4c80'],hichiriki:['b9d61c8e22ff9003d94c0743ae4ce9f5c3154a99d3af969924bc9111bb7d6605']};
function approved(name,sha){return APPROVED[name]?.includes(sha)===true;}
function validateLevels(levels){
 if(!levels||typeof levels!=='object'||Array.isArray(levels)||Object.keys(levels).sort().join(',')!=='hichiriki,ryuteki,sho')throw Error('三管の設定が必要です');
 for(const name of NAMES)if(!Number.isInteger(levels[name])||levels[name]<0||levels[name]>150)throw Error('音量は0〜150%の整数です');
 if(!NAMES.some(n=>levels[n]>0))throw Error('少なくとも一管の音量を上げてください');
 return {...levels};
}
function mixPCM(stems,levels){
 levels=validateLevels(levels);
 if(Object.keys(stems).sort().join(',')!=='hichiriki,ryuteki,sho'||!NAMES.every(n=>stems[n] instanceof Int16Array&&stems[n].length===stems.sho.length)||!stems.sho.length)throw Error('三管の同じ長さのPCMが必要です');
 const peaks=NAMES.map(n=>{let peak=0;for(const v of stems[n])peak=Math.max(peak,Math.abs(v));return peak;});
 const bounds=[0,1].map(c=>NAMES.reduce((s,n,i)=>s+peaks[i]*COEFFICIENTS[n][c]*levels[n],0)/10000);
 if(Math.max(...bounds)>=32766.5)throw Error('音量設定が安全な範囲を超えています');
 const result=new Int16Array(stems.sho.length*2),weights=[0,1].map(c=>NAMES.map(n=>COEFFICIENTS[n][c]*levels[n]));
 for(let i=0;i<stems.sho.length;i++)for(let c=0;c<2;c++){
  const numerator=NAMES.reduce((s,n,k)=>s+stems[n][i]*weights[c][k],0);
  result[i*2+c]=(numerator<0?-1:1)*Math.floor((Math.abs(numerator)+5000)/10000);
 }
 return result;
}
function wavBytes(samples){
 if(!(samples instanceof Int16Array)||samples.length%2)throw Error('stereo PCM required');
 const bytes=new Uint8Array(44+samples.length*2),v=new DataView(bytes.buffer),text=(at,s)=>{for(let i=0;i<s.length;i++)bytes[at+i]=s.charCodeAt(i);};
 text(0,'RIFF');v.setUint32(4,36+samples.length*2,true);text(8,'WAVE');text(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,2,true);v.setUint32(24,FS,true);v.setUint32(28,FS*4,true);v.setUint16(32,4,true);v.setUint16(34,16,true);text(36,'data');v.setUint32(40,samples.length*2,true);
 for(let i=0;i<samples.length;i++)v.setInt16(44+i*2,samples[i],true);return bytes;
}
function stemPCM(buffer){
 const v=new DataView(buffer),tag=at=>String.fromCharCode(...new Uint8Array(buffer,at,4));
 if(v.byteLength!==44+FRAMES*2||tag(0)!=='RIFF'||tag(8)!=='WAVE'||tag(12)!=='fmt '||v.getUint32(16,true)!==16||v.getUint16(20,true)!==1||v.getUint16(22,true)!==1||v.getUint32(24,true)!==FS||v.getUint16(34,true)!==16||tag(36)!=='data'||v.getUint32(40,true)!==FRAMES*2)throw Error('候補stemのWAV形式が違います');
 const result=new Int16Array(FRAMES);for(let i=0;i<FRAMES;i++)result[i]=v.getInt16(44+i*2,true);return result;
}
function audioBuffer(context,samples){
 const buffer=context.createBuffer(2,samples.length/2,FS);
 for(let c=0;c<2;c++){const channel=buffer.getChannelData(c);for(let i=0;i<channel.length;i++)channel[i]=samples[i*2+c]/32768;}
 return buffer;
}
return {approved,validateLevels,mixPCM,wavBytes,stemPCM,audioBuffer};
})();
if(typeof module!=='undefined')module.exports=PipeBalance;
