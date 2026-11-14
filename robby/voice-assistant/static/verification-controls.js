// Persist only quality/latency choices, never keys, microphone data or identities.
export class VerificationControls {
 constructor(client){
  this.client=client;this.values={verify_tts:true,verify_input:true,serial_tts:false};
  try{const s=JSON.parse(localStorage.getItem('robby.verification')||'{}');for(const k of Object.keys(this.values))if(typeof s[k]==='boolean')this.values[k]=s[k];}catch{}
  this.panel=document.createElement('details');this.panel.id='verification-controls';this.panel.className='settings option-menu';
  this.panel.innerHTML=`<summary>Speed &amp; verification · choose which checks run</summary>
   <p>These choices apply to your next turn. Defaults keep both checks on. Input isolation, speaker admission, the speech-pause timer and Stop handling remain separate.</p>
   <label><input type="checkbox" id="verify-input"> Use the selected second ASR recognizer after a speech pause</label>
   <p>On: Parakeet/your selected ASR refines the full utterance; speculative work is reused. Off: use the existing Nemotron transcript pass only. This can save recognizer work but may reduce German transcription quality, including recognition of “Hey Robby”. It does not submit mid-sentence or bypass speaker matching.</p>
   <label><input type="checkbox" id="verify-tts"> Check generated speech before playback (recommended)</label>
   <p>On: a parallel ASR worker waits for the opening target words and cuts/fades the ending. Off: stream raw TTS earlier; unwanted lead-in, wrong words or trailing mumbling can be heard. This changes audio quality, not the LLM's factual accuracy.</p>
   <label><input type="checkbox" id="verify-serial"> Use the older serial TTS check (comparison only)</label>
   <p>Unchecked uses the faster parallel checker. Serial checks pause generation and usually add latency. The optional quick-reply batch engine uses its own checker; this comparison only affects the normal sentence stream. Pre-generated interruption acknowledgments are reused.</p>
   <p>Other costs: Voice tone hints run Humaneness Ears; Voice isolation filters microphone audio; quick reactions add a small LLM/TTS stage. Their existing switches are in the menus above. The timing cards show actual per-turn measurements, not fixed estimates.</p>
   <p id="verification-status" role="status"></p>`;
  document.querySelector('aside').append(this.panel);
  for(const [key,id] of Object.entries({verify_input:'verify-input',verify_tts:'verify-tts',serial_tts:'verify-serial'})){
   const input=this.panel.querySelector('#'+id);input.checked=this.values[key];input.onchange=()=>{this.values[key]=input.checked;try{localStorage.setItem('robby.verification',JSON.stringify(this.values));}catch{}this.send();this.status('Saved for the next turn.');};
  }
  this.status('Saved locally; applied when connected.');
 }
 send(){this.client.send('verification:'+JSON.stringify(this.values));}
 status(text){this.panel.querySelector('#verify-serial').disabled=!this.values.verify_tts;this.panel.querySelector('#verification-status').textContent=text+(this.values.verify_tts?'':' Raw TTS playback is enabled.');}
 message(m){if(m.type==='ready')this.send();if(m.type==='verification_settings')this.status('Server confirmed your settings.');}
}
