"""Aggregate exported viewer judgments against intended labels, without inventing reviews.

Agreement measures whether a viewer chose the author's intended category. It is
not the accuracy of a trained detector, nor proof of universal emotion semantics.
"""
from pathlib import Path
import csv
import json
from .emotion_library import catalog


def evaluate_reviews(paths,output=None):
    profiles=catalog()['profiles'];slugs=[p['slug'] for p in profiles]
    predicted=slugs+['unclear'];matrix=[[0]*41 for _ in slugs];judgments=[]
    sources=[]
    for path in paths:
        path=Path(path);data=json.loads(path.read_text())
        if data.get('taxonomy_id')!=catalog()['taxonomy_id']:
            raise ValueError(f'{path}: incompatible taxonomy')
        method=data.get('method','')
        if 'automated' in method.casefold():
            raise ValueError(f'{path}: automated smoke-test exports are not human reviews')
        sources.append({'file':str(path),'method':method})
        for row in data.get('reviews',[]):
            target=row['target_slug'];recognized=row['recognized_slug']
            if target not in slugs or recognized not in predicted:
                raise ValueError(f'{path}: unknown target or recognized category')
            confidence=row.get('confidence',3)
            if not isinstance(confidence,int) or isinstance(confidence,bool) or not 1<=confidence<=5:
                raise ValueError(f'{path}: confidence must be an integer from 1 to 5')
            matrix[slugs.index(target)][predicted.index(recognized)]+=1
            judgments.append({**row,'correct':target==recognized,
                # Do not infer blindness from the checkbox state at export time.
                'target_hidden':row.get('target_name_hidden_when_rated') is True})
    if not judgments:raise ValueError('No completed viewer judgments in the supplied files')
    hidden=[r for r in judgments if r['target_hidden']]
    per_class={}
    for slug in slugs:
        rows=[r for r in judgments if r['target_slug']==slug]
        per_class[slug]={'judgment_count':len(rows),
            'target_agreement_rate':sum(r['correct'] for r in rows)/len(rows) if rows else None}
    report={'taxonomy_id':catalog()['taxonomy_id'],'sources':sources,'judgment_count':len(judgments),
        'target_agreement_rate':sum(r['correct'] for r in judgments)/len(judgments),
        'hidden_target_judgment_count':len(hidden),
        'hidden_target_agreement_rate':sum(r['correct'] for r in hidden)/len(hidden) if hidden else None,
        'interpretation':'Viewer agreement with intended authored labels; no detector accuracy or expert validation inferred',
        'per_category':per_class,'confusion_matrix':{'rows_intended':slugs,'columns_recognized':predicted,'counts':matrix}}
    if output is not None:
        output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        with output.with_suffix('.csv').open('w',newline='') as handle:
            writer=csv.writer(handle);writer.writerow(['intended / recognized']+predicted)
            writer.writerows([slug]+counts for slug,counts in zip(slugs,matrix))
    return report
