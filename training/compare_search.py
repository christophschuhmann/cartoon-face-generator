"""Lock validation-only selection, then evaluate selected models on frozen tests."""
from pathlib import Path
import argparse,json,shutil
import numpy as np
import torch
from .extra_variants import evaluation_contract,file_hash
from .model import LandmarkNet
from .search import validation_score
from .train import evaluate,HoldoutDataset
from .visualize import visualize_predictions
from .evaluate_references import evaluate_references


def compare(search,cache,out,baseline,device='cuda:4'):
    search=Path(search);cache=Path(cache);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    plan=json.loads((search/'search_plan.json').read_text());contract=evaluation_contract(cache)
    assert contract==plan['evaluation_sha256']
    rows=[];normal_rows=[]
    for name,path in [('baseline',Path(baseline))]+[(r['name'],search/r['name']/'best.pt') for r in plan['candidates']]:
        if name!='baseline':
            completed=json.loads((path.parent/'candidate.json').read_text())
            assert completed['completed'] and not completed['test_evaluated']
            assert completed['config']['evaluation_sha256']==contract
        state=torch.load(path,map_location='cpu',weights_only=False);metrics=state['validation']
        rows.append({'candidate':name,'checkpoint':str(path),'checkpoint_sha256':file_hash(path),'epoch':state['epoch'],
            'score':validation_score(metrics),'validation':{k:metrics[k] for k in ('normal','clean','augmented','ood')}})
        precise=path if name=='baseline' else path.parent/'best_normal.pt'
        normal_state=torch.load(precise,map_location='cpu',weights_only=False)
        normal_rows.append({'candidate':name,'checkpoint':str(precise),'checkpoint_sha256':file_hash(precise),
            'epoch':normal_state['epoch'],'normal_nme':normal_state['validation']['normal']['nme_diagonal']})
    chosen=min(rows,key=lambda r:r['score']);precise=min(normal_rows,key=lambda r:r['normal_nme'])
    selection={'selection_rule':plan['selection'],'evaluation_sha256':contract,'chosen':chosen,'best_normal':precise,
        'candidates':rows,'test_used_for_selection':False,'selection_locked_before_test':True}
    lock=out/'selection_locked.json'
    if lock.exists() and json.loads(lock.read_text())!=selection:raise ValueError('Existing selection is different; no result will be overwritten')
    lock.write_text(json.dumps(selection,indent=2)+'\n')
    shutil.copy2(chosen['checkpoint'],out/'best.pt');shutil.copy2(precise['checkpoint'],out/'best_normal.pt')
    torch.set_num_threads(4);test=HoldoutDataset(cache/'test_heldout.npz');evaluations={}
    for label,path in [('robust',out/'best.pt'),('normal',out/'best_normal.pt')]:
        state=torch.load(path,map_location=device,weights_only=False);model=LandmarkNet().to(device);model.load_state_dict(state['model'])
        report,pred,vis=evaluate(model,test,device,128)
        evaluations[label]={'epoch':state['epoch'],'config':state['config'],'validation':state['validation'],'test':report}
        suffix='' if label=='robust' else '_normal'
        np.savez_compressed(out/f'test_predictions{suffix}.npz',xy=pred,visibility=vis,keys=test.data['keys'],conditions=test.data['conditions'])
        visualize_predictions(test.data,pred,vis,out/f'test_examples{suffix}.png')
        ood_mask=test.data['categories']>=100
        ood_data={key:value[ood_mask] for key,value in test.data.items()}
        # Use annotation visibility here: a missed landmark must remain visible
        # in the diagnostic rather than vanish with the model's own prediction.
        visualize_predictions(ood_data,pred[ood_mask],ood_data['visibility'],out/f'test_ood_examples{suffix}.png')
    external=evaluate_references(out/'best.pt',out)
    baseline_report=json.loads((Path(baseline).parent/'evaluation.json').read_text())
    result={'selection':selection,'baseline_test':{k:baseline_report['test'][k] for k in ('normal','clean','augmented','ood')},
        'models':evaluations,'external_reference_check':external,'evaluation_files_unchanged':evaluation_contract(cache)==contract,
        'scope':'Same authored cartoon identity and frozen v2 evaluation; no human emotion or arbitrary-video accuracy claim.'}
    (out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'evaluation.json').write_text(json.dumps(evaluations['robust'],indent=2)+'\n')
    summary={'chosen':chosen['candidate'],'best_normal':precise['candidate'],'evaluation_files_unchanged':True,
        'test':{label:{k:value['test'][k]['mean_error_px'] for k in ('normal','clean','augmented','ood')} for label,value in evaluations.items()},
        'external_reference_error':external['mean_error_px_mean_of_references']}
    print(json.dumps(summary,indent=2),flush=True);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--search',type=Path,default=Path('output/detector_search_v3'))
    p.add_argument('--cache',type=Path,default=Path('datasets/training_cache_v2'));p.add_argument('--output',type=Path,default=Path('output/detector_v3'))
    p.add_argument('--baseline',type=Path,default=Path('output/detector/best.pt'));p.add_argument('--device',default='cuda:4')
    a=p.parse_args();compare(a.search,a.cache,a.output,a.baseline,a.device)
