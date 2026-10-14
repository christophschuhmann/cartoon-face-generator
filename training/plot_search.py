"""Standalone plots of actual validation histories; never read test outcomes."""
from pathlib import Path
import argparse,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot(search,baseline):
    search=Path(search);old=json.loads(Path(baseline).read_text())['validation']
    plan=json.loads((search/'search_plan.json').read_text())
    fig,axes=plt.subplots(1,3,figsize=(15,4.4),layout='constrained')
    baseline_values=[old['normal']['mean_error_px'],old['ood']['mean_error_px'],
        .25*old['clean']['mean_error_px']+.25*old['augmented']['mean_error_px']+.5*old['ood']['mean_error_px']]
    for ax,value in zip(axes,baseline_values):ax.axhline(value,color='#777777',ls='--',lw=1,label='Baseline (15 epochs)')
    for spec in plan['candidates']:
        history=search/spec['name']/'history.json'
        if not history.exists():continue
        rows=json.loads(history.read_text());epochs=[0]+[r['epoch'] for r in rows]
        series=[[baseline_values[0]]+[r['validation']['normal']['mean_error_px'] for r in rows],
            [baseline_values[1]]+[r['validation']['ood']['mean_error_px'] for r in rows],
            [baseline_values[2]]+[.25*r['validation']['clean']['mean_error_px']+
                .25*r['validation']['augmented']['mean_error_px']+.5*r['validation']['ood']['mean_error_px'] for r in rows]]
        for ax,data in zip(axes,series):ax.plot(epochs,data,lw=1.6,label=spec['name'])
    axes[0].axhline(.5,color='#b44',ls=':',lw=1,label='Normal-quality guardrail')
    for ax,title in zip(axes,['Normal validation','Extreme OOD validation','Balanced validation score']):
        ax.set_title(title);ax.set_xlabel('Additional fine-tuning epochs');ax.set_ylabel('Mean error (pixels, 320 x 192)');ax.grid(alpha=.2)
    axes[2].legend(fontsize=8);fig.suptitle('Frozen validation set: test outcomes are not used for model selection')
    fig.savefig(search/'validation_curves.png',dpi=160);fig.savefig(search/'validation_curves.svg');plt.close(fig)
    svg=search/'validation_curves.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--search',type=Path,default=Path('output/detector_search_v3'))
    p.add_argument('--baseline',type=Path,default=Path('output/detector/evaluation.json'))
    a=p.parse_args();plot(a.search,a.baseline)
