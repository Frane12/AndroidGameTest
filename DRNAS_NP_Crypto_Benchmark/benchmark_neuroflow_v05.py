#!/usr/bin/env python3
"""DRNAS v0.5: 160 original SATLIB train, 160 NEW SHA-disjoint SATLIB holdout,
72 seeded controls per split. Train once, freeze; paired test x3 on one runner.
All solvers see the exact same canonical DIMACS constraints.
"""
import csv,hashlib,io,tarfile,random,statistics,subprocess,json
from pathlib import Path
from collections import defaultdict
from drnas_np_lab import read_dimacs,normalize,check
from fetch_satlib import BASE,SOURCES,fetch
from neuroflow_v05_structural import structure,execute,fit_training,choose

ROOT=Path(__file__).resolve().parent
DEST=ROOT/'nf05_results'
BUDGET=1.8

def writecsv(path,records):
    if not records:return
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)

def satlib_split():
    train=[];held=[];known=set()
    for family_i,(family,rel,expected) in enumerate(SOURCES):
        url=BASE+'/'+rel
        raw=fetch(url)
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
            mm=sorted([m for m in tar.getmembers()
                       if m.isfile() and m.name.lower().endswith('.cnf') and m.size<3000000],
                      key=lambda m:m.name)
            data=[(m.name,tar.extractfile(m).read()) for m in mm]
        digests=[hashlib.sha256(x[1]).hexdigest() for x in data]
        original=random.Random(20261031+family_i*701).sample(range(len(data)),20)
        not_old=[i for i in range(len(data)) if digests[i] not in {digests[k] for k in original}]
        # Exclude the previously USED v0.4 heldout SATLIB sample.
        prev_v04=random.Random(2026110107+111*family_i).sample(not_old,20)
        new_candidates=[i for i in not_old if i not in set(prev_v04)]
        unseen=random.Random(2026110617+197*family_i).sample(new_candidates,20)
        assert not(set(original)&set(unseen)) and not(set(prev_v04)&set(unseen))
        for phase,indices,out in (('train',original,train),('holdout',unseen,held)):
            folder=DEST/('train_cases' if phase=='train' else 'holdout_cases')
            folder.mkdir(parents=True,exist_ok=True)
            for ix in indices:
                name,source=data[ix]
                sha=digests[ix]
                if sha in known:raise AssertionError('Duplicate source SHA256 between splits')
                known.add(sha)
                cid=('%s_%04d'%(phase,len(out)+1))
                p=folder/(cid+'.cnf')
                p.write_bytes(source)
                n,clauses=read_dimacs(p)
                # SATLIB '%' EOF gets removed; both solvers receive same CNF.
                canonical='p cnf %d %d\n'%(n,len(clauses))+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)
                p.write_text(canonical)
                assert read_dimacs(p)==(n,clauses)
                out.append(dict(case_id=cid,source='SATLIB',family=family,n=n,c=clauses,
                         sha=sha,expected=expected,file=p,source_url=url,source_name=name))
        print(f'SATLIB {family}: train 20, prior-v04 excluded 20, NEW holdout 20',flush=True)
    assert len(train)==len(held)==160
    assert set(x['sha'] for x in train).isdisjoint(set(x['sha'] for x in held))
    writecsv(DEST/'satlib_train_manifest.csv',[{k:v for k,v in x.items() if k not in ('c','file')} for x in train])
    writecsv(DEST/'satlib_holdout_manifest.csv',[{k:v for k,v in x.items() if k not in ('c','file')} for x in held])
    return train,held

