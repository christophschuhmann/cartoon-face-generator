"""Real Chromium smoke test: drag, sliders, variants, overlay, exports and reset."""
import json,threading
from pathlib import Path
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from cartoon_face.server import create_app
from cartoon_face.reference import ROOT

server=make_server('127.0.0.1',0,create_app(),threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
out=ROOT/'output/editor';out.mkdir(exist_ok=True);errors=[]
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1540,'height':1080})
  page.on('pageerror',lambda e:errors.append(str(e)));page.goto(f'http://127.0.0.1:{server.server_port}')
  page.wait_for_selector('#drawing svg');assert page.locator('#landmarks circle').count()>65
  with page.expect_response('**/api/render'):page.locator('#left_eye_openness').evaluate('(e)=>{e.value=.5;e.dispatchEvent(new Event("input",{bubbles:true}))}')
  page.wait_for_timeout(100)
  circle=page.locator('circle[data-name="right_moustache_curl_tip"]');box=circle.bounding_box()
  with page.expect_response('**/api/render'):
   page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down();page.mouse.move(box['x']+18,box['y']-8,steps=5);page.mouse.up()
  page.locator('#overlayOpacity').evaluate('(e)=>{e.value=.4;e.dispatchEvent(new Event("input"))}');assert page.locator('#overlay').is_visible()
  page.locator('select[data-name="left_under_eye"]').select_option('mixed');page.wait_for_timeout(150)
  for button,name in [('jsonExport','pose.json'),('svgExport','face.svg'),('pngExport','face.png')]:
   with page.expect_download() as download:page.locator('#'+button).click()
   download.value.save_as(out/name)
  p=json.loads((out/'pose.json').read_text());assert len(p['keypoints'])==101
  page.locator('#emotion').select_option('surprised')
  with page.expect_response('**/api/emotion'):page.locator('#emotionLoad').click()
  page.wait_for_timeout(150);page.locator('#showPoints').uncheck();page.locator('#overlayOpacity').evaluate('(e)=>{e.value=0;e.dispatchEvent(new Event("input"))}')
  page.screenshot(path=str(out/'editor.png'),full_page=True)
  with page.expect_response('**/api/pose/smile'):page.locator('#reset').click()
  page.wait_for_timeout(100);assert page.locator('#left_eye_openness').input_value()=='1'
  # The browser uses the same complete 101-point pose contract for all forty
  # classes, seeded variations and parameter mixtures.
  page.locator('#emotion').select_option('emonet:anger')
  with page.expect_response('**/api/emotion') as loaded:
   page.locator('#emotionLoad').click()
  archetype=loaded.value.json()['pose'];assert archetype['emotion']['category_id']==32
  page.wait_for_timeout(180)
  page.locator('#emotionSeed').fill('42')
  with page.expect_response('**/api/emotion') as varied:page.locator('#variationLoad').click()
  variation=varied.value.json()['pose'];assert variation['recipe']['seed']==42
  page.wait_for_timeout(180);assert page.locator('#emotionSeed').input_value()=='43'
  assert archetype['keypoints']!=variation['keypoints']
  page.screenshot(path=str(ROOT/'output/emonet/editor.png'))
  page.locator('#mixEmotion').select_option('sadness')
  page.locator('#mixWeight').evaluate('(e)=>e.value=.24')
  with page.expect_response('**/api/mix') as mixed:page.locator('#mixLoad').click()
  mixture=mixed.value.json()['pose'];assert mixture['emotion']['weights'][27]==.24
  assert mixture['emotion']['weights'][31]==.76
  page.wait_for_timeout(150)
  page.goto(f'http://127.0.0.1:{server.server_port}/emotions')
  page.wait_for_selector('#cards .card');assert page.locator('#cards .card').count()==40
  page.wait_for_function('document.querySelector(".card img").naturalWidth>0')
  page.screenshot(path=str(ROOT/'output/emonet/gallery.png'))
  page.locator('#hideTargets').check();assert not page.locator('.card h2').first.is_visible()
  page.locator('.card select[aria-label="Erkannte Emotion"]').first.select_option('amusement')
  with page.expect_download() as download:page.locator('#exportReviews').click()
  # This verifies JSON export, and is explicitly excluded from human evidence.
  fixture=json.loads(Path(download.value.path()).read_text())
  fixture['method']='automated UI smoke-test example; not a human review'
  assert fixture['reviews'][0]['target_name_hidden_when_rated'] is True
  (out/'automated_review_fixture.json').write_text(json.dumps(fixture,indent=2)+'\n')
  page.locator('#sampleChoice').select_option('variation')
  assert '0 / 40' in page.locator('#galleryStatus').inner_text()
  page.goto(f'http://127.0.0.1:{server.server_port}/social')
  page.wait_for_selector('#cards .card');assert page.locator('#cards .card').count()==60
  page.wait_for_function('document.querySelector(".card img").naturalWidth>0')
  page.screenshot(path=str(ROOT/'output/social/gallery.png'))
  page.locator('#family').select_option('playful');assert page.locator('#cards .card').count()==10
  page.locator('#family').select_option('');page.locator('#search').fill('Monster');assert page.locator('#cards .card').count()==1
  page.locator('.card a').first.click();page.wait_for_selector('#drawing svg')
  page.wait_for_function('document.getElementById("emotionMeaning").textContent.includes("Sozialer Ausdruck")')
  assert page.locator('#emotion').input_value()=='social:mock_monster'
  page.locator('#emotionSeed').fill('314')
  with page.expect_response('**/api/emotion') as social_varied:page.locator('#variationLoad').click()
  social=social_varied.value.json()['pose'];assert social['expression']['category_id']==9
  assert len(social['expression']['weights'])==60 and len(social['keypoints'])==101
  page.wait_for_timeout(150);assert page.locator('#emotionSeed').input_value()=='315'
  page.locator('#mixEmotion').select_option('social:knowing_wink')
  with page.expect_response('**/api/mix') as social_mixed:page.locator('#mixLoad').click()
  assert len(social_mixed.value.json()['pose']['expression']['weights'])==60
  page.wait_for_timeout(150)
  with page.expect_response('**/api/render') as under_eye:
   page.locator('#left_underBlend').evaluate('(e)=>{e.value=.4;e.dispatchEvent(new Event("input",{bubbles:true}))}')
  updated=under_eye.value.json()['pose'];assert updated['rig']['left_hatching']['foldness']==.4
  assert updated['geometry']['under_eye_transition']=='stroke_bank_v1'
  page.wait_for_timeout(150);page.screenshot(path=str(ROOT/'output/social/editor.png'))
  browser.close()
finally:server.shutdown()
assert not errors,errors
(out/'browser_test.json').write_text(json.dumps({'passed':True,'errors':errors,'checks':['load','slider','drag','variant','overlay','JSON export','SVG export','PNG export','legacy emotion','reset','40-category archetype','seeded variation','mixture','40-card gallery','hidden-target review export','review sample switching','60-card social gallery','family and text filters','gallery-to-editor social load','social seeded variation','social mixture']},indent=2))
print('Chromium editor smoke test passed')
