"""ASR of actual paired eager/graphed synthesis; no private audio."""
import base64,json,sys
from pathlib import Path
import numpy as np,soundfile as sf,httpx
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT.parent/'humaneness-small'))
from metrics import word_errors
from parallel_verification_benchmark import PROMPTS
from prompting import parse_literal
texts={k:parse_literal(p,'structured')['text'] for k,p in PROMPTS.items()}
texts['english']='Please do not open the door. We can talk about it tomorrow.'
rows=[]
with httpx.Client(timeout=20,trust_env=False) as c:
 for path in sorted(Path('/tmp/robby-prefill-graph').glob('*.wav')):
  mode,name,seed=path.stem.split('-');wave,sr=sf.read(path,dtype='float32');a=resample_poly(wave,16000,sr).astype('<f4')
  e=c.post('http://127.0.0.1:8822/batch/parakeet_ultra',json={'audio':[base64.b64encode(a.tobytes()).decode()]}).json()['results'][0]
  w=word_errors(texts[name],e['text']);row={'mode':mode,'case':name,'seed':int(seed),'text':texts[name],'transcript':e['text'],'wer':w['wer'],'rms':float(np.sqrt(np.mean(wave**2))),'audio_s':len(wave)/sr,'finite':bool(np.isfinite(wave).all())};rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
report={'rows':rows,'passed':all(x['wer']<=.15 and x['finite'] and x['rms']>.001 for x in rows),'scope':'Tiny authored intelligibility check, not a listening-quality or speaker-similarity study.'}
(ROOT/'logs/isolation-latency/prefill-quality.json').write_text(json.dumps(report,indent=2));assert report['passed']
