#!/usr/bin/env python3
"""Learn at most TWO transparent CNF-structure routing rules for native CaDiCaL.

Data: 100 already examined external CNFs (v0.6.3, v0.9.1, v1.0), not
the v1.1 42-case external test. "SAT"/"UNSAT" is not a model feature.
Every variant is the same compiled native CaDiCaL backend. 2 paired repeats.
Hard constraints on validation completion regressions; OFF is acceptable.
"""
import csv,hashlib,json,random,statistics,subprocess
from pathlib import Path
from drnas_np_lab import read_dimacs
ROOT=Path(__file__).resolve().parent
BIN=ROOT/'native_v110/drnas_nf110'
OUT=ROOT/'native_v110/training'
BUDGET=2200
REPEAT=2
MODES=('base','phase-majority','phase-selective')
N_FAMILY='BytWyze'  # prior studies only, never used at inference

def read_csv(path):
    with path.open(encoding='utf-8') as f:return list(csv.DictReader(f))
def write_csv(path,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def prior_cases():
    cases=[]
    for x in read_csv(ROOT/'nf063_external/manifest.csv'):
        assert x['fetch_status']=='READY'
        path=ROOT/'nf063_external'/(x['case_id']+'.cnf')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==x['canonical_sha256']
        cases.append(dict(id=x['case_id'],family=x['source_group'],sha=x['source_sha256'],path=path))
    for x in read_csv(ROOT/'nf091_holdout/manifest.csv'):
        path=ROOT/'nf091_holdout'/(x['id']+'.cnf')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==x['canonical_sha256']
        cases.append(dict(id='old091_'+x['id'],family='BytWyze',sha=x['source_sha256'],path=path))
    for x in read_csv(ROOT/'nf100_holdout/manifest.csv'):
        path=ROOT/'nf100_holdout'/(x['id']+'.cnf')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==x['normalized_sha256']
        cases.append(dict(id='old100_'+x['id'],family='BytWyze',sha=x['original_sha256'],path=path))
    assert len(cases)==100 and len({c['sha'] for c in cases})==100
    return cases

def structural(path):
    n,clauses=read_dimacs(path)
    pos=[0]*n;neg=[0]*n
    count=0
    for cl in clauses:
        for lit in cl:
            count+=1
            if lit>0:pos[lit-1]+=1
            else:neg[-lit-1]+=1
    m=max(1,len(clauses))
    return dict(n=n,density=len(clauses)/max(1,n),
        minority=sum(min(a,b) for a,b in zip(pos,neg))/max(1,count),
        binary=sum(len(c)==2 for c in clauses)/m,
        long=sum(len(c)>=4 for c in clauses)/m,
        unit=sum(len(c)==1 for c in clauses)/m)

def solve(path,method):
    proc=subprocess.run([str(BIN),'--input',str(path),'--mode',method,
          '--budget-ms',str(BUDGET)],capture_output=True,text=True,
          timeout=BUDGET/1000+4)
    if proc.returncode:
        raise RuntimeError(f'{path} {method}: {proc.stderr[-800:]}')
    out=json.loads(proc.stdout.strip())
    assert out['status'] in ('SAT','UNSAT','UNKNOWN')
    if out['status']=='SAT':assert out['witness_valid'] is True
    return out

def benefit(a,b):
    """Completion matters MORE than a modest runtime gain."""
    ac=a['status'] in ('SAT','UNSAT')
    bc=b['status'] in ('SAT','UNSAT')
    if ac and bc:
        assert a['status']==b['status']
        return max(-250.,min(250.,float(a['total_ms'])-float(b['total_ms'])))
    if ac and not bc:return -600.
    if bc and not ac:return +400.
    return 0.

def match(row,rule):
    eng,min_n,min_density,max_minor,min_binary,min_long,max_unit=rule
    return (row['n']>=min_n and row['density']>=min_density and
            row['minority']<=max_minor and row['binary']>=min_binary and
            row['long']>=min_long and row['unit']<=max_unit)
def benefit_row(row,rule):
    return row['gain_'+rule[0]] if match(row,rule) else 0.

def rules():
    for eng in ('majority','selective'):
      for min_n in (0,100,300,600):
       for min_density in (0.,3.,5.,8.):
        for max_minor in (.22,.32,.43,.50):
         for min_binary in (0.,.20,.50):
          for min_long in (0.,.10,.30):
           for max_unit in (0.,1.):
            yield (eng,min_n,min_density,max_minor,min_binary,min_long,max_unit)

def score(rows,rule,prev=[]):
    """The previous accepted rule handles its matching inputs first."""
    usable=[r for r in rows if not any(match(r,p) for p in prev)]
    chosen=[r for r in usable if match(r,rule)]
    return dict(n=len(chosen),up=sum(r['gain_'+rule[0]]>0 for r in chosen),
       down=sum(r['gain_'+rule[0]]<0 for r in chosen),
       total=len(rows),mean_gain=(sum(r['gain_'+rule[0]] for r in chosen)/max(1,len(rows))),
       lost_completion=sum(max(0,int(r['base_completed'])-int(r[rule[0]+'_completed']))
          for r in chosen))

def train():
    OUT.mkdir(parents=True,exist_ok=True)
    samples=prior_cases()
    random.Random(202611031124).shuffle(samples)
    measurements=[]
    for i,c in enumerate(samples):
        feats=structural(c['path'])
        readings={m:[] for m in MODES}
        for repeat in range(REPEAT):
            k=(i+repeat)%len(MODES)
            for method in MODES[k:]+MODES[:k]:
                readings[method].append(solve(c['path'],method))
        reference={r['status'] for vals in readings.values()
                   for r in vals if r['status'] in ('SAT','UNSAT')}
        assert len(reference)<=1,(c['id'],reference)
        gains={}
        for method,engine in (('phase-majority','majority'),('phase-selective','selective')):
            gains[engine]=statistics.mean(
                benefit(base,trial) for base,trial in zip(readings['base'],readings[method]))
        measurements.append(dict(id=c['id'],family=c['family'],original_sha256=c['sha'],
            **feats,
            gain_majority=gains['majority'],gain_selective=gains['selective'],
            base_completed=sum(r['status'] in ('SAT','UNSAT') for r in readings['base']),
            majority_completed=sum(r['status'] in ('SAT','UNSAT') for r in readings['phase-majority']),
            selective_completed=sum(r['status'] in ('SAT','UNSAT') for r in readings['phase-selective'])))
        if (i+1)%10==0:print(f'TRAIN {i+1}/100',flush=True)
    write_csv(OUT/'train_cases.csv',measurements)
    # Split by source families (no results of v1.1 test available).
    grouped={}
    for r in measurements:grouped.setdefault(r['family'],[]).append(r)
    tune=[];validation=[]
    for family,entries in grouped.items():
        random.Random(202611031125+len(family)).shuffle(entries)
        n=max(2,len(entries)//4)
        validation.extend(entries[:n]);tune.extend(entries[n:])
    assert len(tune)>=70 and len(validation)>=20
    frozen=[];history=[]
    for depth in range(2):
        options=[]
        for rule in rules():
            ts=score(tune,rule,frozen)
            if ts['n']<8 or ts['up']<3:continue
            # Score is total net value per training-case after clipping
            # gains/timeouts, with a complexity and noise reserve.
            quality=ts['mean_gain'] - 1.0 - 0.2*len(frozen)
            options.append((quality,rule,ts))
        options.sort(key=lambda x:x[0],reverse=True)
        if not options:break
        quality,choice,ts=options[0]
        vs=score(validation,choice,frozen)
        # Reject model without independently positive validation benefit
        # and NO validation degradation in completed solves.
        accepted=(quality>1.5 and vs['n']>=4 and
             vs['mean_gain']>1.5 and vs['lost_completion']==0)
        history.append(dict(depth=depth,train_rule=list(choice),
                            tune_score=quality,tune=ts,validation=vs,
                            accepted=accepted))
        if not accepted:break
        frozen.append(choice)
    # Policy line has exactly 2 + 12*rules whitespace tokens.
    # The model reads NEVER a SAT/UNSAT label.
    model=['DRNAS_V110_POLICY',str(len(frozen))]
    for engine,min_n,min_density,max_minor,min_binary,min_long,max_unit in frozen:
        model.extend([engine,str(min_n),'2000000',str(min_density),'1e20',
          '0',str(max_minor),str(min_binary),'1',str(min_long),'1',str(max_unit)])
    policy=' '.join(model)+'\n'
    (OUT/'frozen_policy.txt').write_text(policy)
    decision=dict(version='v1.1',enabled=len(frozen)>0,rule_count=len(frozen),
        selected_rules=[list(r) for r in frozen],
        search_history=history,training_cases=len(tune),validation_cases=len(validation),
        all_prior_cases=len(measurements),
        no_new_holdout_access=True,
        frozen_policy=policy.strip(),
        gain_definition='Capped +/-250ms paired difference; +400/-600 completion utility; separately enforce zero validation completion losses',
        note='Two shallow structural rules maximum, no status labels used in inference')
    (OUT/'frozen_decision.json').write_text(json.dumps(decision,indent=2))
    print('FROZEN MODEL BEFORE NEW HOLDOUT',json.dumps(decision),flush=True)

if __name__=='__main__':train()
