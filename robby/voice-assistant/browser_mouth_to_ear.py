"""Mouth-to-ear latency in a real browser: synthetic microphone -> Robby -> scheduled playback.

Chromium (Playwright) gets a WAV file as its microphone: 3 s silence, a German "Hey Robby ..."
request in a different voice than Robby's, then silence. Everything is timed with the page's
own clock (performance.now):

  speech end   last loud microphone block before >= 700 ms of silence (AnalyserNode tap on
               the captured stream), so short pauses inside the sentence don't count
  first sound  when the first Robby reply buffer is scheduled to play (AudioContext time
               mapped to performance.now); the device's own output latency is excluded

It also records server messages (asr_sentence, endpoint, pipeline_metrics) for a breakdown and
the client's underflow counters (gaps after playback started).

Robby allows one live session per server. Close other Robby tabs, or start a separate test
instance (ROBO_PORT=8893 ROBO_MOUTH_PORT=8895 ROBO_MEMORY_DIR=/tmp/robby-test python server.py).
Runs are serialized and wait until the shared TTS server is idle.

    python browser_mouth_to_ear.py                                   # live server, 3 x 2 runs
    python browser_mouth_to_ear.py --config "a|http://127.0.0.1:8893|" \\
        --config "b|http://127.0.0.1:8893|160" --runs 4              # interleaved A/B, b = 160 ms start buffer

Requires: pip install playwright && python -m playwright install chromium
"""
import argparse,asyncio,io,json,statistics
from pathlib import Path
import httpx,numpy as np,soundfile as sf
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
FIXTURES=ROOT/'logs/mouth-to-ear'
TEXTS=['Hey Robby, wie geht es dir heute?','Hey Robby, was ist dein Lieblingsessen?','Hey Robby, erzähl mir einen kurzen Witz.']
TTS='http://127.0.0.1:8792'

INIT=r"""
window.m2e={plays:[],msgs:[],loud:[]};
const gum=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
navigator.mediaDevices.getUserMedia=async c=>{const s=await gum(c);
  try{const ctx=new AudioContext();const an=ctx.createAnalyser();an.fftSize=256;ctx.createMediaStreamSource(s).connect(an);
    const buf=new Float32Array(an.fftSize);
    setInterval(()=>{an.getFloatTimeDomainData(buf);let e=0;for(const v of buf)e+=v*v;
      if(Math.sqrt(e/buf.length)>0.01){const t=performance.now(),l=m2e.loud;if(!l.length||t-l[l.length-1]>20)l.push(t);else l[l.length-1]=t;}},4);}catch(e){m2e.err=String(e);}
  return s;};
const start=AudioBufferSourceNode.prototype.start;
AudioBufferSourceNode.prototype.start=function(when,...rest){
  if(this.roboId)m2e.plays.push({id:this.roboId,dur:this.buffer.duration,at:performance.now(),
    audible:performance.now()+Math.max(0,(when||0)-this.context.currentTime)*1000});
  return start.call(this,when,...rest);};
localStorage.setItem('robby.cameraAuto','false');localStorage.setItem('robby.cameraAutoVersion','3');
localStorage.setItem('robby.avatar-idle-enabled','false');localStorage.setItem('robby.avatar-pet-invites-enabled','false');
"""

def fixtures():
    """Authored synthetic requests in the 'Idris' voice (not Robby's 'Mira'); made once."""
    FIXTURES.mkdir(parents=True,exist_ok=True);paths=[]
    with httpx.Client(base_url=TTS,timeout=300) as client:
        for index,text in enumerate(TEXTS):
            path=FIXTURES/f'request-{index}.wav';paths.append(path)
            if path.exists():continue
            body={'model':'small_rl','input_mode':'manual','format':'structured','generation':'single','n':1,
                  'message':'GENERAL: Calm, clear natural conversational German. Preserve the reference speaker.\nSCRIPT:\n'+text,
                  'streaming':False,'seconds':3.5,'temperature':.8,'guidance':2.,'voice_mode':'profile','voice_profile':'anime_088',
                  'voice_conversion':False,'align':True,'seed':4242+index}
            result=None
            with client.stream('POST','/api/turn',json=body) as response:
                for line in response.iter_lines():
                    if line.startswith('data: ') and json.loads(line[6:]).get('event')=='result':result=json.loads(line[6:])
            wave,rate=sf.read(io.BytesIO(client.get(result['candidates'][0]['url']).content),dtype='float32')
            sf.write(path,wave.mean(1) if wave.ndim>1 else wave,rate)
    return paths

