"""Local, same-renderer debug UI, bound to localhost by default."""
import io
from flask import Flask,request,jsonify,send_file,send_from_directory
from .reference import ROOT,NAMES
from .model import load_pose,topology,validate_pose,refresh_states
from .renderer import render_svg,rasterize
from .expressions import EMOTIONS,emotion_pose,apply_controls,set_variant
from .emotion_library import catalog,emotion_pose40,mix_emotions
from .social_expressions import social_catalog,social_pose


def create_app():
    app=Flask(__name__);app.config['MAX_CONTENT_LENGTH']=2*1024*1024
    @app.get('/')
    def index():return send_from_directory(ROOT/'viewer','index.html')
    @app.get('/viewer/<path:filename>')
    def viewer(filename):return send_from_directory(ROOT/'viewer',filename)
    @app.get('/api/catalog')
    def api_catalog():return jsonify({'references':NAMES,'emotions':EMOTIONS,'emonet':catalog()['profiles'],'social':social_catalog()['profiles'],'topology':topology()})
    @app.get('/emotions')
    def emotion_gallery():return send_from_directory(ROOT/'viewer','emotions.html')
    @app.get('/api/emotion_manifest')
    def emotion_manifest():return send_file(ROOT/'output/emonet/manifest.json')
    @app.get('/emotion-assets/<path:filename>')
    def emotion_asset(filename):return send_from_directory(ROOT/'output/emonet',filename)
    @app.get('/social')
    def social_gallery():return send_from_directory(ROOT/'viewer','social.html')
    @app.get('/api/social_manifest')
    def social_manifest():return send_file(ROOT/'output/social/manifest.json')
    @app.get('/social-assets/<path:filename>')
    def social_asset(filename):return send_from_directory(ROOT/'output/social',filename)
    @app.get('/dataset-preview/<path:filename>')
    def dataset_preview(filename):return send_from_directory(ROOT/'output/dataset_previews',filename)
    @app.get('/downloads/webcam-mapper.zip')
    def webcam_download():return send_file(ROOT/'webcam_mapper/output/cartoon_webcam_mapper.zip',as_attachment=True,download_name='cartoon_webcam_mapper.zip')
    @app.get('/under-eye-assets/<path:filename>')
    def under_eye_asset(filename):return send_from_directory(ROOT/'output/under_eye',filename)
    @app.get('/refinement-assets/<path:filename>')
    def refinement_asset(filename):return send_from_directory(ROOT/'output/refinement/comparisons',filename)
    @app.get('/api/pose/<name>')
    def pose(name):
        if name not in NAMES:return jsonify(error='Unknown pose'),404
        return jsonify(load_pose(ROOT/f'poses/{name}.json'))
    @app.get('/reference/<name>.png')
    def reference(name):
        if name not in NAMES:return jsonify(error='Unknown reference'),404
        return send_file(ROOT/f'output/references/{name}.png')
    @app.post('/api/emotion')
    def emotion():
        data=request.get_json()
        if data.get('taxonomy')=='emonet':
            p=emotion_pose40(data['name'],data.get('seed'),float(data.get('variation',.65)),float(data.get('intensity',1)))
        elif data.get('taxonomy')=='social':
            p=social_pose(data['name'],data.get('seed'),float(data.get('variation',.85)))
        else:p=emotion_pose(data['name'],float(data.get('intensity',1)))
        return jsonify(pose=p,svg=render_svg(p))
    @app.post('/api/mix')
    def mix():
        from .animation import mix_targets
        data=request.get_json();p=mix_targets(data['a'],data['b'],float(data.get('weight',.5)),data.get('seed'),float(data.get('variation',.65)))
        return jsonify(pose=p,svg=render_svg(p))
    @app.post('/api/render')
    def render():
        data=request.get_json();p=validate_pose(data['pose'])
        if data.get('controls'):p=apply_controls(p,data['controls'])
        for n,v in data.get('variants',{}).items():
            if n not in p['variants']:raise ValueError('Unknown variant')
            set_variant(p,n,v)
        if p.get('recipe') and (data.get('manual_edit') or data.get('controls') or data.get('variants')):
            p['recipe']['modified_after_generation']=True
        refresh_states(p);return jsonify(svg=render_svg(p),pose=p)
    @app.post('/api/png')
    def png():
        p=validate_pose(request.get_json()['pose']);out=io.BytesIO();rasterize(render_svg(p)).save(out,format='PNG');out.seek(0)
        return send_file(out,mimetype='image/png',download_name='face.png')
    @app.errorhandler(ValueError)
    @app.errorhandler(KeyError)
    def invalid(error):return jsonify(error=str(error)),400
    return app


def serve(host='127.0.0.1',port=8766):create_app().run(host=host,port=port,debug=False)
