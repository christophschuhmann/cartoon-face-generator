"""Allowlisted standalone Git snapshot. No environments, credentials or datasets."""
from pathlib import Path
import json,shutil,re,argparse
from cartoon_face.reference import ROOT


def prepare(destination):
    dest=Path(destination);dest.mkdir(parents=True,exist_ok=True);files=set()
    for folder in ('src','viewer','poses','docs','tests','tools','training','images','.github'):
        files.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts)
    # Workflow activation needs a separate GitHub permission; retain the inert
    # tools/github_ci_template.yml, rather than publishing active workflow files.
    files={p for p in files if '.github/workflows' not in p.relative_to(ROOT).as_posix()}
    for name in ('README.md','CONTRIBUTING.md','AGENTS.md','LICENSE','pyproject.toml','uv.lock','.python-version','.gitignore'):
        p=ROOT/name
        if p.is_file():files.add(p)
    webcam=ROOT/'webcam_mapper'
    files.update(p for p in webcam.glob('*') if p.is_file() and p.suffix in ('.py','.md','.txt','.json'))
    files.add(webcam/'output/cartoon_webcam_mapper.zip')
    for folder in ('static','assets'):
        files.update(p for p in (webcam/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.html','.css','.js','.json','.md','.txt'))
    for folder in ('output/comparisons','output/reconstructions','output/references','output/under_eye','webcam_mapper/output/verification'):
        files.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.svg','.png','.json'))
    for name in ('output/README.md','output/evaluation.json','output/test_results.txt','output/editor/browser_test.json',
                 'output/editor/editor.png','output/emotions/contact_sheet.png','output/synthetic_samples/contact_sheet.png',
                 'output/refinement/report.json','output/emonet/visual_review.json'):
        p=ROOT/name
        if p.exists():files.add(p)
    for family in ('emonet','social'):
        base=ROOT/'output'/family
        for name in ('manifest.json','mixture_validation.json'):
            p=base/name
            if p.exists():files.add(p)
        files.update(p for p in (base/'archetypes').glob('*') if p.is_file())
        for directory in (base/'variations').glob('*'):
            if directory.is_dir():files.update(p for p in directory.glob('0000_*') if p.is_file())
            elif directory.suffix=='.png':files.add(directory)
        for directory in (base/'mixtures').glob('*'):
            if directory.is_dir():
                files.update(p for p in directory.glob('mixture.*') if p.is_file())
                contact=directory/'contact_sheet.png'
                if contact.is_file():files.add(contact)
            elif directory.suffix=='.png':files.add(directory)
    for folder in ('output/refinement/comparisons','output/dataset_previews'):
        files.update(p for p in (ROOT/folder).glob('*.png') if p.is_file())
    detector=ROOT/'output/detector'
    for name in ('config.json','history.json','evaluation.json','test_examples.png','external_references.json','external_references.png'):
        p=detector/name
        if p.exists():files.add(p)
    for folder in ('output/detector_v3','output/detector_search_v3'):
        base=ROOT/folder
        files.update(p for p in base.glob('*') if p.is_file() and p.suffix in ('.json','.png','.svg'))
        if folder.endswith('search_v3'):
            files.update(p for p in (base/'source').glob('*') if p.is_file() and p.suffix in ('.py','.json'))
            for directory in base.glob('*'):
                if directory.is_dir():files.update(p for p in directory.glob('*') if p.is_file() and p.name in ('config.json','history.json','candidate.json'))
    videos=ROOT/'video_experiments'
    files.update(p for p in videos.glob('*') if p.is_file() and p.suffix in ('.py','.sh','.txt','.md','.json'))
    files.update(p for p in (videos/'inputs').rglob('*') if p.is_file() and p.suffix in ('.png','.svg','.json','.txt'))
    # MP4s and the large collection of decoded frames belong in release ZIPs.
    files.update(p for p in (videos/'output').rglob('*.json') if p.is_file())
    pattern=re.compile(rb'(?:ghp_|hf_)[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----')
    total=0
    for file in sorted(files):
        relative=file.relative_to(ROOT)
        if file.stat().st_size>25_000_000:raise ValueError(f'Unexpected large Git source file: {relative}')
        data=file.read_bytes()
        if pattern.search(data):raise ValueError(f'Credential pattern found in publication candidate: {relative}')
        target=dest/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target);total+=len(data)
    report={'snapshot':str(dest),'source_files':len(files),'bytes':total,'datasets_included':False,'environments_included':False,'credential_scan_passed':True}
    (ROOT/'output/github_snapshot.json').write_text(json.dumps(report,indent=2)+'\n');return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(prepare(a.output),indent=2))
