"""Exercise real local ASR, Ears and SVG preparation before enabling uploads."""
import argparse
import gzip
import json
from pathlib import Path
import time
from .audio_jobs import AudioJobs,ROOT


def verify(source,variant='base'):
    jobs=AudioJobs();started=time.monotonic();job=jobs.start(source.read_bytes(),variant);last=None
    try:
        while True:
            state=jobs.snapshot(job['id'])
            signature=(state['state'],state.get('stage'),state.get('segment'))
            if signature!=last:
                print(json.dumps(state,ensure_ascii=False),flush=True);last=signature
            if state['state']=='error':raise RuntimeError(state['error'])
            if state['state']=='ready':break
            if time.monotonic()-started>900:raise TimeoutError('End-to-end verification exceeded 15 minutes')
            time.sleep(.5)
        data=json.loads(gzip.decompress(jobs.result))
        assert len(data['words'])>=3,'Expected a spoken test sample with at least three words'
        assert data['segments'],'Expected emotion segments'
        for word in data['words']:
            assert 0<=word['start']<word['end']<=data['duration']+.01,word
        for segment in data['segments']:
            assert len(segment['scores_raw'])==40
            assert len(segment['scores_z'])==40 and len(segment['voice_z'])==57
            assert {'ranting','whispering'}<=segment['styles'].keys()
            if variant=='medium':assert segment['normalization']=='medium-speech-80265-mean-std'
        assert 'NaN' not in json.dumps(data) and 'Infinity' not in json.dumps(data)
        report={'runtime':'redux-q8-ears-script-v1','input':source.name,'duration':data['duration'],
            'words':len(data['words']),'segments':len(data['segments']),'transcript':data['transcript'],
            'stage_seconds':data['stage_seconds'],'analysis_seconds':data['analysis_seconds'],
            'models':data['models'],'normalization':data['segments'][0]['normalization'],
            'style_dimensions':len(data['segments'][0]['voice_z']),'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
        out=ROOT/'webcam_mapper/output/verification'
        stem='audio_cpu' if variant=='base' else 'audio_medium_cpu'
        (out/(stem+'_result.json')).write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
        (out/(stem+'_report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        marker=ROOT/('webcam_mapper/models/audio_runtime_verified.json' if variant=='base' else 'webcam_mapper/models/ears/medium/inference_verified.json')
        temporary=marker.with_suffix('.tmp');temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');temporary.replace(marker)
        print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    finally:jobs.cancel()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('--variant',choices=('base','medium'),default='base')
    args=parser.parse_args();verify(args.source,args.variant)
