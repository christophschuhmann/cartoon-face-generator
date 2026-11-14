"""Publish only authored test summaries, never private session logs."""
import html,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def worklog_entry():
 path=ROOT/'static/whole-body-stunts.json'
 if not path.exists():return ''
 report=json.loads(path.read_text());passed=report.get('passed',False)
 return ('<!-- whole-body-stunts --><article id="whole-body-stunts" class="'+('done' if passed else 'working')+'"><h2><input type="checkbox" disabled '+('checked' if passed else '')+'> Whole-body spins and somersaults · 13 November 2026</h2><p>Validated direct commands, playback-synchronized whole-body transforms including the platform, crouch and soft landing, bounded spoken-response recovery. '+str(len(report['rows']))+' authored HTTPS/browser cases; synthetic microphone, actual model calls. <a href="/static/whole-body-stunts.html">Results, retained failures and reproduction</a>.</p></article><!-- /whole-body-stunts -->')
def main():
 typed=json.loads((ROOT/'logs/stunts-body-browser-20261113.json').read_text())
 spoken=json.loads((ROOT/'logs/stunts-body-spoken-20261113.json').read_text())
 rows=[]
 for source,report in [('Typed HTTPS + real LLM/TTS',typed),('Synthetic microphone + real ASR/LLM/TTS',spoken)]:
  for turn in report['turns']:
   action=next((e['steps'] for e in turn['events'] if e['type']=='avatar_action'),[])
   frames=turn['frames'];render=[f['render_ms'] for f in frames if 'render_ms' in f]
   rows.append({'path':source,'request':turn['request'],'passed':turn.get('passed',False),'steps':action,
      'audio_chunks':turn.get('audio',turn.get('audio_chunks')),
      'audio_during_animation':any(f.get('audio',f.get('heard')) for f in frames),
      'render_ms_median':round(statistics.median(render),1) if render else None,
      'reply':' '.join(e.get('sentence_text',e.get('text','')) for e in turn['events'] if e['type']=='reply'),
      'fallback_ack':any(e.get('timing',{}).get('visual_acknowledgment_fallback',False) for e in turn['events'])})
 report={'passed':typed['passed'] and spoken['passed'],'date':'2026-11-13','rows':rows,'renderer_checks':typed['renderer'],
         'scope':'Authored test material, real public HTTPS and model calls; synthetic microphone, no physical room test.'}
 (ROOT/'static/whole-body-stunts.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
 e=html.escape
 table=''.join('<tr>'+''.join('<td>'+e(str(v))+'</td>' for v in [r['request'],r['path'],', '.join(s['kind'] for s in r['steps']),r['audio_chunks'],r['audio_during_animation'],'PASS' if r['passed'] else 'FAIL'])+'</tr>' for r in rows)
 page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Robby: body turns and somersaults</title><style>body{max-width:1050px;margin:30px auto;padding:20px;font:17px/1.6 system-ui;color:#243b47;background:#faf8f4}h1{line-height:1.2}a{color:#176175}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;border:1px solid #cbd8dd;text-align:left}.scroll{overflow:auto}code{overflow-wrap:anywhere}img{max-width:100%}</style><nav><a href="/desk-robot/">Open Robby</a> · <a href="/static/avatar-manual.html">Expressions and tricks manual</a></nav><h1>Whole-body turns, somersaults and spoken reactions</h1><p>13 November 2026. The normal “Dreh dich im Kreis” request now turns the platform and body together. “Dreh deinen Kopf” retains head-only movement. “Mach einen Salto” performs a crouch, one forward flip and a soft landing. “Mach einen Salto rückwärts” / “Do a backflip” reverses its direction.</p>
<p>Actions use the existing validated perform_avatar vocabulary. Direct requests have a deterministic parser and a unique action ID, so they are scheduled even if the LLM only describes a movement. The browser waits for actual speech playback, or four seconds at most, before starting. Silent requests and UI previews start immediately. Stop, disabled actions and reduced-motion controls remain effective.</p>
<h2>Recorded integration checks</h2><p>Overall result: <b>RESULT</b>. Real model calls and public HTTPS; microphone fixtures were generated from authored text. No physical camera/microphone or real-room robustness claim. Request-level passes require actual audio and visible motion during playback.</p><div class="scroll"><table><tr><th>Request</th><th>Path</th><th>Action</th><th>Audio chunks</th><th>Audio during action</th><th>Result</th></tr>TABLE</table></div>
<h2>What was wrong</h2><p>The original turn only moved the head. The somersault action was missing. A live request also produced a third-person Markdown stage direction instead of words to speak, which failed TTS verification. Later tests found laughter-only replies and an untyped planning failure; those negative receipts are retained. Stage directions and generic laughter-only reactions now trigger bounded regeneration. After two unusable completions, a short local acknowledgment is allowed for a directly requested trick and explicitly marked in metrics. Normal responses remain LLM-generated; optional petting/idle dialogue does not use this fallback. Transient HTTP failures preserve their status for the retry policy. The TTS word gate is not weakened.</p>
<h2>Rendering and limits</h2><p>The existing CPU 3-D renderer transforms all meshes, face texture and surface normals together, after ordinary head articulation. Tests assert movement of actual platform geometry, not only an animation label. A temporary camera pullback keeps the jump visible. During whole-body motion, internal raster size is capped at 360 pixels on its longest edge; normal resolution returns at rest. The older SVG page has a flat cartoon fallback. All tricks are screen effects, never robot motor commands.</p>
<p>The test is a small deterministic command suite, not a guarantee that all paraphrases, speech recordings or API failures work. A four-second animation fallback can precede speech during a longer provider outage. The new code does not address the separately documented background-speaker false match.</p>
<h2>Reproduce</h2><p>See <code>robo-integration/WHOLE_BODY_STUNTS.md</code>, <code>browser_whole_body_stunts.py</code> and <code>browser_whole_body_spoken.py</code>. Run browser conversation tests serially. <a href="whole-body-stunts.json">Measured JSON summary</a>. Model/TTS services and the existing tunnel are reused.</p></html>'''
 (ROOT/'static/whole-body-stunts.html').write_text(page.replace('RESULT','PASS' if report['passed'] else 'FAIL').replace('TABLE',table))
 worklog=ROOT/'static/worklog.html'
 if worklog.exists():
  import re
  old=re.sub(r'<!-- whole-body-stunts -->.*?<!-- /whole-body-stunts -->','',worklog.read_text(),flags=re.S)
  worklog.write_text(old.replace('</h1>','</h1>'+worklog_entry(),1))
 print(json.dumps({'passed':report['passed'],'cases':len(rows)}))
if __name__=='__main__':main()
