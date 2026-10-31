#!/usr/bin/env python3
"""DRNAS V12: retrospective, guarded structural router diagnosis.
LOCO means leave one official-runtime cohort out. The cohort, answer, and
official solver timings are NEVER given to the prediction function.
Counterfactual paired replay; no integrated binary and no future holdout.
"""
import argparse, hashlib, json, math
from pathlib import Path
from collections import Counter

FEATURES = ('log_vars','log_clauses','clause_var','avg_width','binary_frac',
            'ternary_frac','four_frac','polarity_imbalance','majority_coverage')
MODES = ('DRNAS_Legacy','DRNAS_NoLate','Kissat404','CaDiCaL301')
CAP=15.0

def check(condition, msg):
    if not condition: raise RuntimeError(msg)

def read(p):
    return json.loads(Path(p).read_text())

def load_audited(root):
    root=Path(root)
    p=root/'frozen/v103_manifest.json'
    m=read(p)
    check(m['protocol']=='DRNAS-v103-locked-router-20261031-v1','Wrong pinned source')
    check(len(m['cases'])==m['accepted_cases']==120,'Cases incomplete')
    check(hashlib.sha256(p.read_bytes()).hexdigest()==
          (root/'frozen/v103_manifest.sha256').read_text().split()[0], 'SHA mismatch')
    report=read(root/'v103_report.json')
    check(report['cases']==120 and report['attempts']==960,'Source audit incomplete')
    cases={c['id']:c for c in m['cases']}
    check(len(cases)==120 and len({c['sha256'] for c in cases.values()})==120,
          'Duplicate source data')
    for c in cases.values():
        check(all(f in c['features'] and math.isfinite(float(c['features'][f]))
                  for f in FEATURES),'Invalid input features')
    keyed={}
    for shard in range(6):
        folder=root/f'combined/v103-shard-{shard}/results'
        meta=read(folder/'meta.json')
        check(meta['shard']==shard and meta['ids']==
              [c['id'] for idx,c in enumerate(m['cases']) if idx%6==shard],
              'Wrong shard')
        for r in read(folder/'rows.json'):
            k=(r['id'],r['repetition'],r['mode'])
            check(k not in keyed and r['id'] in cases and
                  r['repetition'] in (0,1) and r['mode'] in MODES,'Bad/duplicate row')
            check(r['sha256']==cases[r['id']]['sha256'],'Wrong formula SHA')
            check(r['status'] in ('SAT','UNSAT','TIMEOUT') and not r['error'],'Solver error')
            check(r['status']=='TIMEOUT' or r['status']==cases[r['id']]['official_label'],
                  'Wrong result')
            check(0<=float(r['seconds'])<=CAP+.2,'Invalid timing')
            keyed[k]=r
    check(len(keyed)==960,'Missing observations')
    values={}
    for cid in cases:
        costs={};solved={}
        for mode in MODES:
            a=[keyed[(cid,rep,mode)] for rep in (0,1)]
            costs[mode]=sum(30 if r['status']=='TIMEOUT' else float(r['seconds'])
                            for r in a)/2
            solved[mode]=sum(r['status']!='TIMEOUT' for r in a)
        values[cid]=(costs,solved)
    check(sum(x[1]['Kissat404'] for x in values.values())==56,
          'Published audit does not match')
    return cases,values

def predict(training, query):
    """Frozen 5-NN threshold: at least 4/5 positive, >2s estimated benefit."""
    check(len(training)>=5,'Not enough training cases')
    span={f:max(max(float(c['features'][f]) for c,_ in training)-
                min(float(c['features'][f]) for c,_ in training),.05) for f in FEATURES}
    def distance(c):
        return math.sqrt(sum(((float(query['features'][f])-
                               float(c['features'][f]))/span[f])**2 for f in FEATURES))
    near=sorted(training,key=lambda pair:(distance(pair[0]),pair[0]['sha256']))[:5]
    w=[1/(.05+distance(c)) for c,_ in near]
    gains=[costs['Kissat404']-costs['DRNAS_Legacy'] for c,costs in near]
    estimate=sum(a*b for a,b in zip(w,gains))/sum(w)
    positive=sum(g>.5 for g in gains)
    choice='DRNAS_Legacy' if positive>=4 and estimate>=2 else 'Kissat404'
    return choice, round(estimate,4)

