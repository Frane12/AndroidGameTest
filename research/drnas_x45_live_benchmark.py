#!/usr/bin/env python3
"""Paired real in-solver frozen model intervention vs identical native CDCL core.
All SAT outputs verified on ORIGINAL CNF; no ground truth used by solver.
Sources freshly generated with fixed seed distinct from X44 and X45 training.
NOT a competition test or claim of causal policy generalization.
"""
from __future__ import annotations
import argparse, hashlib, json, statistics, random, math, subprocess, time, pathlib, os, sys, collections
ROOT=pathlib.Path('drnas_x45_live_results')
sys.path.insert(0,'research')
import drnas_x42_1000 as G
import drnas_x44_counterfactual as OLD
EXE=pathlib.Path('build/drnas-x45-live')
CAP=2.0
CHECKPOINT=32
G.SAMPLE_HASH='drnas-live-model-fresh-source-20261113-v1'

def convert_model(model, dest):
    s=f"DRNAS_MODEL_V1 {len(model['features'])} {model['weights'][0]:.17g}\n"
    for name,c,sc,w in zip(model['features'],model['centers'],model['scales'],model['weights'][1:]):
        s+=f'{name} {c:.17g} {sc:.17g} {w:.17g}\n'
    dest.write_text(s)

def trial(src,mode,model_file):
    cmd=[str(EXE),src['path'],'--mode','core','--time',str(CAP),'--stats']
    if mode=='model':cmd+=['--checkpoint',str(CHECKPOINT),'--model-file',str(model_file)]
    t=time.monotonic()
    try:cp=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP+1.0)
    except subprocess.TimeoutExpired:
        return {'status':'UNKNOWN','wall_s':round(time.monotonic()-t,6),'par2_s':CAP*2,'model_applications':0,'too_long':True}
    wall=time.monotonic()-t
    if cp.returncode not in (0,10,20):raise RuntimeError(f'Exit {cp.returncode}; err {cp.stderr[-600:]}')
    if cp.returncode==20:raise RuntimeError('UNSAT contradicts planted witness: '+src['formula_id'])
    stats_line=next((s.split('X45_STATS ')[1] for s in cp.stderr.splitlines() if 'X45_STATS ' in s),None)
    if not stats_line:raise RuntimeError('Missing stats')
    stats=json.loads(stats_line)
    if cp.returncode==10:
        if not OLD.check_witness(pathlib.Path(src['path']),cp.stdout,src['nvars']):
            raise RuntimeError('Witness invalid: '+src['formula_id'])
    status='SAT_VERIFIED' if cp.returncode==10 and wall<=CAP else 'UNKNOWN'
    return {'status':status,'wall_s':round(wall,6),'par2_s':round(wall if status=='SAT_VERIFIED' else 2*CAP,6),
            'model_applications':stats.get('model_applications',0),'model_selected_sign':stats.get('model_selected_sign',0),
            'model_score':stats.get('model_score',0),'model_features_s':stats.get('model_features_s',0),
            'decisions':stats.get('decisions'), 'conflicts':stats.get('conflicts')}

def main():
    a=argparse.ArgumentParser();a.add_argument('--per-family',type=int,default=10);a.add_argument('--reps',type=int,default=2);
    a.add_argument('--seed',type=int,default=361);a.add_argument('--model-json',type=str,default=str(ROOT/'frozen_x44_legacy.json'));
    a.add_argument('--checkpoint',type=int,default=CHECKPOINT);a.add_argument('--cap',type=float,default=CAP)
    args=a.parse_args()
    globals()["CHECKPOINT"]=args.checkpoint;globals()["CAP"]=args.cap
    if hasattr(os,'sched_setaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    model=json.loads(pathlib.Path(args.model_json).read_text());model_file=ROOT/'converted_model.txt';convert_model(model,model_file)
    folder=ROOT/'fresh_source';folder.mkdir(exist_ok=True)
    # Source selection frozen independently of solver results.
    fams=[name for group in G.SPLITS.values() for name in group]
    sources=[G.gen_source(fam, args.seed+i, folder) for fam in fams for i in range(args.per_family)]
    assert len(sources)==len({x['sha256'] for x in sources})
    manifest=[{k:v for k,v in s.items() if k!='path'} for s in sources]
    (ROOT/'fresh_manifest.json').write_text(json.dumps(manifest,indent=2))
    rows=[]; totals=collections.defaultdict(lambda: {'PAR2_s':0.0,'SAT_verified':0,'E2E_s':0.0,'runs':0,'model_applications':0})
    out=ROOT/'fresh_trials.jsonl'
    with out.open('w') as fd:
        for j,src in enumerate(sources):
            for rep in range(args.reps):
                arms=['core','model'] if ((j+rep)%2==0) else ['model','core']
                rec={'family':src['family'],'sha256':src['sha256'],'idx':j,'rep':rep,'arms':{}}
                for arm in arms:
                    result=trial(src,arm,model_file)
                    rec['arms'][arm]=result
                    t=totals[arm];t['PAR2_s']+=result['par2_s'];t['E2E_s']+=result['wall_s'];t['SAT_verified']+=result['status']=='SAT_VERIFIED';t['runs']+=1;t['model_applications']+=result['model_applications']
                rows.append(rec);fd.write(json.dumps(rec,sort_keys=True)+'\n');fd.flush()
            if (j+1)%10==0:
                print('LIVE_PROGRESS',json.dumps({'sources':j+1,'out_of':len(sources),'totals':dict(totals)}),flush=True)
    for k,v in totals.items():v['PAR2_s']=round(v['PAR2_s'],6);v['E2E_s']=round(v['E2E_s'],6)
    paired=[r['arms']['model']['par2_s']-r['arms']['core']['par2_s'] for r in rows]
    by_formula=collections.defaultdict(list)
    for r,d in zip(rows,paired):by_formula[r['sha256']].append(d)
    formula_deltas=[statistics.mean(d) for d in by_formula.values()]
    rng=random.Random(282); boots=[]
    for _ in range(600):boots.append(statistics.mean(rng.choices(formula_deltas,k=len(formula_deltas))))
    boots.sort()
    final={'sources':len(sources),'seed':args.seed,'reps':args.reps,'cap_s':CAP,'checkpoint':CHECKPOINT,'model_kind':model.get('kind'),'totals':dict(totals),
           'model_vs_core_speedup_x':round(totals['core']['PAR2_s']/totals['model']['PAR2_s'],5),
           'model_vs_core_PAR2_reduction_pct':round(100*(1-totals['model']['PAR2_s']/totals['core']['PAR2_s']),4),
           'paired_model_minus_core_par2_s_bootstrap_ci_95pct':[round(boots[14],5),round(boots[584],5)],
           'model_faster_pairs':sum(x<-.001 for x in paired),'model_slower_pairs':sum(x>.001 for x in paired),'ties':sum(abs(x)<=.001 for x in paired),
           'limitations':'Generated SAT families historically studied, new unique source SHA. Frozen X45 combined28 trained only on train families; one model intervention at fixed checkpoint. Original SAT witnesses independently checked; not official SAT2024 or proof of broad policy generalization.'}
    (ROOT/'fresh_report.json').write_text(json.dumps(final,indent=2));print('LIVE_FINAL',json.dumps(final,sort_keys=True),flush=True)
if __name__=='__main__':main()