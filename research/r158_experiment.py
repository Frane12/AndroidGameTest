#!/usr/bin/env python3
"""R158 FED: raw verified R17 -> four OFFLINE ablations -> strict abstention.

No modification or promotion of any live solver. Test labels never train models.
R17 data are previously measured synthetic 3-SAT, NOT new/official/external SAT.
"""
import argparse
import collections
import csv
import hashlib
import itertools
import json
import math
import random
import statistics
import time
from pathlib import Path
from r158_features import (parse_dimacs, static_features, dynamic_features,
                           ENTROPY_KEYS, GRAPH_KEYS)

RUN_ID = 42094261835
ARTIFACT_ID = 13447042971
SOURCE_COMMIT = 'dc1a94520e90c75bb121203a273215a3c7b55308'
AGGREGATE_SHA = {
    'results.json': '5d026d6117d5c1de4483263245f28bddfd6b929ad2fdc4b137fd6ab5d11ec771',
    'formula_features.csv': '497580181e1c5823a6f01f895fbe915ddc1f83fff1cd961752618d606715a967',
    'paired.csv': '5e25636be2251e83639e3fa776f5695ef3df27d63e258c529bccc82e858d6de9',
    'native_decisions.csv': 'b3f746c25df4861f0cd637e10e84c273ffbd01386f7b46f7f763bfffdcafaaba',
}
FOLD_COUNTS = {'random3_development':60, 'community3_development':20,
               'random3_test':60, 'community3_test':20}
MODES = ('monitor','r11_2048_50','r13_rescue50','r14_dual50',
         'r16_live50','r16_live50_strict','r17_agree50','r17_guarded50',
         'original_kissat','stable_v1531')
ABLATIONS = {'A': (), 'B': ENTROPY_KEYS, 'C': GRAPH_KEYS,
             'D': ENTROPY_KEYS + GRAPH_KEYS}
ALPHA = 10.0
MIN_DISTINCT_SWITCH_FORMULAS = 10
THRESHOLD = 0.02
BOOTSTRAPS = 2000


def need(ok, message):
    if not ok:
        raise RuntimeError('R158_FAIL_CLOSED ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def csvrows(path):
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))


def number(value):
    x = float(value)
    need(math.isfinite(x), 'non-finite number')
    return x


def average(values):
    return sum(values)/len(values) if values else 0.


