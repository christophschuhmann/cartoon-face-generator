"""Reproducible headless workflows and localhost editor."""
import argparse,json
from pathlib import Path
from .reference import ROOT

def main():
    parser=argparse.ArgumentParser(description='Parametric cartoon face rig · Phase 1');sub=parser.add_subparsers(dest='command',required=True)
    s=sub.add_parser('inspect_images');s.add_argument('--images',type=Path,default=ROOT/'images')
    s=sub.add_parser('preprocess');s.add_argument('--images',type=Path,default=ROOT/'images')
    s=sub.add_parser('fit_references');s.add_argument('--max-nfev',type=int,default=170);s.add_argument('--workers',type=int,default=3)
    s=sub.add_parser('render');s.add_argument('--pose',type=Path,required=True);s.add_argument('--output',type=Path,required=True);s.add_argument('--png',type=Path);s.add_argument('--width',type=int);s.add_argument('--height',type=int)
    sub.add_parser('evaluate')
    s=sub.add_parser('generate_dataset');s.add_argument('--count',type=int,default=100);s.add_argument('--seed',type=int,default=42);s.add_argument('--output',type=Path,default=ROOT/'output/synthetic_samples')
    s=sub.add_parser('interpolate');s.add_argument('--from',dest='source',type=Path,required=True);s.add_argument('--to',dest='target',type=Path,required=True);s.add_argument('--frames',type=int,default=60);s.add_argument('--output',type=Path,default=ROOT/'output/interpolations/custom')
    s=sub.add_parser('emotion');s.add_argument('--taxonomy',choices=['legacy','emonet'],default='legacy');s.add_argument('--seed',type=int);s.add_argument('--variation',type=float,default=.65);s.add_argument('--name',required=True);s.add_argument('--intensity',type=float,default=1);s.add_argument('--output',type=Path,required=True)
    s=sub.add_parser('validate');s.add_argument('--frames',type=int,default=32);s.add_argument('--count',type=int,default=100);s.add_argument('--seed',type=int,default=42)
    s=sub.add_parser('list_emotions')
    s=sub.add_parser('generate_emotions');s.add_argument('--variations',type=int,default=8);s.add_argument('--seed',type=int,default=42);s.add_argument('--output',type=Path,default=ROOT/'output/emonet')
    s=sub.add_parser('mix');s.add_argument('--a',required=True);s.add_argument('--b',required=True);s.add_argument('--weight',type=float,default=.5);s.add_argument('--seed',type=int);s.add_argument('--output',type=Path,required=True)
    s=sub.add_parser('validate_emotions');s.add_argument('--variations',type=int,default=8);s.add_argument('--frames',type=int,default=32);s.add_argument('--seed',type=int,default=42);s.add_argument('--output',type=Path,default=ROOT/'output/emonet')
    s=sub.add_parser('evaluate_reviews');s.add_argument('--input',type=Path,nargs='+',required=True);s.add_argument('--output',type=Path,default=ROOT/'output/emonet/human_reviews.json')
    s=sub.add_parser('serve');s.add_argument('--host',default='127.0.0.1');s.add_argument('--port',type=int,default=8766)
    sub.add_parser('list_social')
    s=sub.add_parser('social');s.add_argument('--name',required=True);s.add_argument('--seed',type=int);s.add_argument('--variation',type=float,default=.85);s.add_argument('--output',type=Path,required=True)
    s=sub.add_parser('generate_social');s.add_argument('--variations',type=int,default=4);s.add_argument('--seed',type=int,default=42);s.add_argument('--output',type=Path,default=ROOT/'output/social')
    s=sub.add_parser('build_dataset');s.add_argument('--per-expression',type=int,default=1000);s.add_argument('--ood-count',type=int,default=5000);s.add_argument('--seed',type=int,default=42);s.add_argument('--workers',type=int,default=16);s.add_argument('--output',type=Path,default=ROOT/'datasets/cartoon_landmarks_v2')
    s=sub.add_parser('export_rasters');s.add_argument('--dataset',type=Path,required=True);s.add_argument('--output',type=Path,required=True);s.add_argument('--split',choices=['train','validation','test'],default='train');s.add_argument('--limit',type=int,default=100);s.add_argument('--seed',type=int,default=42);s.add_argument('--width',type=int,default=768);s.add_argument('--height',type=int,default=400);s.add_argument('--format',choices=['png','jpg'],default='png');s.add_argument('--no-augment',action='store_true')
    a=parser.parse_args()
    if a.command=='inspect_images':
        from .reference import inspect
        print(json.dumps(inspect(a.images),indent=2,ensure_ascii=False))
    elif a.command=='preprocess':
        from .reference import preprocess
        print(json.dumps(preprocess(a.images),indent=2,ensure_ascii=False))
    elif a.command=='fit_references':
        from .fitting import fit_references
        fit_references(a.max_nfev,a.workers)
    elif a.command=='render':
        from .model import load_pose
        from .renderer import render_files
        render_files(load_pose(a.pose),a.output,a.png,a.width,a.height)
    elif a.command=='evaluate':
        from .evaluation import evaluate
        print(json.dumps(evaluate()['mean'],indent=2))
    elif a.command=='generate_dataset':
        from .dataset import generate_dataset
        r=generate_dataset(a.count,a.seed,a.output);print(json.dumps({k:v for k,v in r.items() if k!='samples'},indent=2))
    elif a.command=='interpolate':
        from .model import load_pose
        from .animation import interpolate
        print(json.dumps(interpolate(load_pose(a.source),load_pose(a.target),a.frames,a.output),indent=2))
    elif a.command=='emotion':
        from .expressions import emotion_pose
        from .model import save_pose
        from .renderer import render_files
        if a.taxonomy=='emonet':
            from .emotion_library import emotion_pose40
            p=emotion_pose40(a.name,a.seed,a.variation,a.intensity)
        else:p=emotion_pose(a.name,a.intensity)
        save_pose(p,a.output.with_suffix('.json'));render_files(p,a.output.with_suffix('.svg'),a.output.with_suffix('.png'))
    elif a.command=='validate':
        from .validation import validate_all
        print(json.dumps(validate_all(a.frames,a.count,a.seed),indent=2))
    elif a.command=='list_emotions':
        from .emotion_library import catalog
        for p in catalog()['profiles']:print(f'{p["id"]:02} {p["slug"]:<20} {p["label"]}')
    elif a.command=='generate_emotions':
        from .emotion_validation import generate_emotions
        r=generate_emotions(a.variations,a.seed,a.output);print(json.dumps({k:r[k] for k in ('category_count','variation_count','all_valid')},indent=2))
    elif a.command=='mix':
        from .animation import mix_targets
        from .model import save_pose
        from .renderer import render_files
        p=mix_targets(a.a,a.b,a.weight,a.seed);save_pose(p,a.output.with_suffix('.json'));render_files(p,a.output.with_suffix('.svg'),a.output.with_suffix('.png'))
    elif a.command=='validate_emotions':
        from .emotion_validation import generate_emotions,validate_mix_space
        r=generate_emotions(a.variations,a.seed,a.output);m=validate_mix_space(a.output,a.frames)
        print(json.dumps({'categories':40,'variations':r['variation_count'],'samples_valid':r['all_valid'],'pairs':m['pair_count'],'pairs_valid':m['all_geometry_valid']},indent=2))
    elif a.command=='serve':
        from .server import serve
        serve(a.host,a.port)
    elif a.command=='evaluate_reviews':
        from .emotion_reviews import evaluate_reviews
        r=evaluate_reviews(a.input,a.output)
        print(json.dumps({k:r[k] for k in ('judgment_count','target_agreement_rate','hidden_target_judgment_count','hidden_target_agreement_rate')},indent=2))
    elif a.command=='list_social':
        from .social_expressions import social_catalog
        for p in social_catalog()['profiles']:print(f'{p["id"]:02} {p["slug"]:<30} {p["label_de"]}')
    elif a.command=='social':
        from .social_expressions import social_pose
        from .model import save_pose
        from .renderer import render_files
        p=social_pose(a.name,a.seed,a.variation);save_pose(p,a.output.with_suffix('.json'));render_files(p,a.output.with_suffix('.svg'),a.output.with_suffix('.png'))
    elif a.command=='generate_social':
        from .social_validation import generate_social
        r=generate_social(a.variations,a.seed,a.output);print(json.dumps({k:r[k] for k in ('category_count','variation_count','all_valid')},indent=2))
    elif a.command=='build_dataset':
        from .large_dataset import build_dataset
        r=build_dataset(a.per_expression,a.ood_count,a.seed,a.workers,a.output)
        print(json.dumps({k:r[k] for k in ('record_count','compressed_bytes','logical_payload_bytes','all_records_validated')},indent=2))
    elif a.command=='export_rasters':
        from .augmentation import export_rasters
        print(json.dumps(export_rasters(a.dataset,a.output,a.split,a.limit,a.seed,a.width,a.height,not a.no_augment,a.format),indent=2))

if __name__=='__main__':main()
