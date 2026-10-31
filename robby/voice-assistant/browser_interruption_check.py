"""Interrupting Robby while it speaks: does it stop, answer, or keep talking when it should?

Chromium (Playwright) gets a WAV file as its microphone: a story request, then 7 s later
one interruption, both in a different voice than Robby's. The script records whether the
reply's playback was stopped (AudioBufferSourceNode.stop), the server's decision events and
whether a new reply followed. Expected outcomes:

  stop      "Stopp, Robby, hör kurz auf."               -> stop
  moment    "Moment mal, ich habe eine andere Frage."   -> stop (and listen)
  backchan  "Mhm, ja."                                  -> keep talking
  question  "Robby, wie spät ist es eigentlich?"        -> stop and answer

Robby allows one live session per server; use a separate test instance, e.g.
ROBO_PORT=8893 ROBO_MOUTH_PORT=8895 ROBO_MEMORY_DIR=/tmp/robby-test python server.py

    python browser_interruption_check.py --url http://127.0.0.1:8893 --runs 2

Requires: pip install playwright && python -m playwright install chromium
"""
import argparse,asyncio,io,json,time
from pathlib import Path
import httpx,numpy as np,soundfile as sf
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
FIXTURES=ROOT/'logs/interruptions'
TTS='http://127.0.0.1:8792'
REQUEST='Hey Robby, erzähl mir bitte eine lange Geschichte über einen kleinen Drachen.'
CASES={'stop':('Stopp, Robby, hör kurz auf.','stop'),'moment':('Moment mal, ich habe eine andere Frage.','stop'),
       'backchan':('Mhm, ja.','continue'),'question':('Robby, wie spät ist es eigentlich?','answer')}

INIT=r"""
window.bt={loud:[],plays:[],stops:[],msgs:[]};
const gum=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
navigator.mediaDevices.getUserMedia=async c=>{const s=await gum(c);const ctx=new AudioContext();const an=ctx.createAnalyser();an.fftSize=256;
  ctx.createMediaStreamSource(s).connect(an);const b=new Float32Array(256);
  setInterval(()=>{an.getFloatTimeDomainData(b);let e=0;for(const v of b)e+=v*v;
    if(Math.sqrt(e/256)>0.01){const t=performance.now(),l=bt.loud;if(!l.length||t-l[l.length-1]>20)l.push(t);else l[l.length-1]=t;}},4);return s;};
const start=AudioBufferSourceNode.prototype.start,stop=AudioBufferSourceNode.prototype.stop;
AudioBufferSourceNode.prototype.start=function(w,...a){if(this.roboId)bt.plays.push({id:this.roboId,at:performance.now()});return start.call(this,w,...a);};
AudioBufferSourceNode.prototype.stop=function(...a){if(this.roboId)bt.stops.push({id:this.roboId,at:performance.now()});return stop.apply(this,a);};
localStorage.setItem('robby.cameraAuto','false');localStorage.setItem('robby.cameraAutoVersion','3');
localStorage.setItem('robby.avatar-idle-enabled','false');localStorage.setItem('robby.avatar-pet-invites-enabled','false');
"""

def synthesize(client,text,path,seed):
    if path.exists():return
    body={'model':'small_rl','input_mode':'manual','format':'structured','generation':'single','n':1,
          'message':'GENERAL: Clear natural conversational German, a bit louder and direct. Preserve the reference speaker.\nSCRIPT:\n'+text,
          'streaming':False,'seconds':max(1.2,len(text)/14),'temperature':.8,'guidance':2.,'voice_mode':'profile',
          'voice_profile':'anime_088','voice_conversion':False,'align':True,'seed':seed}
    result=None
    for _ in range(60):  # 409 = the shared TTS is busy with another turn; wait and retry
        with client.stream('POST','/api/turn',json=body) as response:
            if response.status_code==409:time.sleep(2);continue
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith('data: ') and json.loads(line[6:]).get('event')=='result':result=json.loads(line[6:])
        break
    if result is None:raise RuntimeError('TTS did not return a fixture take')
    wave,rate=sf.read(io.BytesIO(client.get(result['candidates'][0]['url']).content),dtype='float32')
    sf.write(path,wave.mean(1) if wave.ndim>1 else wave,rate)