def verify_extract(aggregate, raw):
    for filename, digest in AGGREGATE_SHA.items():
        need((aggregate/filename).is_file() and sha(aggregate/filename) == digest,
             'aggregate SHA ' + filename)
    report = json.loads((aggregate/'results.json').read_text())
    need(report['protocol']=='R17-live-confidence-abstention-frozen-20261105-v1',
         'source protocol')
    need(report['formulas']==160 and report['attempts']==4800, 'source row total')
    need(report['sha_disjoint_from_R7_R16'] is True and
         report['paired_native_cores_verified'] is True and
         report['preintervention_mismatches']==0, 'source native audit')
    need(report['independent_unsat_certificate'] is False, 'independent UNSAT claim drift')
    source = report['source_shards']
    need(len(source)==16 and len({x['shard'] for x in source})==16,
         '16 pinned shards')
    formula_rows = csvrows(aggregate/'formula_features.csv')
    need(len(formula_rows)==160 and len({r['sha256'] for r in formula_rows})==160,
         'aggregate formula count')
    need(collections.Counter(r['fold'] for r in formula_rows)==collections.Counter(FOLD_COUNTS),
         'fold counts')
    by_sha = {r['sha256']:r for r in formula_rows}
    paired = csvrows(aggregate/'paired.csv')
    decisions = csvrows(aggregate/'native_decisions.csv')
    need(len(paired)==1440 and len(decisions)==960, 'paired/decision row totals')
    meas_hashes={};results=[];overheads=[]
    for info in sorted(source,key=lambda a:a['shard']):
        cat=info['shard'];directory=raw/('r17-'+cat)
        files={'source_sha256':directory/'manifest.json',
               'measurements_sha256':directory/'measurements.csv',
               'traces_sha256':directory/'traces.jsonl'}
        for key,path in files.items():
            need(path.is_file() and sha(path)==info[key], 'raw SHA '+cat+' '+key)
            meas_hashes[str(path.relative_to(raw))]=info[key]
        manifest=json.loads(files['source_sha256'].read_text())
        need(manifest['category']==cat and manifest['source_commit']==SOURCE_COMMIT,
             'source commit mismatch '+cat)
        need(manifest['runner']==info['runner'] and manifest['modes']==list(MODES)
             and manifest['repeats']==3 and len(manifest['cases'])==10,
             'source runner or frozen policy drift '+cat)
        measurements=csvrows(files['measurements_sha256'])
        traces=[json.loads(line) for line in files['traces_sha256'].read_text().splitlines()
                if line.strip()]
        need(len(measurements)==300 and len(traces)==300, 'raw incomplete '+cat)
        mk={(r['formula'],int(r['repeat']),r['mode']) for r in measurements}
        tk={(r['formula'],int(r['repeat']),r['mode']) for r in traces}
        need(len(mk)==300 and mk==tk, 'unpaired/duplicate trace '+cat)
        monitors=collections.defaultdict(list)
        for t in traces:
            if t['mode']=='monitor':
                monitors[t['formula']].append(t)
        for case in manifest['cases']:
            name=case['formula']
            need(Path(name).name==name, 'unsafe source path')
            cnf=directory/name
            need(cnf.is_file() and sha(cnf)==case['formula_sha256'], 'formula SHA '+name)
            original=by_sha.get(case['formula_sha256'])
            need(original and original['formula']==name and original['category']==cat,
                 'source/aggregate formula drift')
            need(int(original['seed'])==int(case['metadata']['seed']), 'seed mismatch')
            need(len(monitors[name])==3 and
                 sorted(int(t['repeat']) for t in monitors[name])==[0,1,2],
                 'missing monitor repeat')
            t0=time.perf_counter()
            graph=static_features(parse_dimacs(cnf))
            dynamics=dynamic_features(monitors[name])
            overheads.append((time.perf_counter()-t0)*1000)
            rec={k:original[k] for k in ('category','formula','sha256','seed','n','fold',
                                          'family','monitor','r17_guarded50','r17_agree50',
                                          'original_kissat','stable_v1531',
                                          'r17_guarded50_switched','r17_agree50_switched')}
            rec.update(graph)
            rec.update(dynamics)
            rec['source_run']=RUN_ID
            rec['source_commit']=SOURCE_COMMIT
            rec['runner']=info['runner']
            rec['source_class']='generated_R17_reused_not_official'
            results.append(rec)
            meas_hashes[str(cnf.relative_to(raw))]=case['formula_sha256']
    need(len(results)==160 and len({r['sha256'] for r in results})==160,
         'duplicate new feature row')
    need(collections.Counter(r['fold'] for r in results)==collections.Counter(FOLD_COUNTS),
         'feature fold drift')
    return report,sorted(results,key=lambda x:x['sha256']),meas_hashes,overheads


def outcome(row):
    a=number(row['monitor'])
    need(a>0., 'zero baseline PAR2')
    return max(-1.,min(1.,(a-number(row['r17_guarded50']))/a))


def linear_solve(matrix,values):
    size=len(values)
    augmented=[list(row)+[values[i]] for i,row in enumerate(matrix)]
    for j in range(size):
        pivot=max(range(j,size), key=lambda i:abs(augmented[i][j]))
        need(abs(augmented[pivot][j])>1e-12, 'singular ridge matrix')
        augmented[j],augmented[pivot]=augmented[pivot],augmented[j]
        scale=augmented[j][j]
        for col in range(j,size+1):
            augmented[j][col]/=scale
        for i in range(size):
            if i==j:continue
            fac=augmented[i][j]
            for col in range(j,size+1):
                augmented[i][col]-=fac*augmented[j][col]
    return [augmented[i][-1] for i in range(size)]


def fit(rows,cols):
    need(rows and all(r['fold'].endswith('_development') for r in rows),
         'fit input includes test labels')
    y=[outcome(r) for r in rows]
    intercept=average(y)
    if not cols:
        return dict(names=[],means=[],scales=[],weights=[],intercept=intercept)
    means=[average([number(r[k]) for r in rows]) for k in cols]
    scales=[max(1e-9, math.sqrt(average([(number(r[k])-means[j])**2 for r in rows])))
            for j,k in enumerate(cols)]
    x=[[(number(r[k])-means[j])/scales[j] for j,k in enumerate(cols)] for r in rows]
    p=len(cols)
    A=[[sum(row[i]*row[j] for row in x)+(ALPHA if i==j else 0)
        for j in range(p)] for i in range(p)]
    rhs=[sum(row[j]*(yy-intercept) for row,yy in zip(x,y)) for j in range(p)]
    return dict(names=list(cols),means=means,scales=scales,
                weights=linear_solve(A,rhs),intercept=intercept)