async def tts_idle():
    async with httpx.AsyncClient(timeout=10) as client:
        quiet=0
        while quiet<3:
            quiet=0 if (await client.get(TTS+'/api/state')).json().get('busy') else quiet+1
            await asyncio.sleep(1)

async def run_once(playwright,mic,url,reserve):
    await tts_idle()
    browser=await playwright.chromium.launch(headless=True,args=['--no-sandbox','--use-fake-device-for-media-stream',
        '--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+str(mic),'--autoplay-policy=no-user-gesture-required'])
    page=await browser.new_page()
    await page.add_init_script(INIT+(f"localStorage.setItem('robby.startReserveMs','{reserve}');" if reserve else "localStorage.removeItem('robby.startReserveMs');"))
    try:
        await page.goto(url+'/desk-robot/');await page.wait_for_function('window.robo',timeout=60000)
        await page.evaluate('''()=>{const old=robo.on.message;robo.on.message=m=>{
            if(['endpoint','asr_sentence','pipeline_metrics','turn_done'].includes(m.type))
              m2e.msgs.push({type:m.type,at:performance.now(),m:m.type==='pipeline_metrics'?m.metrics:(m.type==='asr_sentence'?{text:m.text,asr:m.asr}:{})});
            old&&old(m)}}''')
        await page.wait_for_function('robo.metrics.reply_chunks>0 && m2e.msgs.some(m=>m.type==="turn_done")',timeout=60000)
        data=await page.evaluate('m2e');metrics=await page.evaluate('robo.metrics')
    finally:await browser.close()
    first=data['plays'][0];loud=[t for t in data['loud'] if t<first['at']]
    speech_end=next((a for a,b in zip(loud,loud[1:]+[first['at']]) if b-a>=700),None)
    if speech_end is None:raise RuntimeError('No speech end before the reply')
    asr=next((m for m in data['msgs'] if m['type']=='asr_sentence'),None)
    server=next((m['m'] for m in data['msgs'] if m['type']=='pipeline_metrics' and m['m'].get('first_audio_ms')),{})
    return {'mouth_to_ear_ms':round(first['audible']-speech_end),
            'speech_end_to_asr_text_ms':round(asr['at']-speech_end) if asr else None,
            'server_first_audio_ms':server.get('first_audio_ms'),'server_llm_first_sentence_ms':server.get('llm_first_sentence_ms'),
            'server_tts_first_audio_ms':server.get('tts_first_audio_ms'),'browser_start_buffer_ms':round(first['audible']-first['at']),
            'underflows':metrics.get('underflows',0),'max_gap_ms':round(metrics.get('max_gap_ms',0)),
            'speculative_asr':bool(((asr or {}).get('m',{}).get('asr') or {}).get('speculative')),'asr':(asr or {}).get('m',{}).get('text')}

async def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config',action='append',help='label|url|start_buffer_ms (empty = client default)')
    parser.add_argument('--runs',type=int,default=2,help='runs per request and config')
    args=parser.parse_args()
    configs=[c.split('|') for c in (args.config or ['live|http://127.0.0.1:8793|'])]
    rows=[]
    async with async_playwright() as playwright:
        for index,path in enumerate(fixtures()):
            wave,rate=sf.read(path,dtype='float32')
            mic=FIXTURES/f'mic-{index}.wav'
            sf.write(mic,np.r_[np.zeros(3*rate),wave,np.zeros(25*rate)].astype(np.float32),rate,subtype='PCM_16')
            for run in range(args.runs):
                for label,url,reserve in (configs if run%2==0 else configs[::-1]):
                    try:row=await run_once(playwright,mic,url,reserve)
                    except Exception as exc:row={'error':str(exc)[:200]}
                    row.update(config=label,request=index);rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    for label,_,_ in configs:
        ok=[r for r in rows if r['config']==label and 'mouth_to_ear_ms' in r]
        if not ok:continue
        keys=[k for k in ok[0] if k.endswith('_ms') and all(isinstance(r.get(k),(int,float)) for r in ok)]
        summary={k:round(statistics.median(r[k] for r in ok)) for k in keys}
        summary.update(runs=len(ok),runs_with_gap=sum(1 for r in ok if r['underflows']),speculative_asr_runs=sum(r['speculative_asr'] for r in ok))
        print('MEDIAN',label,json.dumps(summary))

if __name__=='__main__':asyncio.run(main())