def aggregate(ids,values,choices):
    ids=list(ids)
    return {'solved':sum(values[cid][1][choices[cid]] for cid in ids),
            'total':len(ids)*2,
            'PAR2_s':round(sum(values[cid][0][choices[cid]] for cid in ids)/len(ids),6)}

def evaluate(root,out):
    cases,values=load_audited(root)
    cohorts=sorted({c['cohort'] for c in cases.values()})
    check(len(cohorts)==6,'Wrong number of validation folds')
    selection={};predictions=[]
    for cohort in cohorts:
        training=[(c,values[cid][0]) for cid,c in cases.items() if c['cohort']!=cohort]
        for cid,c in cases.items():
            if c['cohort']!=cohort: continue
            choice,estimate=predict(training,c)
            selection[cid]=choice
            predictions.append({'id':cid,'held_out_cohort':cohort,
                                'selected':choice,'estimated_gain_s':estimate})
    check(len(selection)==120,'Missing fold predictions')
    kissat={cid:'Kissat404' for cid in cases}
    legacy={cid:'DRNAS_Legacy' for cid in cases}
    oracle={cid:min(('Kissat404','DRNAS_Legacy'),key=lambda x:values[cid][0][x])
            for cid in cases}
    report={
        'protocol':'DRNAS-V12-LOCO-retrospective-v1',
        'scope':'Retrospective research only, not a future holdout or official SAT competition',
        'source':'V10.3 audited 120 CNF / 960 trials; mixed original runner CPU models',
        'rules':{'k':5,'min_positive':4,'positive_gain_s':.5,
                 'min_expected_gain_s':2,'fallback':'Kissat404'},
        'choices':dict(Counter(selection.values())),
        'overall':{'Kissat404':aggregate(cases,values,kissat),
                   'DRNAS_Legacy':aggregate(cases,values,legacy),
                   'V12_Guarded_LOCO':aggregate(cases,values,selection),
                   'Oracle_POSTHOC_NOT_DEPLOYABLE':aggregate(cases,values,oracle)},
        'cohorts':{cohort:{mode:aggregate([cid for cid,c in cases.items()
                            if c['cohort']==cohort],values,policy)
                     for mode,policy in [('Kissat404',kissat),
                                         ('DRNAS_Legacy',legacy),
                                         ('V12_Guarded_LOCO',selection)]}
                   for cohort in cohorts},
        'predictions':predictions}
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'v12_report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    lines=['# V12 Retrospective structural guard','',
           '**NOT a blind holdout, world record, or official ranking.**','',
           'V10.3 frozen 120 CNFs, 960 matched attempts, 15s cap, heterogeneous CPUs.',
           'Six held-out cohorts; scales fitted on training data only.',
           'Coho rt/difficulty, official answer and runtime are never router features.'.replace('Coho rt','Cohort'),
           'Posthoc oracle is an optimistic, nondeployable ceiling.','',
           '| Method | Solved | PAR2 s |','|---|---:|---:|']
    for k,r in report['overall'].items():
        lines.append(f"| {k} | {r['solved']}/{r['total']} | {r['PAR2_s']:.5f} |")
    lines += ['',f"V12 router choices: {report['choices']}",'',
              'Next: independent prospective evaluation on truly fresh inputs.']
    (out/'v12_report.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines),flush=True)

def selftest():
    def fake(i):
        return {'sha256':f'{i:064x}','features':{f:float(i%3)/10 for f in FEATURES}}
    training=[(fake(i),{'Kissat404':20,'DRNAS_Legacy':5}) for i in range(6)]
    check(predict(training,fake(11))[0]=='DRNAS_Legacy','Positive branch broken')
    training[0]=(fake(0),{'Kissat404':5,'DRNAS_Legacy':20})
    training[1]=(fake(1),{'Kissat404':5,'DRNAS_Legacy':20})
    check(predict(training,fake(11))[0]=='Kissat404','Fallback broken')
    print('V12_SELFTEST_PASS')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('cmd', choices=('selftest','audit'))
    parser.add_argument('--root',default='baseline')
    parser.add_argument('--out',default='results')
    args=parser.parse_args()
    if args.cmd=='selftest': selftest()
    else: evaluate(args.root,args.out)
