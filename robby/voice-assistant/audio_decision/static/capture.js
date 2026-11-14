// Browser-only capture. Resample using sample accumulation; never connect mic to speakers.
class Capture extends AudioWorkletProcessor {
  constructor(){super();this.sum=0;this.count=0;this.phase=0;this.packet=[];}
  process(inputs){const a=inputs[0]?.[0];if(!a)return true;for(let i=0;i<a.length;i++){this.sum+=a[i];this.count++;this.phase+=16000;if(this.phase>=sampleRate){this.phase-=sampleRate;this.packet.push(this.sum/this.count);this.sum=0;this.count=0;if(this.packet.length===3200){const out=new Float32Array(this.packet);this.port.postMessage({samples:out,frame_end:currentFrame+i+1},[out.buffer]);this.packet=[];}}}return true;}
}
registerProcessor('decision-capture',Capture);
