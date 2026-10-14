"""Rendered social-expression previews and protected-cue audits."""
from pathlib import Path
import json,hashlib
import numpy as np
from PIL import Image
from .reference import ROOT
from .social_expressions import social_catalog,social_pose,social_cue_checks
from .model import save_pose
from .renderer import render_files
from .dataset import audit_pose
from .emotion_validation import _sheet


def generate_social(variations=8,seed=42,out=None):
    if variations<1:raise ValueError('At least one variation is required')
    out=Path(out or ROOT/'output/social');out.mkdir(parents=True,exist_ok=True)
    (out/'archetypes').mkdir(exist_ok=True);(out/'variations').mkdir(exist_ok=True)
    rows=[];archetypes=[];families={}
    for profile in social_catalog()['profiles']:
        slug=profile['slug'];pre=out/'archetypes'/f'{profile["id"]:02}_{slug}'
        p=social_pose(slug);save_pose(p,pre.with_suffix('.json'));s=render_files(p,pre.with_suffix('.svg'),pre.with_suffix('.png'))
        valid=audit_pose(p,s)['valid'] and social_cue_checks(p)['passed']
        row={**profile,'archetype':str(pre.relative_to(out)),'archetype_valid':valid,'samples':[]}
        items=[];dest=out/'variations'/slug;dest.mkdir(exist_ok=True)
        for j in range(variations):
            sample_seed=seed+profile['id']*100000+j;p=social_pose(slug,sample_seed,.95);sample=dest/f'{j:04}_seed{sample_seed}'
            save_pose(p,sample.with_suffix('.json'));s=render_files(p,sample.with_suffix('.svg'),sample.with_suffix('.png'))
            area=float(np.mean(np.asarray(Image.open(sample.with_suffix('.png')).convert('L'))<128))
            checks=social_cue_checks(p);valid=audit_pose(p,s)['valid'] and checks['passed'] and .02<area<.18
            row['samples'].append({'seed':sample_seed,'pose':str(sample.with_suffix('.json').relative_to(out)),
              'png':str(sample.with_suffix('.png').relative_to(out)),'svg':str(sample.with_suffix('.svg').relative_to(out)),
              'valid':valid,'checks':checks,'foreground_fraction':area,'svg_sha256':hashlib.sha256(s.encode()).hexdigest()})
            items.append((slug+' / '+str(j+1),sample.with_suffix('.png')))
        _sheet(items,dest/'contact_sheet.png',cols=min(4,variations))
        item=(f'{profile["id"]:02} {slug}',pre.with_suffix('.png'));archetypes.append(item)
        families.setdefault(profile['family'],[]).extend([item]+items[:4]);rows.append(row)
    _sheet(archetypes,out/'archetypes/contact_sheet.png')
    for family,items in families.items():_sheet(items,out/'variations'/f'family_{family}.png')
    report={'catalog_id':social_catalog()['catalog_id'],'recipe_version':social_catalog()['recipe_version'],
      'category_count':60,'variation_count':60*variations,'variations_per_category':variations,'seed':seed,
      'all_valid':all(r['archetype_valid'] and all(s['valid'] for s in r['samples']) for r in rows),
      'semantic_recognition':'unmeasured; authored social performances, not extra EmoNet categories','categories':rows}
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');return report
