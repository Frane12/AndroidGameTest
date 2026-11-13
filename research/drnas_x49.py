#!/usr/bin/env python3
"""X4.9: sealed train/validation/holdout with zero-probe CDCL predictor.

Original CNF is evaluated unchanged. Matched-state continuation labels train the
predictor; only actual end-to-end validation selects a gate. Native CORE remains
the deployment fallback. SAT is independently witness-verified; this pilot
contains generated SAT only, not a claim about official industrial benchmarks.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import random
import time

import numpy as np
import drnas_x47 as X
from x49_models import NF, fit, predict, choose, write_model

NAMESPACE = 'X49-ZERO-PROBE-v1'
DECISION = 16
WORK_LIMIT = 100000
THRESHOLDS = (0.5, 1.5, 2.5)
MIN_CONFLICTS = (0, 4)
ARMS = ('core', 'cheap', 'cheap_sham')
CHEAP_FEATURES = (
    'log_n','log_original_clause_density','assigned_fraction','depth_fraction',
    'log_conflicts','log_learnt','log_decisions','log_propagations',
    'conflicts_per_decision','propagations_per_decision','learnt_per_conflict',
    'restarts_per_conflict','signed_initial_polarity_balance','log_positive_occ',
    'log_negative_occ','log_binary_degree','binary_density','log_vsids_activity',
    'log_restarts','log_trail','decision_level','implied_fraction',
    'log_original_clauses','log_total_clauses','learnt_clause_fraction',
    'conflicts_per_propagation','decisions_per_assignment',
    'restarts_per_decision','baseline_literal_sign','stored_phase_positive')
assert NF == len(CHEAP_FEATURES)
X.DECISION = DECISION
X.WORK_LIMIT = WORK_LIMIT


def emit(tag, data):
    X.emit('X49_' + tag, data)


def save(path, data):
    X.save(path, data)


def series(candidates, core, source):
    vals = [candidates[s]['PAR2'] for s in source]
    ref = [core[s]['PAR2'] for s in source]
    return X.effect(ref, vals, draws=1500)


def cheap_pair(binary, path, case):
    # Deterministic matched-state branch polarity A/B, no shadow propagation.
    order=(False,True) if case['index']%2 else (True,False)
    rs={flip:X.run(binary,path,case,'collect_cheap',0,flip=flip,work_limit=WORK_LIMIT) for flip in order}
    b,f=rs[False],rs[True]
    row={k:case[k] for k in ('family','index','sha256','n')}
    row.update(base=b,flip=f,label=None,features=None,exclusion='checkpoint_not_reached')
    assert b['reached']==f['reached']
    if not b['reached']:return row
    for key in ('pre_state_digest','baseline_literal','prefix_conflicts','prefix_learnt','prefix_propagations'):
        assert b['pre'][key]==f['pre'][key],(case['sha256'],key)
    assert b['policy']['features']==f['policy']['features']
    assert b['pre']['actual_literal']==-f['pre']['actual_literal']
    assert b['policy']['probe_inspections']==f['policy']['probe_inspections']==0
    row['features']=b['policy']['features']
    if b['verified'] and f['verified']:
        row['label']=float(np.log1p(b['remaining_propagations'])-np.log1p(f['remaining_propagations']))
        row['exclusion']=None
    else:row['exclusion']='work_censored'
    return row


def discrimination(model, rows):
    rr=[r for r in rows if r['label'] is not None and abs(r['label'])>.1]
    if not rr:return dict(n=0,auc=None,auc_formula95=None,balanced_accuracy=None,accepted_flips=0)
    lab=np.asarray([r['label']>0 for r in rr])
    score=np.asarray([predict(model,r['features'])[0] for r in rr])
    allowed=np.asarray([r['base']['pre']['prefix_conflicts']>=model['min_conflicts'] for r in rr])
    flip=np.asarray([bool(a and choose(model,r['features'])) for r,a in zip(rr,allowed)])
    def auc(y,s):
        pos=s[y];neg=s[~y]
        return float(np.mean((pos[:,None]>neg)+0.5*(pos[:,None]==neg))) if len(pos) and len(neg) else None
    val=auc(lab,score)
    rng=np.random.default_rng(491315);bs=[]
    for _ in range(1000):
        ids=rng.integers(len(rr),size=len(rr));a=auc(lab[ids],score[ids])
        if a is not None:bs.append(a)
    bal=float((flip[lab].mean()+1-flip[~lab].mean())/2) if lab.any() and (~lab).any() else None
    return dict(n=len(rr),auc=val,auc_formula95=np.quantile(bs,[.025,.975]).tolist() if bs else None,
                balanced_accuracy=bal,accepted_flips=int(flip.sum()),gate_eligible=int(allowed.sum()),
                conditional_on_completed_nontrivial_pairs=True)


def collect_pairs(binary, manifest, workfile, path):
    rows = []
    with path.open('w') as out:
        for i, case in enumerate(manifest):
            workfile.write_text(case['source'])
            r = cheap_pair(binary, workfile, case)
            if r['features'] is not None and len(r['features']) != NF:
                raise AssertionError('X49 native feature schema mismatch')
            rows.append(r)
            out.write(json.dumps(r, sort_keys=True) + '\n')
            if (i+1) % 40 == 0:
                emit('COLLECT', {'done':i+1, 'total':len(manifest),
                                'labeled':sum(x['label'] is not None for x in rows)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--binary', type=Path, default=Path('build/drnas-x49'))
    ap.add_argument('--out', type=Path, default=Path('x49_results'))
    ap.add_argument('--per-family', type=int, default=40)
    ap.add_argument('--cap', type=float, default=0.8)
    ap.add_argument('--repeats', type=int, default=3)
    args = ap.parse_args()
    if args.per_family < 24 or args.cap < .1 or args.repeats < 2:
        raise ValueError('benchmark too small for prespecified protocol')
    args.out.mkdir(parents=True, exist_ok=False)
    binary = args.binary.resolve()
    if hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    started = time.perf_counter()
    cohorts = {split:[X.make_case(f, i, namespace=NAMESPACE+':'+split)
                      for f in families for i in range(args.per_family)]
               for split, families in [('train', X.TRAIN),
                                        ('validation', X.VALIDATION),
                                        ('holdout', X.HOLDOUT)]}
    source_ids = [x['sha256'] for rows in cohorts.values() for x in rows]
    assert len(source_ids) == len(set(source_ids))
    assert not (set(X.TRAIN) & set(X.VALIDATION))
    assert not ((set(X.TRAIN)|set(X.VALIDATION)) & set(X.HOLDOUT))
    save(args.out/'manifest.json',
         {s:[{k:c[k] for k in ('sha256', 'family', 'index', 'n')}
             for c in cc] for s, cc in cohorts.items()})
    save(args.out/'protocol.json',
         {'namespace':NAMESPACE, 'decision':DECISION, 'work_limit':WORK_LIMIT,
          'features':list(CHEAP_FEATURES),'probe_budget':0,
          'gate_min_conflicts':MIN_CONFLICTS, 'thresholds':THRESHOLDS,
          'train':X.TRAIN, 'validation':X.VALIDATION, 'holdout':X.HOLDOUT,
          'cap_s':args.cap, 'repeats':args.repeats,
          'validation_acceptance':'paired formula bootstrap lower95 > 3% and no solved regression; two thirds of validation families win',
          'primary':'prevalidated zero-probe cheap model vs CORE; fallback CORE unless preset validation accepted',
          'benchmark_type':'generated SAT planted-witness; independent analytic pigeonhole UNSAT benchmark separately; NOT official CNFs',
          'selection':'frozen before holdout, no holdout tuning'})
    cnf = args.out/'current.cnf'
    train = collect_pairs(binary, cohorts['train'], cnf, args.out/'train_pairs.jsonl')
    # Checkpoint depth may be adjusted using TRAIN ONLY; never tune it on holdout.
    first_labeled=sum(r['label'] is not None for r in train)
    if first_labeled < 80:
        X.DECISION=8
        emit('CHECKPOINT_TRAIN_ONLY', {'old_decision':DECISION,'new_decision':X.DECISION,
                                      'labeled_at_old':first_labeled})
        train=collect_pairs(binary,cohorts['train'],cnf,args.out/'train_pairs.jsonl')
    validation = collect_pairs(binary, cohorts['validation'], cnf, args.out/'validation_pairs.jsonl')
    protocol=json.loads((args.out/'protocol.json').read_text())
    protocol['decision']=X.DECISION
    protocol['checkpoint_selection']='16 else 8 if <80 complete train-only pairs at 16'
    save(args.out/'protocol.json',protocol)
    emit('TRAIN_STATS', {'labeled':sum(r['label'] is not None for r in train),
                         'total':len(train), 'exclusions':dict(Counter(r['exclusion'] or 'labeled' for r in train))})
    model_set = fit(train)
    candidates = {}
    files = {}
    for kind, base in model_set.items():
        for threshold in THRESHOLDS:
            for min_conf in MIN_CONFLICTS:
                key = f'{kind}_t{threshold}_c{min_conf}'
                m = {**base, 'threshold':threshold, 'min_conflicts':min_conf}
                p = args.out/(key+'.txt')
                write_model(p, m)
                candidates[key] = m
                files[key] = p
    validation_core = {}
    validation_runs = {k:{} for k in candidates}
    with (args.out/'validation_trials.jsonl').open('w') as out:
        for i, case in enumerate(cohorts['validation']):
            cnf.write_text(case['source'])
            order = ['core'] + list(candidates)
            random.Random(i+4911).shuffle(order)
            row = {'family':case['family'], 'sha256':case['sha256'], 'arms':{}}
            for name in order:
                trial = X.run(binary, cnf, case, 'core' if name=='core' else 'cheap',
                              args.cap, model=files.get(name))
                row['arms'][name] = trial
                if name == 'core':
                    validation_core[case['sha256']] = trial
                else:
                    validation_runs[name][case['sha256']] = trial
            out.write(json.dumps(row, sort_keys=True)+'\n')
            if (i+1) % 24 == 0:emit('VALIDATION', {'done':i+1,'total':len(cohorts['validation'])})
    val_order = [c['sha256'] for c in cohorts['validation']]
    effects = {k:series(validation_runs[k],validation_core,val_order) for k in candidates}
    winner = max(candidates, key=lambda k:(effects[k]['improvement_pct'], k))
    families = sorted(X.VALIDATION)
    family_gains = {f:100*(1-sum(validation_runs[winner][c['sha256']]['PAR2'] for c in cohorts['validation'] if c['family']==f)/
                         sum(validation_core[c['sha256']]['PAR2'] for c in cohorts['validation'] if c['family']==f))
                    for f in families}
    solved_core = sum(x['within_cap'] for x in validation_core.values())
    solved_winner = sum(x['within_cap'] for x in validation_runs[winner].values())
    accept = (effects[winner]['paired_formula_bootstrap95_pct'][0] > 3.0
              and sum(v>0 for v in family_gains.values())>=2
              and solved_winner>=solved_core)
    frozen = candidates[winner]
    frozen_file = files[winner]
    frozen_sha = hashlib.sha256(frozen_file.read_bytes()).hexdigest()
    save(args.out/'freeze.json',
         {'primary_candidate':winner, 'model_sha256':frozen_sha,
          'deploy_policy':'cheap' if accept else 'core',
          'validation_accepted':accept, 'candidate_effects':effects,
          'validation_family_gains':family_gains,
          'validation_solved':{'core':solved_core,'candidate':solved_winner}})
    emit('FROZEN', {'candidate':winner,'sha256':frozen_sha,
                     'validation_accepted':accept,
                     'effect':effects[winner],
                     'deployment':'cheap' if accept else 'core'})
    # The only read of sealed holdout starts after the complete frozen manifest.
    trials = []
    holdout_pairs = []
    with (args.out/'holdout_trials.jsonl').open('w') as out, (args.out/'holdout_pairs.jsonl').open('w') as pairs_fd:
        for i, case in enumerate(cohorts['holdout']):
            cnf.write_text(case['source'])
            matched = cheap_pair(binary, cnf, case)
            holdout_pairs.append(matched)
            pairs_fd.write(json.dumps(matched,sort_keys=True)+'\n')
            for rep in range(args.repeats):
                order=list(ARMS)
                random.Random(i*37+rep+114).shuffle(order)
                arms={}
                for name in order:
                    arms[name]=X.run(binary, cnf, case, name, args.cap,
                                     model=frozen_file if name in ('cheap','cheap_sham') else None)
                gated=arms['cheap']
                if gated['reached']:
                    features=gated['policy']['features']
                    if gated['policy']['gate_skipped']:
                        assert not features and not gated['policy']['flipped']
                        if gated['within_cap'] and arms['core']['within_cap']:
                            assert all(gated[k] == arms['core'][k]
                                       for k in ('decisions','conflicts','propagations'))
                    else:
                        assert len(features)==NF
                        expected=(choose(frozen,features))
                        assert gated['policy']['flipped']==expected, 'native/Python decision mismatch'
                        score,_=predict(frozen,features)
                        assert abs(score-gated['policy']['score']) < 1e-7
                assert not arms['cheap_sham']['policy']['flipped']
                if arms['core']['within_cap'] and arms['cheap_sham']['within_cap']:
                    assert all(arms['core'][k]==arms['cheap_sham'][k]
                               for k in ('decisions','conflicts','propagations'))
                row={'sha256':case['sha256'],'family':case['family'],'index':case['index'],
                     'rep':rep,'arms':arms}
                trials.append(row)
                out.write(json.dumps(row,sort_keys=True)+'\n')
            if (i+1)%25==0:emit('HOLDOUT',{'done':i+1,'total':len(cohorts['holdout'])})
    assert hashlib.sha256(frozen_file.read_bytes()).hexdigest()==frozen_sha
    by_source=defaultdict(list)
    for r in trials:by_source[r['sha256']].append(r)
    arm_means={k:[float(np.mean([r['arms'][k]['PAR2'] for r in group]))
                  for group in by_source.values()] for k in ARMS}
    comparisons={k:X.effect(arm_means['core'], arm_means[k]) for k in ARMS if k!='core'}
    totals={k:{'PAR2_s':sum(r['arms'][k]['PAR2'] for r in trials),
               'SAT_verified':sum(r['arms'][k]['within_cap'] for r in trials),
               'trials':len(trials),
               'flips':sum(r['arms'][k]['policy']['flipped'] for r in trials),
               'gate_skips':sum(r['arms'][k]['policy'].get('gate_skipped',False) for r in trials),
               'probe_inspections':sum(r['arms'][k]['policy']['probe_inspections'] for r in trials)}
            for k in ARMS}
    group_totals={f:{k:sum(r['arms'][k]['PAR2'] for r in trials if r['family']==f)
                     for k in ARMS} for f in X.HOLDOUT}
    y=[r for r in holdout_pairs if r['label'] is not None]
    work={k:{'matched_solved_trials':sum(r['arms']['core']['within_cap'] and r['arms'][k]['within_cap'] for r in trials),
             'propagations':sum(r['arms'][k]['propagations'] for r in trials
                                if r['arms']['core']['within_cap'] and r['arms'][k]['within_cap'])}
          for k in ARMS}
    # AUC on nontrivial completed counterfactuals is exploratory, not a performance guarantee.
    diagnostics=discrimination(frozen,holdout_pairs)
    # The inherited discrimination helper scores the model but does not know
    # X4.9's cheap pre-probe gate. Report actual gated decisions separately.
    comparable=[r for r in holdout_pairs if r['label'] is not None and abs(r['label'])>.1]
    diagnostics['gate_eligible']=sum(r['base']['pre']['prefix_conflicts']>=frozen['min_conflicts'] for r in comparable)
    diagnostics['gated_accepted_flips']=sum(
        r['base']['pre']['prefix_conflicts']>=frozen['min_conflicts'] and choose(frozen,r['features'])
        for r in comparable)
    diagnostics['accepted_flips']=diagnostics['gated_accepted_flips']
    report={'status':'COMPLETE','namespace':NAMESPACE,'source_count':len(source_ids),
            'train':len(train),'validation':len(validation),
            'holdout':len(cohorts['holdout']),'repeats':args.repeats,
            'decision':X.DECISION,'cap_s':args.cap,'model_sha256':frozen_sha,
            'candidate':winner,'validation_accepted':accept,
            'deploy_policy':'cheap' if accept else 'core',
            'holdout_effects_vs_core':comparisons,'primary_success':accept and comparisons['cheap']['paired_formula_bootstrap95_pct'][0]>3,
            'arms':totals,'families':group_totals,'work':work,
            'prediction':diagnostics,'elapsed_s':time.perf_counter()-started,
            'limits':['Main holdout generated SAT only; analytic UNSAT benchmark is separate.',
                      'No predictive confidence claim from only five holdout generator families.',
                      'One decision checkpoint per formula; matched-state completed labels are selection-biased.',
                      'CHEAP_SHAM estimates cheap feature/model overhead; scheduling noise remains.',
                      'CORE deployed unless preset validation gate passed; holdout never updates weights.']}
    cnf.unlink()
    save(args.out/'report.json',report)
    emit('FINAL',report)


if __name__=='__main__':
    main()
