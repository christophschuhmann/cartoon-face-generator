"""Collect measured outputs, write a playable gallery and package actual videos.

No model files, virtualenv, credentials or vendor source enter the archive.
"""
from pathlib import Path
import argparse,collections,hashlib,html,json,statistics,zipfile

ROOT=Path(__file__).resolve().parent
OBSERVATIONS={
 '01':'Without an end anchor the model invents a clearer frown, but shrinks and recenters the face. Fails strict endpoint/position control.',
 '02':'Start/end retained closely. Speaking mouth changes visibly; intended anger is mild because the supplied ending pose is mild.',
 '03':'Three anchors preserve identity and position well in the sampled frames. A blink and speaking-mouth shapes appear. Ending anger remains subtle.',
 '04':'6+2 updates retain endpoints and speech; sampled late mouth shapes occasionally have double thin contours.',
 '05':'4+2 updates retain endpoints and speech in this example. Motion is restrained; less evidence of blinking than the standard schedule.',
 '06':'Lower-resolution variant retains identity and speech; small lines have less definition.',
 '07':'Sad mouth changes toward a hopeful smile. Speaking-mouth interiors occasionally contain gray, soft details.',
 '08':'Doubt changes into amusement. Early brow motion reaches beyond the upper border despite fixed-camera instructions.',
 '09':'Fear relaxes into relief. Mid-clip eyebrow/face drift reaches the top border; strict position control is not fully met.',
 '10':'Five anchor images constrain the trajectory more tightly; increases image-conditioning cost. Additional anchors are directing frames, not dense ground truth.',
 '11':'Same seed, prompt and three anchors as case 03, with warm caches. Close agreement with source endpoints.',
 '12':'Real full-dev + distilled LoRA run. CPU weight retention avoids initial fusion OOM; model loading/fusion makes the first generation slow.',
 '13':'Warm dev + distilled LoRA still pays per-generation fusion/transfer cost. Blink and speaking mouths retained; slower than direct distilled weights.',
 '14':'A more downward inner-brow slope makes the ending sterner. Added SVG margin keeps all sampled features inside the image. Speaking-mouth shapes remain variable.',
 '15':'Same padded directing pose with 4+2 updates. Endpoints remain close; a sampled mouth briefly has doubled thin contours. Not an independent emotion-recognition result.',
 '16':'Five padded anchors keep sampled brows inside the image and guide fear toward relaxed eyes. Extra conditioning limits motion; small speaking mouths sometimes turn gray.',
}
TITLES={'happy_to_angry':'Fröhlich → sanft wütend','happy_to_angry_clear':'Fröhlich → deutlicher wütend, mit Rand',
 'sad_to_hopeful':'Traurig → hoffnungsvoll','doubt_to_laughter':'Skeptisch → amüsiert',
 'fear_to_relief':'Ängstlich → erleichtert','fear_to_relief_margin':'Ängstlich → erleichtert, mit Rand'}