def control(n,seed,kind):
    rng=random.Random(seed);flips=[bool(rng.getrandbits(1)) for _ in range(n)]
    clauses=[]
    for _ in range(n*3):
        v=rng.sample(range(1,n+1),3);p=rng.randrange(4)
        clauses.append(tuple(x if j==p else -x for j,x in enumerate(v)))
    if kind=='horn_unsat':
        clauses += [(1,),(-n,)] + [(-x,x+1) for x in range(1,n)]
    if kind=='near_sat':
        for _ in range(max(1,n//2)):
            a,b,c=rng.sample(range(1,n+1),3)
            clauses.append((a,b,-c))
    return normalize(n,[tuple(-l if flips[abs(l)-1] else l for l in c) for c in clauses])

def control_cases(phase):
    cases=[]
    prefix=654321 if phase=='train' else 765432
    for n in (30,60,100):
        for kind in ('horn_sat','horn_unsat','near_sat'):
            for j in range(8):
                seed=prefix+1000*n+31*j+len(kind)
                clauses=control(n,seed,kind)
                expected='UNSAT' if kind=='horn_unsat' else 'SAT'
                cid=f'{phase}_{kind}_{n}_{j:02d}'
                cases.append(dict(case_id=cid,source='constructed',family=kind,n=n,c=clauses,
                                  sha=hashlib.sha256(repr(clauses).encode()).hexdigest(),
                                  expected=expected,file=None,source_url='constructed',
                                  source_name='seed:'+str(seed)))
    return cases

def verified(c,result):
    if result['status'] != c['expected']:
        raise AssertionError(f"{c['case_id']} expected {c['expected']} got {result['status']}: {result['path']}")
    if result['status']=='SAT':
        assert result['model'] is not None and check(c['c'],result['model'])

def train_policy(data):
    random.Random(2026110619).shuffle(data)
    samples=[]
    for i,c in enumerate(data):
        n,clauses=c['n'],c['c']
        f=structure(n,clauses)
        # Paired, order counterbalanced. ALL train alternatives measured.
        if i%2:
            alt=execute(n,clauses,'always',budget=BUDGET)
            base=execute(n,clauses,'base',budget=BUDGET)
        else:
            base=execute(n,clauses,'base',budget=BUDGET)
            alt=execute(n,clauses,'always',budget=BUDGET)
        verified(c,base);verified(c,alt)
        if f['bad']==0:
            direct=execute(n,clauses,'learned',threshold=0,budget=BUDGET)
            verified(c,direct)
            candidate_ms=direct['ms']
        else:
            candidate_ms=alt['ms']+f['feature_ms']
        samples.append(dict(case_id=c['case_id'],family=c['family'],source=c['source'],tier=f['tier'],
            defect=f['defect'],feature_ms=f['feature_ms'],base_ms=base['ms'],
            candidate_ms=candidate_ms,baseline_path=base['path'],candidate_path=alt['path']))
        if (i+1)%40==0:print(f'TRAIN {i+1}/{len(data)}',flush=True)
    writecsv(DEST/'train_samples.csv',samples)
    model=fit_training(samples)
    (DEST/'frozen_policy.json').write_text(json.dumps(model,indent=2))
    print('POLICY FREEZE '+str(model['table']),flush=True)
    return model

def cms_verify(c):
    if c['file'] is None:return
    p=subprocess.run(['cryptominisat5','--verb','0',str(c['file'])],
                     text=True,capture_output=True,timeout=4)
    status='UNSAT' if 's UNSATISFIABLE' in p.stdout else ('SAT' if 's SATISFIABLE' in p.stdout else 'ERROR')
    assert status==c['expected'],(c['case_id'],status,p.stderr[-300:])

def test_only(data,model,reps=3):
    random.Random(2026110620).shuffle(data)
    observations=[]
    for i,c in enumerate(data):
        cms_verify(c)
        threshold=choose(model,c['n'])
        for rep in range(reps):
            modes=('base','always','learned') if (i+rep)%2==0 else ('learned','always','base')
            results={}
            for m in modes:
                r=execute(c['n'],c['c'],m,threshold=threshold,budget=BUDGET)
                verified(c,r);results[m]=r
            f=structure(c['n'],c['c'])
            observations.append(dict(case_id=c['case_id'],source=c['source'],family=c['family'],
                    n=c['n'],rep=rep,status=c['expected'],threshold=threshold,
                    defect=round(f['defect'],5),
                    base_ms=round(results['base']['ms'],4),
                    always_ms=round(results['always']['ms'],4),
                    learned_ms=round(results['learned']['ms'],4),
                    always_path=results['always']['path'],learned_path=results['learned']['path'],
                    learned_feature_ms=round(results['learned']['feature_ms'],4),
                    learned_probe_ms=round(results['learned']['probe_ms'],4)))
        if (i+1)%40==0:print(f'HELDOUT {i+1}/{len(data)}',flush=True)
    writecsv(DEST/'heldout.csv',observations)
    summ=[]
    for src,family in sorted(set((r['source'],r['family']) for r in observations)):
        group=[r for r in observations if (r['source'],r['family'])==(src,family)]
        savings=[r['base_ms']-r['learned_ms'] for r in group]
        summ.append(dict(source=src,family=family,cases=len(group)//reps,
             repeats=reps,base_med_ms=round(statistics.median(r['base_ms'] for r in group),4),
             always_med_ms=round(statistics.median(r['always_ms'] for r in group),4),
             learned_med_ms=round(statistics.median(r['learned_ms'] for r in group),4),
             learned_med_paired_gain_ms=round(statistics.median(savings),4),
             learned_wins=sum(s>0 for s in savings),
             direct_horn=sum(r['learned_path']=='direct-majority-Horn' for r in group)//reps,
             full_probe_success=sum(r['learned_path']=='renamable-Horn' for r in group)//reps))
    writecsv(DEST/'summary.csv',summ)
    print('FINAL HELDOUT RESULTS',flush=True)
    for r in summ:print(json.dumps(r,sort_keys=True),flush=True)
    (DEST/'protocol.json').write_text(json.dumps({'train_cases':232,'holdout_cases':232,
      'SATLIB_holdout_new':160,'synthetic_holdout':72,'repetitions':reps,
      'frozen_before_holdout':True,'data_leakage':'source SHA256 disjoint from prior 160 and prior v04 set',
      'total_cost':'feature + algebra probe + solve; no python process startup',
      'safety':'All SAT models checked; all SATLIB outcomes verified by actual CryptoMiniSat 5.11.15',
      'caution':'Pre-existing renamable-Horn math; not a generic SAT speedup or novel complexity result'},indent=2))
    return summ

def main():
    DEST.mkdir(exist_ok=True)
    train,held=satlib_split()
    train+=control_cases('train');held+=control_cases('holdout')
    assert len(train)==len(held)==232
    assert {c['sha'] for c in train}.isdisjoint({c['sha'] for c in held})
    model=train_policy(train)
    test_only(held,model)
    print('SUCCESS: 232 train and 232 heldout with frozen NeuroFlow structural policy',flush=True)

if __name__=='__main__':main()
