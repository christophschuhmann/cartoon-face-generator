"""Add browser evidence and authored avatar snapshots to the generated audio report."""
import json,html,base64
from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=ROOT/'static/stunts-emotions.html';page=p.read_text();marker='<section id="browser-evidence">'
if marker in page:page=page[:page.index(marker)]+page[page.index('</section>',page.index(marker))+10:]
typed=json.loads((ROOT/'static/stunts-emotions-browser.json').read_text());spoken=json.loads((ROOT/'static/stunts-emotions-spoken.json').read_text())
section=marker+'<h2>Action verification</h2><p>Real HTTPS browser checks: '+str(len(typed['turns']))+' typed commands, '+str(len(typed['poses']))+' rendered catalog poses, and '+str(len(spoken['turns']))+' synthetic microphone requests. Typed and spoken runs passed: '+str(typed['passed'] and spoken['passed'])+'. No physical microphone or human forty-way expression-recognition test was performed.</p><ul>'
for row in typed['turns'][:2]:section+='<li>'+html.escape(row['request'])+' — rendered yaw range '+str(round(row['rendered_yaw_min'],1))+'° to '+str(round(row['rendered_yaw_max'],1))+'°.</li>'
section+='</ul><div style="display:flex;flex-wrap:wrap">'
for slug in ['anger','sadness','surprise','half-spin']:
 path=ROOT/('logs/stunt-preview-'+slug+'.png')
 if path.exists():section+='<figure style="margin:8px;width:210px"><img style="width:100%" src="data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()+'"><figcaption>'+slug+'</figcaption></figure>'
section+='</div><p>These are authored virtual robot poses. The half-turn shows the back of the head. Color, geometry and the forty-category taxonomy were preserved.</p></section>'
page=page.replace('</html>',section+'</html>');p.write_text(page)