def predict(model,row):
    return model['intercept']+sum(w*(number(row[k])-m)/s for k,m,s,w in
       zip(model['names'],model['means'],model['scales'],model['weights']))


def fit_models(rows):
    dev=[r for r in rows if r['fold'].endswith('_development')]
    need(len(dev)==80 and len({r['sha256'] for r in dev})==80, 'leaking development labels')
    exposure={r['sha256'] for r in dev if int(r['r17_guarded50_switched'])>0}
    models={}
    for ablation,cols in ABLATIONS.items():
        full=fit(dev,cols)
        oof={}
        for fold in range(5):
            held=[r for r in dev if int(r['sha256'][:12],16)%5==fold]
            train=[r for r in dev if int(r['sha256'][:12],16)%5!=fold]
            need(train and held,'empty crossfit group')
            local=fit(train,cols)
            oof.update({r['sha256']:predict(local,r) for r in held})
        need(len(oof)==80,'missing crossfit formula')
        models[ablation]={
            'features':list(cols),'ridge':full,'dev_oof_predictions':oof,
            'intervened_dev_formulas':len(exposure),
            'promotion_allowed':False,
            'reason':('insufficient distinct intervened development formulas'
                      if len(exposure)<MIN_DISTINCT_SWITCH_FORMULAS else
                      'requires new external SHA-distinct prospective evaluation')}
    return models


def bootstrap(rows,policy,seed):
    rng=random.Random(seed)
    changes=[]
    for _ in range(BOOTSTRAPS):
        sub=[rng.choice(rows) for _ in rows]
        m=sum(float(r['monitor']) for r in sub)
        p=sum(float(r[policy]) for r in sub)
        changes.append(100*(m-p)/m if m else 0.)
    changes.sort()
    return [round(changes[int((len(changes)-1)*v)],5) for v in (.025,.975)]


def csvwrite(path,rows):
    if not rows:return
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def scatter(path,rows,x_field,y_field,title,diagonal=False):
    W,H=850,600
    values=[(float(row[x_field]),float(row[y_field])) for row in rows]
    min_x,max_x=min(v[0] for v in values),max(v[0] for v in values)
    min_y,max_y=min(v[1] for v in values),max(v[1] for v in values)
    if diagonal:
        lo=min(min_x,min_y,0.);hi=max(max_x,max_y)
        min_x=min_y=lo;max_x=max_y=hi
    if max_x-min_x<1e-12:max_x=min_x+1.
    if max_y-min_y<1e-12:max_y=min_y+1.
    def sx(x):return 65+690*(x-min_x)/(max_x-min_x)
    def sy(y):return 520-420*(y-min_y)/(max_y-min_y)
    circles=''.join('<circle cx="%.2f" cy="%.2f" r="3.6" fill="%s" opacity="0.65"/>'%
         (sx(x),sy(y),'#138f9e' if row['fold'].endswith('_development') else '#d99219')
         for (x,y),row in zip(values,rows))
    diag=('<path d="M%f %f L%f %f" fill="none" stroke="#666" stroke-dasharray="5 4"/>' %
          (sx(lo),sy(lo),sx(hi),sy(hi))) if diagonal else ''
    svg=('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 850 600">'
       '<rect width="850" height="600" fill="white"/>'
       '<text x="65" y="36" font-size="19">%s</text>'
       '<path d="M65 100 V520 H755" fill="none" stroke="#333"/>'
       '%s%s<text x="65" y="563" font-size="13">X: %s</text>'
       '<text x="390" y="563" font-size="13">Y: %s</text>'
       '<text x="520" y="65" font-size="12">cyan:dev ochre:test</text></svg>'%
       (title,diag,circles,x_field,y_field))
    path.write_text(svg)


