"""Non-destructive reference inventory and exact shared crop, with no denoising."""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[2]
CROP = (42, 56, 1492, 806)
NAMES = ['smile', 'tense', 'love', 'cheeky', 'tongue', 'skeptical']
DESCRIPTIONS = [
 'Freundliches asymmetrisches Lächeln; breite aufwärts geschwungene Brauen; runde Pupillen; je ein Lichtreflex; durchgehende kurze Unteraugenkurven.',
 'Unsicher/angespannt; links hochgezogene, rechts abgesenkte Braue; enger welliger offener Mund mit weißem Innenraum; Schraffuren und doppelte Lichtreflexe.',
 'Verliebt/begeistert; weiße Herzreflexe in schwarzen Pupillen, zusätzlicher runder Reflex; schwarzer offener Mund mit weißer Innenzunge; Schraffuren.',
 'Schelmisches Lächeln; ähnlich tense/love in Augen und Brauen, geschlossenes aufwärts gerichtetes Lächeln; Schraffuren.',
 'Verspielt mit herausgestreckter Zunge; stark geöffnete Augen mit entgegengesetzter Blickrichtung; dünnere Brauen; lange weiße Zunge mit schwarzem Rand und Mittellinie; zusätzliche Augenwinkelstriche.',
 'Skeptisch/selbstbewusst; gegensinnig gekrümmte Brauen; schräge obere Lider; nach innen gerichteter Blick; breites flaches Lächeln und kleiner Unterlippenstrich; Schraffuren.'
]

def files(directory=None):
    directory = Path(directory or ROOT / 'images')
    return sorted(p for p in directory.iterdir() if p.suffix.lower() in {'.png','.jpg','.jpeg','.webp'})

def inspect(directory=None):
    out=ROOT/'output/analysis';out.mkdir(parents=True,exist_ok=True)
    inventory=[]
    board=Image.new('RGB',(1200, len(files(directory))//2*360+360),'#e1e4e8')
    for i,p in enumerate(files(directory)):
        im=Image.open(p).convert('RGB')
        entry={'id':NAMES[i] if i<len(NAMES) else p.stem,'filename':p.name,'resolution':list(im.size),'mode':im.mode,
          'used':im.size==(1536,864),'expression':DESCRIPTIONS[i] if i<len(DESCRIPTIONS) else 'Unclassified: inspect manually',
          'source_sha256':__import__('hashlib').sha256(p.read_bytes()).hexdigest()}
        inventory.append(entry)
        thumb=ImageOps.contain(im,(590,320));x=i%2*600;y=i//2*360
        board.paste(thumb,(x,y+25));ImageDraw.Draw(board).text((x+10,y+5),f"{entry['id']}: {p.name}",fill='black')
    board.crop((0,0,1200,((len(inventory)+1)//2)*360)).save(out/'reference_contact_sheet.png')
    (out/'inventory.json').write_text(json.dumps(inventory,indent=2,ensure_ascii=False))
    lines=['# Bestandsaufnahme der sechs Referenzen','', 'Alle sechs Bilder sind isolierte Gesichtsillustrationen. Keine Roboterfotos vorhanden. Originaldateien bleiben unverändert.','',
      '| Pose | Datei | Auflösung | Ausdruck / Details |','|---|---|---|---|']
    for e in inventory:lines.append(f"| {e['id']} | {e['filename']} | {e['resolution']} | {e['expression']} |")
    lines += ['', '## Gemeinsame Formensprache', '',
      'Zwei unabhängig geformte breite Brauen; jeweils ein stark betontes oberes Lid mit äußerer Wimper, feine seitliche und untere Lidkurven; leicht elliptische schwarze Pupillen und weiße Reflexe. Eine kleine bogenförmige Nase. Zwei gefüllte Wangenbänder mit dünner werdender äußerer Spirale. Kein Gesichtsumriss.', '',
      'Die Wangenbänder, Brauen und Lidformen sind kontinuierlich deformierbar. Die diskreten Modi sind Unteraugendekoration (none/continuous/hatching/mixed), Reflex (round/heart) und Mundinnenraum (dark/white). Zunge und Akzentstriche sind optionale feste Komponenten. Sichtbarkeit wird weich als Deckkraft interpoliert; Landmark-IDs werden niemals umgeordnet.', '',
      '## Vorverarbeitung', '',
      'Gemeinsamer Ausschnitt [42, 56, 1492, 806] (x0,y0,x1,y1, rechte/untere Grenze exklusiv), 1450 × 750 Pixel. Dieser Ausschnitt liegt in allen sechs weißen Bildschirmen. Keine Rotation, kein Resize, kein Thresholding oder Glätten der gespeicherten Referenzen. Affine Transformation: x′=x−42, y′=y−56. Normalisierung: u=x′/1450, v=y′/750. Die Rastermasken für Metriken verwenden Grau<128; Details bleiben im RGB-Original erhalten.', '',
      '## Modellentscheidung vor Implementierung', '',
      'Semantische Anker auf den Mittellinien und an den Mund-/Augengrenzen. Interne Hermite-Tangenten und positive Breitenprofile erzeugen glatte gefüllte Bézier-Bänder. Die Spirale erhält eigene Anker für Bauch, Außenbogen, Scheitel und Spitze. Keine Referenzkonturen werden im Renderer gespeichert. Zusatzstriche werden aus festen Akzentankern und einer parametrierten Schraffurzone erzeugt. Alle sechs Posen teilen identische Komponenten und Landmark-Reihenfolge.'
    ]
    (ROOT/'docs/reference_analysis.md').write_text('\n'.join(lines),encoding='utf-8')
    return inventory

def preprocess(directory=None):
    inventory=inspect(directory);out=ROOT/'output/references';out.mkdir(parents=True,exist_ok=True)
    params={'schema_version':'1.0','crop':list(CROP),'canvas':{'width':1450,'height':750},'operations':['crop'],'denoising':False,'references':[]}
    for e,p in zip(inventory,files(directory)):
        if not e['used']:continue
        im=Image.open(p).convert('RGB').crop(CROP);im.save(out/f"{e['id']}.png")
        params['references'].append({**e,'prepared':f"output/references/{e['id']}.png",'affine_original_to_canvas':[[1,0,-42],[0,1,-56],[0,0,1]]})
    (out/'preprocess.json').write_text(json.dumps(params,indent=2,ensure_ascii=False))
    return params