def segments(loud,gap=1500):
    out=[]
    for t in loud:
        if out and t-out[-1][1]<=gap:out[-1][1]=t
        else:out.append([t,t])
    return out

async def run(playwright,url,case):
    request,rate=sf.read(FIXTURES/'request.wav',dtype='float32');interruption,_=sf.read(FIXTURES/f'{case}.wav',dtype='float32')
    mic=FIXTURES/f'mic-{case}.wav'
    sf.write(mic,np.r_[np.zeros(3*rate),request,np.zeros(7*rate),interruption,np.zeros(20*rate)].astype(np.float32),rate,subtype='PCM_16')
    browser=await playwright.chromium.launch(headless=True,args=['--no-sandbox','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream',
        '--use-file-for-fake-audio-capture='+str(mic),'--autoplay-policy=no-user-gesture-required'])
    page=await browser.new_page();await page.add_init_script(INIT)
    try:
        await page.goto(url+'/desk-robot/');await page.wait_for_function('window.robo',timeout=60000)
        await page.evaluate('''()=>{const old=robo.on.message;robo.on.message=m=>{
            if(['speech_turn_decision','reply_cancelled','stop_command','asr_sentence','ignored','speaker_focus'].includes(m.type))
              bt.msgs.push({at:performance.now(),type:m.type,text:m.text||'',action:m.action||null,reason:m.reason||m.source||''});old&&old(m)}}''')
        await page.wait_for_timeout((3+len(request)/rate+7+len(interruption)/rate+14)*1000)
        data=await page.evaluate('bt')
    finally:await browser.close()
    spoken=segments(data['loud'])
    if len(spoken)<2:return {'case':case,'error':'interruption not heard'}
    onset,end=spoken[-1]
    first=data['plays'][0]['id'] if data['plays'] else None
    speaking=any(p['id']==first and p['at']<onset for p in data['plays'])
    stops=[s['at'] for s in data['stops'] if s['id']==first and s['at']>=onset-200]
    later=[p for p in data['plays'] if p['id']!=first and p['at']>onset]
    decision=next((m['action'] for m in data['msgs'] if m['type']=='speech_turn_decision' and m['at']>=onset),None)
    stopped=bool(stops);expected=CASES[case][1]
    ok=speaking and (stopped if expected in ('stop','answer') else not stopped) and (bool(later) if expected=='answer' else True)
    return {'case':case,'expected':expected,'ok':ok,'robby_was_speaking':speaking,'stopped':stopped,
            'stop_after_speech_end_ms':round(stops[0]-end) if stops else None,'decision':decision,'answered':bool(later),
            'events':[(round(m['at']-onset),m['type'],m['text'][:50],m['action'] or m['reason'][:50]) for m in data['msgs'] if m['at']>=onset-300]}

async def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url',default='http://127.0.0.1:8793');parser.add_argument('--runs',type=int,default=1)
    parser.add_argument('--cases',default=','.join(CASES))
    args=parser.parse_args();FIXTURES.mkdir(parents=True,exist_ok=True)
    with httpx.Client(base_url=TTS,timeout=300) as client:
        synthesize(client,REQUEST,FIXTURES/'request.wav',500)
        for index,(case,(text,_)) in enumerate(CASES.items()):synthesize(client,text,FIXTURES/f'{case}.wav',501+index)
    results=[]
    async with async_playwright() as playwright:
        for case in args.cases.split(','):
            for _ in range(args.runs):
                try:row=await run(playwright,args.url,case)
                except Exception as exc:row={'case':case,'error':str(exc)[:200]}
                results.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    passed=sum(1 for r in results if r.get('ok'));print(f'PASSED {passed}/{len(results)}')

if __name__=='__main__':asyncio.run(main())