def run(aggregate,raw,out):
    report,rows,raw_shas,feature_cost=verify_extract(aggregate,raw)
    models=fit_models(rows)
    changed=[dict(r) for r in rows]
    for r in changed:
        if r['fold'].endswith('_test'):
            r['monitor']='100000'
            r['r17_guarded50']='1'
    need(models==fit_models(changed),'heldout test labels leaked into model')
    out.mkdir(parents=True,exist_ok=True)
    pred=[]
    for row in rows:
        pred.append({**row,'observed_paired_gain_pct':100*outcome(row),
                     **{'predicted_gain_'+a:predict(m['ridge'],row)
                        for a,m in models.items()}})
    csvwrite(out/'r158_features.csv',pred)
    model={
       'protocol':'R158-FED-20261106-v1','mode':'OFFLINE_REPLAY_ONLY',
       'source_run':RUN_ID,'source_artifact':ARTIFACT_ID,'source_commit':SOURCE_COMMIT,
       'aggregate_sha256':AGGREGATE_SHA,'models':models,
       'train_formulas':80,'heldout_formulas':80,'new_external_formulas':0,
       'frozen_thresholds':{'ridge_alpha':ALPHA,'predicted_gain':THRESHOLD,
                            'minimum_intervention_formulas':MIN_DISTINCT_SWITCH_FORMULAS},
       'safe_action':'MONITOR_ABSTAIN','test_labels_used_for_fit':False,
       'live_solver_changed':False,'V15_3_1_changed':False,
       'independent_UNSAT_proof':False,
       'caveats':['all 160 sources are synthetic previously measured R17 CNFs',
                  'fractal number is a greedy box-cover proxy, not a proven dimension',
                  'entropy is measured over prefix checkpoint counters',
                  'no Lyapunov exponent or verified chaotic attractor',
                  'paired replay predictions are not live solver acceleration',
                  'feature extraction CPU cost is NOT included in replay PAR-2']}
    (out/'r158_models.json').write_text(json.dumps(model,sort_keys=True,indent=2)+'\n')
    paired=[]
    for fold in FOLD_COUNTS:
        sel=[r for r in rows if r['fold']==fold]
        total=sum(float(r['monitor']) for r in sel)
        for arm in ('r17_guarded50','r17_agree50','original_kissat','stable_v1531'):
            value=sum(float(r[arm]) for r in sel)
            paired.append({'fold':fold,'formulas':len(sel),'policy':arm,
             'monitor_PAR2_s':round(total,7),'policy_PAR2_s':round(value,7),
             'gain_percent':round(100*(total-value)/total,6),
             'bootstrap_formula_95_pct':json.dumps(bootstrap(sel,arm,len(arm)*1001+len(sel)))})
    csvwrite(out/'r158_paired.csv',paired)
    scatter(out/'r158_paired_scatter.svg',rows,'monitor','r17_guarded50',
            'R17 source paired replay: generated, not official',True)
    scatter(out/'r158_prediction_scatter.svg',pred,'predicted_gain_D',
            'observed_paired_gain_pct','R158 D ridge vs observed historical gain')
    audit={'source_run':RUN_ID,'source_artifact':ARTIFACT_ID,
       'source_commit':SOURCE_COMMIT,'source_sha256':raw_shas,
       'source_aggregate_sha256':AGGREGATE_SHA,
       'source_shards_verified':16,'source_attempts_reused':4800,
       'formulas':160,'development_formulas':80,'test_formulas':80,
       'fractal_proxy_valid':sum(bool(r['graph_box_valid']) for r in rows),
       'prefix_valid':sum(bool(r['prefix_valid']) for r in rows),
       'feature_cpu_ms_median':round(statistics.median(feature_cost),5),
       'feature_cpu_ms_max':round(max(feature_cost),5),
       'new_SAT_attempts':0,'new_live_decisions':0,
       'test_label_leakage_metamorphic_check':'PASS',
       'V15_3_1_changed':False,'deployment':'MONITOR_ABSTAIN',
       'model_SHA256':sha(out/'r158_models.json'),
       'features_SHA256':sha(out/'r158_features.csv'),
       'UNSAT_independent_certificate':False}
    (out/'r158_audit.json').write_text(json.dumps(audit,sort_keys=True,indent=2)+'\n')
    print('R158_FED_AUDIT_PASS '+json.dumps({k:audit[k] for k in (
      'formulas','source_attempts_reused','fractal_proxy_valid','prefix_valid',
      'new_SAT_attempts','deployment')}))
    return audit


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--aggregate',type=Path,required=True)
    ap.add_argument('--shards',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    run(args.aggregate,args.shards,args.out)