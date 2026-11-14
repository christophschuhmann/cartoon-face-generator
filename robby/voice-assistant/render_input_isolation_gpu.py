"""Render measured JSON artifacts and authored listening examples; no inference."""
import base64
import html
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'logs/input-isolation-gpu'
reports={}
for p in sorted(OUT.glob('*.json')):
    d=json.loads(p.read_text())
    if d.get('status')=='completed' and d.get('rows'): reports[d['label']]=d


def fmt(x, digits=2):
    return '—' if x is None else f'{x:.{digits}f}'


def memory(d):
    return next((s.split(',')[1].strip() for s in d.get('gpu_process_memory',[])
                 if s.split(',')[0].strip()==str(d.get('pid'))),'—')


speed=[]; quality=[]; md=[]
for name,d in reports.items():
    r=next((r for r in d['rows'] if r['case']=='christoph-bg0.5'),d['rows'][0])
    t=d.get('paced',{})
    cells=[name,str(r['chunk_ms']),fmt(r['chunk_p50_ms']),fmt(r['chunk_p95_ms']),
           fmt(r['processing_rtf'],3),fmt(t.get('first_output',{}).get('wall_ms')),
           fmt(t.get('output_age_p95_ms')),memory(d),fmt(d['model_initialize_ms']/1000)]
    speed.append('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in cells)+'</tr>')
    md.append('| '+' | '.join(cells)+' |')
    for r in d['rows']:
        a=r.get('asr')
        if a is None:continue
        cells=[name,r['case'],fmt(a['target_interval_wer']),fmt(a['whole_scene_target_wer']),
               fmt(r.get('background_only_attenuation_db')),
               fmt(r.get('vad',{}).get('background_only',{}).get('fraction_over_0_5')),
               a['target_interval_text'],a['background_only_text']]
        quality.append('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in cells)+'</tr>')

(OUT/'speed-table.md').write_text('| Configuration | Chunk ms | Compute p50 ms | Compute p95 ms | RTF | First output, paced ms | Newest output age p95 ms | Process VRAM | Initialization s |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n'+'\n'.join(md)+'\n')


def player(path):
    if not path.exists():return '<span>Not measured</span>'
    data=subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',str(path),'-ac','1',
                                 '-codec:a','libmp3lame','-b:a','96k','-f','mp3','pipe:1'])
    return '<audio controls preload="none" src="data:audio/mpeg;base64,'+base64.b64encode(data).decode()+'"></audio>'


listen=[]
for who in ['christoph','selma']:
    for level in ['0','0.5','1']:
        case=who+'-bg'+level
        cards=[]
        for title,path in [
          ('Unfiltered',ROOT/'logs/input-isolation'/(case+'-raw.wav')),
          ('Alkove Focus · CPU',ROOT/'logs/input-isolation'/(case+'-alkove.wav')),
          ('VoxLock · native CUDA Graphs',OUT/('vox-torch-graph-40-'+case+'.wav')),
          ('Scicom agent · CUDA Graphs',OUT/('scicom-agent-graph-40-'+case+'.wav'))]:
            cards.append('<div class="audio-card"><b>'+title+'</b>'+player(path)+'</div>')
        listen.append('<details><summary>'+case+' · independent clean enrollment</summary><div class="players">'+''.join(cards)+'</div></details>')

