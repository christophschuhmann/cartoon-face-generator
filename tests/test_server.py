import io
from PIL import Image
from cartoon_face.server import create_app

def test_emonet_api_uses_the_shared_renderer_and_validates_weights():
    from cartoon_face.emotion_library import emotion_pose40
    from cartoon_face.renderer import render_svg
    c=create_app().test_client()
    assert len(c.get('/api/catalog').json['emonet'])==40
    r=c.post('/api/emotion',json={'taxonomy':'emonet','name':'anger','seed':42,'variation':.85})
    assert r.status_code==200 and r.json['svg']==render_svg(emotion_pose40('anger',42,.85))
    assert c.post('/api/emotion',json={'taxonomy':'emonet','name':'unknown'}).status_code==400
    mixed=c.post('/api/mix',json={'a':'gratitude','b':'affection','weight':.4})
    assert mixed.status_code==200 and mixed.json['pose']['emotion']['weights'][5]==.4
    changed=c.post('/api/render',json={'pose':r.json['pose'],'controls':{'smile':.1}})
    assert changed.json['pose']['recipe']['modified_after_generation'] is True
    invalid=r.json['pose'];invalid['emotion']['weights']=[1,0]
    assert c.post('/api/render',json={'pose':invalid}).status_code==400
from cartoon_face.renderer import render_svg

def test_editor_and_cli_use_identical_renderer():
    client=create_app().test_client();p=client.get('/api/pose/smile').json
    r=client.post('/api/render',json={'pose':p})
    assert r.status_code==200
    assert r.json['svg']==render_svg(r.json['pose'])
    assert client.get('/reference/../README.png').status_code in (404,308)
    assert client.get('/api/pose/unknown').status_code==404
    bad=client.post('/api/render',json={'pose':{}})
    assert bad.status_code==400
    png=client.post('/api/png',json={'pose':p});assert png.status_code==200
    assert Image.open(io.BytesIO(png.data)).size==(1450,750)


def test_api_controls_and_details_keep_all_ids():
    c=create_app().test_client();p=c.get('/api/pose/tongue').json
    r=c.post('/api/render',json={'pose':p,'controls':{'left_eye_openness':.1,'smile':.2},'variants':{'right_under_eye':'none'}})
    assert r.status_code==200
    assert len(r.json['pose']['keypoints'])==101
    assert r.json['pose']['rig']['right_hatching']['opacity']==0