def build():
    rows=[];repeat_groups=collections.defaultdict(list)
    for directory in sorted((ROOT/'output').iterdir()):
        if not (directory/'timing.json').exists():continue
        timing=json.loads((directory/'timing.json').read_text())
        settings=json.loads((directory/'settings.json').read_text())
        # Make old provenance files portable, without altering generated video.
        for anchor in settings['anchors']:
            path=Path(anchor['path'])
            if path.is_absolute():anchor['path']=str(path.relative_to(ROOT))
        (directory/'settings.json').write_text(json.dumps(settings,indent=2)+'\n')
        metrics=json.loads((directory/'video_metrics.json').read_text()) if (directory/'video_metrics.json').exists() else None
        speech=json.loads((directory/'speech_check.json').read_text()) if (directory/'speech_check.json').exists() else None
        row={'name':directory.name,'title':TITLES[settings['pair']],'timing':timing,'metrics':metrics,'speech':speech,
             'manual_contact_sheet_review':OBSERVATIONS.get(directory.name[:2]),
             'video_bytes':(directory/'video.mp4').stat().st_size,
             'video_sha256':hashlib.sha256((directory/'video.mp4').read_bytes()).hexdigest()}
        rows.append(row)
        if timing.get('repeat_index') and not timing['first_run_in_process']:
            repeat_groups[(timing['schedule'],timing['width'],timing['height'])].append(timing['wall_seconds'])
    benchmarks=[{'schedule':key[0],'size':list(key[1:]),'warm_repetitions':len(values),
                 'median_seconds':statistics.median(values),'min_seconds':min(values),'max_seconds':max(values)}
                for key,values in sorted(repeat_groups.items())]
    result={'model':'LTX-2.5','vendor_commit':'be6d6d0a69d11a0a399c462ed92606692e5f8697',
       'model_revision':'49b093a39c19169a8a81721dcc541e07e945232f','clips':rows,'warm_benchmarks':benchmarks,
       'scope':'Measured on one A100 80GB server. ASR checks words, not voice quality or lip synchronization. Pixel metrics do not measure emotion recognition.',
       'dense_ground_truth':False,'video_bytes':sum(row['video_bytes'] for row in rows)}
    (ROOT/'results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    featured=[row for row in rows if 'repeat' not in row['name']]
    cards=[]
    for row in featured:
        name=row['name'];t=row['timing'];speech=row['speech'] or {};metrics=row['metrics'] or {}
        cards.append(f'''<article><h2>{html.escape(row['title'])}</h2><p>{html.escape(name)} · {t['schedule'].replace('_','+')} Updates · {t['wall_seconds']:.2f} s Generierung · {'erster Lauf' if t['first_run_in_process'] else 'warme Caches'}</p>
<video controls preload="metadata" poster="output/{name}/frame_0000.png" src="output/{name}/video.mp4"></video>
<p>{html.escape(speech.get('transcript',speech.get('text','Sprachprüfung noch nicht vorhanden')))}</p>
<p>{html.escape(row['manual_contact_sheet_review'] or 'Review pending')}</p>
<p><a href="output/{name}/contact_sheet.png">Kontaktbogen</a> · <a href="output/{name}/settings.json">Einstellungen</a> · <a href="output/{name}/timing.json">Zeitmessung</a> · <a href="output/{name}/video.mp4" download>MP4 laden</a></p></article>''')
    page='''<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LTX 2.5 Cartoon-Videotests</title>
<style>body{font:16px system-ui;background:#f3f4f6;color:#18202a;margin:24px auto;max-width:1150px;padding:16px}article{background:white;border-radius:12px;padding:20px;margin:24px 0}video{width:100%;height:auto}h2{margin-top:0}a{color:#175cc1}p{line-height:1.5}table{border-collapse:collapse}td,th{padding:10px;text-align:left;border-bottom:1px solid #bbb}</style>
<h1>LTX 2.5: echte Cartoon-Videos mit deutscher Sprache</h1><p>Die Referenzbilder stammen aus unserem SVG-Rig. Die MP4s einschließlich Sprache stammen direkt aus LTX; sie sind nicht nachträglich stabilisiert oder vertont. Jeder Clip hat 129 Frames bei 24 fps, also 5,375 Sekunden.</p>
<p>Start-, End- und Zwischenbilder werden als Bildbedingungen verwendet. Die Zeitmessungen enthalten Generierung, Decoding und MP4-Encoding; Downloads, Python-Start und CUDA-Initialisierung liegen außerhalb. Warme Caches benötigen hier bis etwa 78 GB GPU-Speicher.</p>
<p><a href="ltx25_examples.zip">Alle Videos, Eingaben, Skripte und Berichte als ZIP</a> · <a href="results.json">Maschinenlesbarer Bericht</a></p>
<h2>Wiederholte Messungen mit warmen Caches</h2><table><tr><th>Updates</th><th>Format</th><th>n</th><th>Median</th><th>Bereich</th></tr>'''
    for b in benchmarks:page+=f"<tr><td>{b['schedule'].replace('_','+')}</td><td>{b['size'][0]}×{b['size'][1]}</td><td>{b['warm_repetitions']}</td><td>{b['median_seconds']:.2f} s</td><td>{b['min_seconds']:.2f}–{b['max_seconds']:.2f} s</td></tr>"
    page+='</table>'+''.join(cards)+'</html>'
    (ROOT/'index.html').write_text(page)
    return result

def package():
    path=ROOT/'ltx25_examples.zip'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for item in sorted(ROOT.rglob('*')):
            relative=item.relative_to(ROOT)
            if not item.is_file() or any(part in ('models','vendor','.venv','__pycache__') for part in relative.parts):continue
            if item.name=='public_verification.json':continue
            if item.suffix in ('.zip','.log','.wav','.pyc'):continue
            if item.suffix not in ('.py','.sh','.txt','.md','.json','.svg','.png','.mp4','.html'):continue
            archive.write(item,relative.as_posix())
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:raise ValueError('Archive CRC check failed')
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--package',action='store_true');args=parser.parse_args()
    result=build();print(json.dumps({'clips':len(result['clips']),'warm_benchmarks':result['warm_benchmarks']}))
    if args.package:print(json.dumps(package()))