page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Robby · GPU speaker isolation benchmark</title>
<style>:root{color-scheme:dark}body{background:#101725;color:#e8edf6;font:16px/1.6 system-ui;margin:0}main{max-width:1350px;margin:auto;padding:32px 24px 80px}a{color:#8dd8ff}h1{font-size:clamp(28px,5vw,46px);line-height:1.2}h2{margin-top:38px}.lead{max-width:900px;color:#c3cfdf}.badge{display:inline-block;background:#204f43;color:#baf2d8;border-radius:20px;padding:4px 14px;font-size:14px}.scroll{overflow:auto;border:1px solid #31415c;border-radius:12px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:12px;border-bottom:1px solid #293650}th{background:#1c2941;white-space:nowrap}td:not(:first-child){font-variant-numeric:tabular-nums}tr:hover{background:#19273b}details{padding:16px;border:1px solid #31415c;border-radius:12px;margin:12px 0}summary{cursor:pointer;font-weight:650}.players{display:grid;grid-template-columns:repeat(auto-fit,minmax(265px,1fr));gap:20px;margin-top:20px}.audio-card b{display:block;margin-bottom:10px}audio{width:100%}.notice{padding:18px;border-left:4px solid #e3b562;background:#27241e;border-radius:6px}code{color:#aae1ff}p,li{max-width:1050px}footer{margin-top:45px;color:#9baec8}</style>
<main><a href="/desk-robot/">← Robby demo</a><p><span class="badge">Measured on RTX 3090 · 12 November 2026</span></p>
<h1>Fast speaker isolation needs stateful GPU streaming</h1>
<p class="lead">Real model inference with 16–80 ms audio chunks, fixed reference voices and continuous recurrent state. Robby and the podcast server remained running. These filters are now available as optional 40-ms CUDA microphone filters in <a href="/desk-robot/">Robby → Speech recognition &amp; quick replies</a>; Off remains the default.</p>
<h2>Measured speed</h2><p>The same 7.83-second synthetic TV mixture is used below. Compute includes CPU→GPU input, inference, GPU→CPU output and overlap-add. RTF below 1 is faster than real time. First output is measured with capture-paced input, after model and reference warm-up.</p>
<div class="scroll"><table><thead><tr><th>Configuration</th><th>Chunk ms</th><th>Compute p50 ms</th><th>Compute p95 ms</th><th>RTF</th><th>First output ms</th><th>Output age p95 ms</th><th>Process VRAM</th><th>Initialization s</th></tr></thead><tbody>'''+''.join(speed)+'''</tbody></table></div>
<p>Output age measures the newest available sample; earlier samples in the same packet also waited for the packet to fill. This is an in-process timing test, not browser microphone-to-ASR latency. Initialization includes model load and, for Scicom, graph warm-up; VoxLock graph capture is in separately recorded stream warm-up. Do not add these cold costs to every audio chunk.</p>
<h2>What changed the speed?</h2>
<p>VoxLock's simple ONNX CUDA execution launches many small operators per chunk. Keeping its speaker keys and LSTM state in VRAM alone did not solve this. The native PyTorch implementation uses the upstream enrollment and chunk modules with fixed-shape CUDA Graphs, retaining state and graph inputs on the GPU. Scicom also benefits strongly from its official CUDA-graph streaming engine. Larger chunks amortize compute but wait longer to collect audio.</p>
<h2>Quality is still the constraint</h2><div class="notice">A fast filter is not automatically a reliable speaker selector. Both families preserve clean speech, but competing TV speech still leaks in these tests. Scicom sometimes suppresses the intended synthetic voice. Two synthetic German voices cannot establish real-room robustness or a population-level ranking.</div>
<p>Target WER uses only the known speech interval (+100 ms padding). Scene WER compares the whole recording with the target sentence, counting leaked background words as insertions; it can exceed 1. Tail attenuation is measured after the target stops. ASR on quiet residuals can itself hallucinate; inspect the audio as well.</p>
<p>TV-tail VAD fraction is the proportion of 32-ms frames with Silero-vad 6.2.1 probability above 0.5 on the actual filtered signal, with no additional gain normalization. Lower means fewer frames likely to keep an end-of-turn detector waiting. This still does not establish correct live turn-taking.</p>
<div class="scroll"><table><thead><tr><th>Configuration</th><th>Case</th><th>Target WER</th><th>Scene WER</th><th>Tail attenuation dB</th><th>TV-tail VAD fraction</th><th>Target transcript</th><th>TV-only tail transcript</th></tr></thead><tbody>'''+''.join(quality)+'''</tbody></table></div>
<h2>Listen to the same mixtures</h2><p>Public authored synthetic fixtures, not private microphone recordings. Background gains 0, 0.5 and 1 are full-clip RMS ratios, not physical distance. TV begins one second before the intended user and continues for four seconds after them. Each model receives a separate clean introduction from the selected voice. Players embed mono 96-kbps MP3 previews; metrics use uncompressed float32 waveforms.</p>'''+''.join(listen)+'''
<h2>Live integration — 40 ms, optional</h2><p>In <a href="/desk-robot/">Robby</a>, open Settings &amp; details → Speech recognition &amp; quick replies → Microphone voice isolation. Choose VoxLock or Scicom Agent. Both use CUDA Graphs on GPU 1; Off is the default. Learn my voice captures four seconds. Accepted clean utterances can also provide a session-only reference. Clear voice reference or allow another speaker to hand over.</p><p>The real CUDA controller/IPC replay measured first forwarded audio at 49.57 ms for VoxLock and 56.22 ms for Scicom with 40-ms chunks. These are capture-paced model-path timings, not total browser-to-reply latency. Both produced the complete expected German ASR sentence. Public HTTPS Chrome tests passed selection, live filtering, ASR/LLM/TTS playback, reference clearing and switching Off.</p><div class="notice">A separate long-reply test with 120-ms delayed simulated bot echo failed spoken Stop and hit the ASR backlog limit with VoxLock and with isolation Off. Reliable real-room interruptions are not established by these filter tests. Environmental sound analysis retains raw audio.</div><h2>Interpretation for Robby</h2><p>The native VoxLock CUDA-graph adapter is a promising low-latency starting point; Scicom offers an alternative with a learned presence gate. Neither should silently replace the raw microphone branch. Use a confirmed clean enrollment, retain wake-word/identity recovery and permit explicit speaker switching. Benchmark actual room audio, short stop commands, emotional delivery, reverb and Robby's own echo before a default rollout.</p>
<p>Alkove Focus remains a CPU reference: its earlier 16-ms test processed chunks in approximately 10–11 ms. No supported CUDA version was tested. A smaller GPU tensor or half precision does not by itself ensure lower single-stream latency. No model output was simulated.</p>
<h2>Sources and reproducibility</h2><p>Source/weights: <a href="https://github.com/arbazsiddiqui/voxlock">VoxLock</a>, <a href="https://huggingface.co/Scicom-intl/voice-isolator">Scicom voice-isolator</a>, <a href="https://alkove.ai/docs/models/focus/">Alkove Focus</a>. Scicom declares a nonstandard license; do not assume all candidates share VoxLock's Apache license.</p>
<p>Local protocol: <code>robo-integration/INPUT_ISOLATION_GPU.md</code>. Reproducible download and benchmark scripts: <code>prepare_input_isolation_gpu.py</code>, <code>benchmark_input_isolation_gpu.py</code>, <code>score_input_isolation_gpu.py</code>. Raw measurements, model revisions, input hashes and WAVs: <code>logs/input-isolation-gpu/</code>. This page is regenerated by <code>render_input_isolation_gpu.py</code>.</p>
<footer>Research measurement on a shared host · optional live integration now available, off by default · no claim of calibrated speaker identity</footer></main></html>'''
dest=ROOT/'static/input-isolation-gpu.html'
dest.write_text(page)
print(dest, len(page))
