"""One cancellable local audio job; uploads live only in a temporary E/project folder."""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid
from .audio_animation import prepare_performance

ROOT=Path(__file__).resolve().parents[1]

class AudioJobs:
    def __init__(self):
        self.lock=threading.RLock();self.job=None;self.process=None;self.result=None

    def readiness(self):
        missing=[]
        for file in ('.venv-audio/Scripts/python.exe','webcam_mapper/models/ears/scores_cpu.pt',
                     'webcam_mapper/models/parakeet-redux/redux-q8.gguf',
                     'webcam_mapper/models/parakeet-redux/redux-bundle.gguf',
                     'webcam_mapper/models/parakeet-redux/cpp/parakeet-v0.6.1-bin-win-cpu-x64/parakeet-cli.exe'):
            if not (ROOT/file).is_file():missing.append(file)
        verification=ROOT/'webcam_mapper/models/audio_runtime_verified.json'
        try:verified=json.loads(verification.read_text(encoding='utf8')).get('runtime')=='redux-q8-ears-script-v1'
        except (OSError,ValueError):verified=False
        medium=ROOT/'webcam_mapper/models/ears/medium'
        try:
            medium_report=json.loads((medium/'inference_verified.json').read_text(encoding='utf8'))
            medium_verified=(medium_report.get('runtime')=='redux-q8-ears-script-v1'
                and medium_report.get('normalization')=='medium-speech-80265-mean-std')
        except (OSError,ValueError):medium_verified=False
        medium_ready=not missing and verified and medium_verified and all((medium/name).is_file()
            for name in ('scores_cpu.pt','runtime_verification.json','speech_reference.json'))
        return {'ready':not missing and verified,'missing':missing,'verified':verified,'variants':{'base':not missing and verified,'medium':medium_ready},
                'message':'Audioanalyse bereit.' if not missing and verified else 'Audioanalyse wird eingerichtet und auf dieser CPU geprüft. Die Dateiauswahl ist bereits verfügbar.',
                'asr':'Moondream Parakeet Redux',
                'emotion':'LAION Humaneness Ears Medium / Base','maximum_mb':100,'maximum_seconds':600}

    def snapshot(self,identifier=None):
        with self.lock:
            if identifier and (not self.job or self.job['id']!=identifier):raise KeyError('Unknown audio job')
            return dict(self.job) if self.job else {'state':'idle'}

    def cancel(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                if os.name=='nt':
                    # Only this known analysis worker and its ffmpeg/ASR children.
                    subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,timeout=10)
                else:self.process.terminate()
            self.process=None;self.result=None
            if self.job:self.job=dict(self.job,state='cancelled')

    def start(self,data,variant='base'):
        if variant not in ('base','medium'):raise ValueError('Invalid Ears variant')
        self.cancel()
        identifier=uuid.uuid4().hex
        with self.lock:
            self.job={'id':identifier,'state':'running','stage':'decode','progress':0.}
        threading.Thread(target=self._run,args=(identifier,data,variant),daemon=True,name='audio-analysis').start()
        return self.snapshot()

    def _update(self,identifier,**data):
        with self.lock:
            if not self.job or self.job['id']!=identifier or self.job['state']=='cancelled':return False
            self.job.update(data);return True

    def _run(self,identifier,data,variant):
        started=time.monotonic()
        base=(ROOT/'webcam_mapper/output/audio_sessions').resolve()
        folder=(base/identifier).resolve()
        if folder.parent!=base:raise ValueError('Invalid temporary audio path')
        folder.mkdir(parents=True,exist_ok=True)
        source=folder/'input.audio';output=folder/'analysis.json';log=[]
        try:
            source.write_bytes(data);del data
            command=[str(ROOT/'.venv-audio/Scripts/python.exe'),'-u','-m','webcam_mapper.audio_inference',str(source),str(output),'--variant',variant]
            env=dict(os.environ,HF_HOME=str(ROOT/'webcam_mapper/models/hf-cache'),TMP=str(folder),TEMP=str(folder),PYTHONIOENCODING='utf-8')
            with self.lock:
                if not self._update(identifier):return
                process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                    text=True,encoding='utf8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                self.process=process
            for line in process.stdout:
                try:
                    item=json.loads(line)
                    if 'stage' in item:
                        item['progress']=float(item.get('progress',0))*.85
                        if not self._update(identifier,**item):process.terminate();break
                except (ValueError,TypeError):log=(log+[line.strip()])[-8:]
            code=process.wait()
            if not self._update(identifier):return
            if code:raise RuntimeError(self.job.get('error') or '\n'.join(log)[-1400:] or 'Audio worker failed')
            result=json.loads(output.read_text(encoding='utf8'))
            self._update(identifier,stage='animation',progress=.85)
            def progress(fraction):
                if not self._update(identifier,stage='animation',progress=.85+.14*fraction):raise InterruptedError('Cancelled')
            result=prepare_performance(result,progress)
            result['worker_seconds']=result['analysis_seconds'];result['analysis_seconds']=time.monotonic()-started
            encoded=gzip.compress(json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf8'),compresslevel=3)
            with self.lock:
                if self._update(identifier,state='ready',stage='complete',progress=1.,duration=result['duration'],
                                analysis_seconds=result['analysis_seconds'],segments=len(result['segments'])):
                    self.result=encoded
        except InterruptedError:pass
        except Exception as error:self._update(identifier,state='error',error=str(error))
        finally:
            # Only our fixed job files, never recursive deletion or input paths.
            for name in ('input.audio','decoded.wav','analysis.json'):
                try:(folder/name).unlink(missing_ok=True)
                except OSError:pass
            try:folder.rmdir()
            except OSError:pass
