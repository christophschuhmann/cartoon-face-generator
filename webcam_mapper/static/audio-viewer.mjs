// Camera exists only during audio playback. One low-resolution request at a time.
export class AudioViewer {
  constructor(onPosition,onStatus){
    this.onPosition=onPosition;this.onStatus=onStatus;this.generation=0;this.stream=null;this.timer=null;
    this.video=document.createElement('video');this.video.muted=true;this.video.playsInline=true;
    this.canvas=document.createElement('canvas');this.context=this.canvas.getContext('2d');
  }
  async start(){
    this.stop();const generation=this.generation;this.onStatus('Webcam für Blickkontakt startet …');
    try{
      const stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:384},height:{ideal:288},frameRate:{ideal:8,max:10},facingMode:'user'},audio:false});
      if(generation!==this.generation){stream.getTracks().forEach(t=>t.stop());return;}
      this.stream=stream;this.video.srcObject=stream;await this.video.play();
      if(generation===this.generation)this.loop(generation);
    }catch(error){
      if(generation!==this.generation)return;this.stop();
      this.onStatus(error.name==='NotAllowedError'?'Blickkontakt aus · Kamerazugriff nicht erlaubt.':'Blickkontakt aus · Webcam nicht verfügbar.');
    }
  }
  stop(){
    this.generation++;clearTimeout(this.timer);this.controller?.abort();
    this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;this.video.srcObject=null;
    this.onPosition(null);
  }
  async loop(generation){
    if(generation!==this.generation || !this.stream)return;
    const started=performance.now();
    try{
      const scale=Math.min(1,384/this.video.videoWidth);
      this.canvas.width=Math.round(this.video.videoWidth*scale);this.canvas.height=Math.round(this.video.videoHeight*scale);
      this.context.drawImage(this.video,0,0,this.canvas.width,this.canvas.height);
      const blob=await new Promise(resolve=>this.canvas.toBlob(resolve,'image/jpeg',.75));
      if(generation!==this.generation)return;
      this.controller=new AbortController();const timeout=setTimeout(()=>this.controller?.abort(),4000);
      let response;try{response=await fetch('/api/audio/viewer',{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'},signal:this.controller.signal});}finally{clearTimeout(timeout);}
      const data=await response.json();if(generation!==this.generation)return;
      if(!response.ok)throw Error(data.error);
      this.onPosition(data.tracking?data.position:null);
      this.onStatus(data.tracking?'Blickkontakt aktiv · ich folge deiner Position.':'Kein Gesicht sichtbar · Blick kehrt sanft zur Mitte zurück.');
    }catch(error){if(generation===this.generation){this.onPosition(null);this.onStatus('Blickkontakt wartet auf die Webcam …');}}
    if(generation===this.generation)this.timer=setTimeout(()=>this.loop(generation),Math.max(40,240-(performance.now()-started)));
  }
}
