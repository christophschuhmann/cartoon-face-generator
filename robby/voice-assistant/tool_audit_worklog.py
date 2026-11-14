"""Append-only task-log entry, derived from authored test receipts."""
import json,html
from pathlib import Path
ROOT=Path(__file__).parent

def entry():
 def read(name):
  p=ROOT/'logs'/name
  return json.loads(p.read_text()) if p.exists() else {}
 b=read('tools-browser-20261114.json');f=read('tool-followups-live-20261114.json');m=read('tools-microphone-20261114.json')
 check=lambda ok:'✓ verified' if ok else 'pending / see receipt'
 return f'''<section id="tools-latency-20261114"><h2>Tools, expressions and latency choices · November 14</h2>
 <ul><li>{check(b.get('passed'))}: real HTTPS requests, audible PCM and rendered actions; 40 authored expressions, 8 grimaces, mobile diagrams and verification switches.</li>
 <li>{check(f.get('passed'))}: conversational lookup, an indirect eye-movement request, literal and semantic interruption rule registration, and clearing in an isolated test rule book.</li>
 <li>{check(m.get('passed'))}: authored synthetic microphone requests through the actual recognizers and TTS, with the second recognizer enabled and disabled.</li></ul>
 <p>Fixed capability/prompt drift, missing wake-address and facial aliases, lost tool calls, empty streamed replies, generic news filters, and a search-plugin/Cerebras prompt-format conflict. The semantic rule schema is selectable instead of always forcing a literal rule. Additional checks now have per-session switches with explicit quality trade-offs.</p>
 <p>Three native SVG diagrams and a generated tool catalogue are at the bottom of the demo. Public search uses the existing encrypted OpenRouter configuration and paid Exa retrieval; it returns real citations, not invented evidence. Earlier API rate-limit failures remain in receipts. No physical-room reliability claim is made by these synthetic tests.</p>
 <p><a href="/static/tools-audit.html">Full English report and receipts</a> · <a href="/desk-robot/#system-guide">Diagrams &amp; catalogue</a></p></section>'''

def update():
 import re
 p=ROOT/'static/worklog.html';s=p.read_text()
 s=re.sub(r'<section id="tools-latency-20261114">.*?</section>','',s,flags=re.S)
 marker='</body>' if '</body>' in s else '</html>'
 s=s.replace(marker,entry()+marker) if marker in s else s+entry()
 p.write_text(s)
if __name__=='__main__':update()
