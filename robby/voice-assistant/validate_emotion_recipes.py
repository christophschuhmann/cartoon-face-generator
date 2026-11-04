"""Authored TTS listening samples: concrete acting recipes, ASR and uncertain delivery captions."""
import base64,io,json,time,subprocess,html
from pathlib import Path
import httpx,numpy as np
from scipy.signal import resample_poly
from bolt_text import Sentence
from rtx3090_quality_check import wer
ROOT=Path(__file__).resolve().parent
TEXT='Das habe ich wirklich nicht erwartet, damit muss ich erst einmal umgehen.'
def main():
 rows=[]
 with httpx.Client(timeout=300) as c:
  for emotion in ['anger','sadness','surprise','elation','fear','affection']:
   spec=Sentence(TEXT,emotion+', intense, natural',language='de').spec()
   body={'model':'small_rl','input_mode':'manual','format':'structured','message':spec['manual_prompt'],'language':'de','generation':'single','n':1,'streaming':True,'stream_transport':'pcm_f32','live_only':True,'chunk_frames':20,'temperature':.8,'guidance':2.,'voice_mode':'profile','voice_profile':'emolia_c1699','voice_conversion':False,'speaker_steering':False,'dynamic_reference':False,'align':True,'seed':777}
   t=time.perf_counter();audio=[];first=None
   with c.stream('POST','http://127.0.0.1:8792/api/turn',json=body) as r:
    r.raise_for_status()
    for line in r.iter_lines():
     if not line.startswith('data: '):continue
     e=json.loads(line[6:])
     if e.get('event')=='error':raise RuntimeError(str(e)[:250])
     if e.get('pcm_f32'):
      audio.append(np.frombuffer(base64.b64decode(e['pcm_f32']),'<f4').copy());first=first if first is not None else time.perf_counter()-t
   generation=time.perf_counter()-t;wave=np.concatenate(audio);assert np.isfinite(wave).all() and np.sqrt(np.mean(wave**2))>.001
   audio16=resample_poly(wave,1,3).astype('<f4');r=c.post('http://127.0.0.1:8798/api/bolt/asr?model=parakeet_v3',content=audio16.tobytes());r.raise_for_status();transcript=r.json()['text']
   r=c.post('http://127.0.0.1:8802/caption',content=audio16.tobytes());caption=r.json() if r.status_code==200 else {'status':'unavailable'}
   mp3=subprocess.run(['ffmpeg','-v','error','-f','f32le','-ar','48000','-ac','1','-i','pipe:0','-b:a','96k','-f','mp3','pipe:1'],input=wave.astype('<f4').tobytes(),capture_output=True,check=True).stdout
   row={'emotion':emotion,'text':TEXT,'general':spec['general'],'first_pcm_s':first,'generation_s':generation,'audio_s':len(wave)/48000,'wer':wer(TEXT,transcript),'transcript':transcript,'uncertain_caption':caption.get('caption',caption.get('status')),'audio_mp3_base64':base64.b64encode(mp3).decode()};rows.append(row);print(json.dumps({k:v for k,v in row.items() if k!='audio_mp3_base64'},ensure_ascii=False),flush=True)
 report={'scope':__doc__,'voice':'Mira, fixed reference','temperature':.8,'cfg':2.,'rows':rows,'limits':'Authored prompt/output probes, not a blinded perceptual test or validated 40-class emotion recognition. Captions are uncertain machine estimates. Rendered poses are checked separately.'}
 (ROOT/'static/stunts-emotions-audio.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
 cards=''.join('<article><h2>'+html.escape(r['emotion'])+'</h2><audio controls preload="none" src="data:audio/mpeg;base64,'+r['audio_mp3_base64']+'"></audio><p>ASR WER: '+str(round(r['wer']*100,1))+'% · '+html.escape(r['transcript'])+'</p><p>Machine delivery impression (uncertain): '+html.escape(r['uncertain_caption'] or 'Unavailable')+'</p><details><summary>Acting direction and timings</summary><p>'+html.escape(r['general'])+'</p><p>First PCM '+str(round(r['first_pcm_s']*1000))+' ms; total generation '+str(round(r['generation_s'],2))+' s.</p></details></article>' for r in rows)
 page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Robby: actions and emotional acting checks</title><style>body{font:17px/1.6 system-ui;max-width:1000px;margin:30px auto;padding:20px;background:#faf9f6;color:#21333b}article{border:1px solid #ccc;border-radius:14px;padding:20px;margin:18px 0}audio{width:100%}a{color:#16718a}</style><h1>Robby: emotional acting samples</h1><p>Measured 4 November 2026. Six authored German samples with the same words, seed, fixed Mira reference, temperature 0.8 and CFG 2. Each uses a concrete performance recipe; speaker identity remains supplied by the reference. Listen and compare: these are not claims that a model recognizes emotions correctly.</p><p>'+html.escape(report['limits'])+'</p>'+cards+'<p><a href="/static/stunts-emotions-browser.json">Typed commands and 40 rendered poses</a> · <a href="/static/stunts-emotions-spoken.json">Synthetic spoken requests</a> · <a href="/desk-robot/">Robby demo</a></p></html>'
 (ROOT/'static/stunts-emotions.html').write_text(page)
if __name__=='__main__':main()
