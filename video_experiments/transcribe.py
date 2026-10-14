"""Independent ASR check of the generated audio; transcripts are not ground truth."""
from pathlib import Path
import argparse,json,re,time
import numpy as np
from faster_whisper import WhisperModel
from scipy.io import wavfile

ROOT=Path(__file__).resolve().parent


def words(text):return re.findall(r'\w+',text.lower())


def word_error(reference,hypothesis):
    expected=words(reference);actual=words(hypothesis);row=list(range(len(actual)+1))
    for i,a in enumerate(expected,1):
        new=[i]
        for j,b in enumerate(actual,1):new.append(min(new[-1]+1,row[j]+1,row[j-1]+(a!=b)))
        row=new
    return row[-1]/max(1,len(expected))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path)
    parser.add_argument('--skip-completed',action='store_true');args=parser.parse_args()
    model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=4,download_root=str(ROOT/'models/whisper'))
    directories=[args.directory] if args.directory else sorted((ROOT/'output').glob('*'))
    for directory in directories:
        if not (directory/'speech.wav').exists():continue
        if args.skip_completed and (directory/'speech_check.json').exists():continue
        rate,samples=wavfile.read(directory/'speech.wav');assert rate==16000 and samples.ndim==1
        samples=samples.astype(np.float32)/32768
        start=time.perf_counter();segments,info=model.transcribe(samples,language='de',beam_size=5,vad_filter=True)
        segments=list(segments);text=' '.join(segment.text.strip() for segment in segments)
        expected=' '.join(re.findall(r"'([^']+)'",(directory/'prompt.txt').read_text()))
        report={'asr_model':'faster-whisper small, CPU int8','language':info.language,'text':text,'expected_dialogue':expected,
            'asr_word_error_rate':word_error(expected,text),'seconds':time.perf_counter()-start,
            'segments':[{'start':s.start,'end':s.end,'text':s.text} for s in segments],
            'scope':'ASR can misrecognize short synthetic speech. This is a check, not a certified transcription.'}
        (directory/'speech_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'name':directory.name,'text':text,'expected':expected,'WER':report['asr_word_error_rate']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
