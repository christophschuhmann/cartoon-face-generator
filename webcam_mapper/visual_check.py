"""Render synthetic gesture comparisons and all 100 authored archetypes.

No webcam access. Headless browser is only an SVG test renderer.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from .mapping import controls_from_signals, controls_to_pose
from .expressions import library, archetype_pose
from cartoon_face.renderer import render_svg


def main():
    out = Path(__file__).parent / 'output/verification'
    out.mkdir(parents=True, exist_ok=True)
    samples = [
        ('Neutral', {}), ('Brauen leicht angehoben', {'browInnerUp':.25,'browOuterUpLeft':.3,'browOuterUpRight':.3}),
        ('Eine Braue hoch, andere runter', {'browOuterUpLeft':.8,'browDownRight':.7}),
        ('Zorn: Brauen + Mundwinkel', {'browDownLeft':.8,'browDownRight':.8,'mouthFrownLeft':.7,'mouthFrownRight':.7}),
        ('Kopf heben', {'headPitch':.6}), ('Kopf senken', {'headPitch':-.6}),
        ('Mundwinkel gesenkt', {'mouthFrownLeft':.6,'mouthFrownRight':.6}),
        ('Linkes Auge zwinkert', {'eyeBlinkLeft':.8}), ('Blick nach oben / verdeckte Pupillen', {'eyeLookUpLeft':.85,'eyeLookUpRight':.85}),
        ('Schielen', {'eyeLookInLeft':.8,'eyeLookInRight':.8}),
        ('Unabhängige Blickrichtungen', {'eyeLookOutLeft':.8,'eyeLookDownLeft':.7,'eyeLookInRight':.7,'eyeLookUpRight':.7}),
        ('Zunge + Zwinkern', {'tongueOut':.85,'eyeBlinkRight':.85,'mouthSmileLeft':.7}), ('Leises Sprechen', {'jawOpen':.10}),
        ('Kopf nach links', {'headYaw':-.65}), ('Kopf nach rechts', {'headYaw':.65}), ('Drehen + Neigen', {'headYaw':.6,'headPitch':.3,'headRoll':-.3}),
    ]
    css = '<style>body{font:14px system-ui;margin:24px;background:#f4f3ed;color:#203a32}h1{font-size:24px}main{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}article{background:white;border-radius:16px;padding:16px;border:1px solid #dde4da}h2{font-size:13px;margin:0 0 10px}svg{width:100%;height:auto}</style>'
    def page(title, tiles, columns=3):
        return '<!doctype html><meta charset="utf-8">'+css+f'<h1>{title}</h1><main style="grid-template-columns:repeat({columns},1fr)">' + ''.join('<article><h2>'+label+'</h2>'+svg+'</article>' for label,svg in tiles)+'</main>'
    gestures = [(label, render_svg(controls_to_pose(controls_from_signals(signals)), live=True, id_prefix=f'g{i}-')) for i,(label, signals) in enumerate(samples)]
    (out/'gestures_v2.html').write_text(page('Synthetische Bewegungstests · Mimikstudio 2', gestures), encoding='utf-8')
    templates = [(item['label'], render_svg(archetype_pose(slug), live=True, id_prefix=f'a{i}-')) for i,(slug,item) in enumerate(library().items())]
    (out/'archetypes_100.html').write_text(page('40 EmoNet-Archetypen + 60 soziale Cartoon-Ausdrücke', templates, 5), encoding='utf-8')
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        view = browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
        for name in ('gestures_v2', 'archetypes_100'):
            view.goto((out/(name+'.html')).resolve().as_uri())
            view.screenshot(path=str(out/(name+'.png')),full_page=True)
        browser.close()
    print(json.dumps({'synthetic_gestures':len(gestures),'archetypes':len(templates),'output':str(out)}))


if __name__ == '__main__': main()
