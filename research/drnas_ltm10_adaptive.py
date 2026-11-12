#!/usr/bin/env python3
"""LTM10: persistent, frozen, source-disjoint policy learning for native LTM9.
Experimental strategy learning, NOT autonomous discovery of mathematical theorems.
"""
import argparse, hashlib, json, os, pathlib, resource, statistics, subprocess, time
import drnas_atlas13_generator as G

BIN="mre_atlas23/bin/drnas_ltm9"
POLICIES={"conservative":"1.0,0.85","explore":"0.7,0.95","aggressive":"1.4,0.75"}
CATEGORIES=tuple(G.CATEGORIES)

def features(n,clauses):
    pos=sum(len(c)>=2 and all(x>0 for x in c) for c in clauses)
    neg=sum(len(c)==2 and all(x<0 for x in c) for c in clauses)
    density=len(clauses)/max(1,n)
    # Labels, generator indices and SHA are never features.
    return ("high-neg" if neg>n else "low-neg")+"|"+("high-pos" if pos>n//2 else "low-pos")+"|"+("dense" if density>4 else "sparse")

def cnf(n,clauses):
    return (f"p cnf {n} {len(clauses)}\n"+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)).encode()

def witness_ok(n,clauses,out):
    values={}
    try:
        for line in out.splitlines():
            if not line.startswith('v '):continue
            for word in line[2:].split():
                lit=int(word)
                if lit==0:continue
                if abs(lit)>n or (abs(lit) in values and values[abs(lit)]!=(lit>0)):return False
                values[abs(lit)]=lit>0
    except ValueError:return False
    return all(any(values.get(abs(x))==(x>0) for x in c) for c in clauses)

def trial(path,n,clauses,policy,cap=5,seed=17):
    command=[BIN,str(path),'--mode','LTM8_FAST','--time',str(cap),'--seed',str(seed),'--policy',policy]
    env=dict(os.environ,DRNAS_LTM8_MEMORY='',OMP_NUM_THREADS='1')
    start=time.monotonic()
    try:
        p=subprocess.run(command,capture_output=True,text=True,timeout=cap,env=env,
                         preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3)))
        status='SAT_VERIFIED' if p.returncode==10 and witness_ok(n,clauses,p.stdout) else ('UNSAT_UNVERIFIED' if p.returncode==20 else 'UNKNOWN')
        if p.returncode==10 and status!='SAT_VERIFIED':status='INVALID_SAT'
        if p.returncode not in (0,10,20):status='ERROR'
        cert='LTM9_PHP_CERT' in p.stdout
    except subprocess.TimeoutExpired:status='TIMEOUT';cert=False
    elapsed=time.monotonic()-start
    return dict(status=status,e2e_s=round(elapsed,6),PAR2_reported_s=round(elapsed if status in ('SAT_VERIFIED','UNSAT_UNVERIFIED') else 2*cap,6),
                PAR2_verified_s=round(elapsed if status=='SAT_VERIFIED' else 2*cap,6),php_marker=cert)

def case(index,family,root):
    n,clauses,_=G.build(family,index)
    data=cnf(n,clauses)
    sha=hashlib.sha256(data).hexdigest()
    path=root/(sha+'.cnf');path.write_bytes(data)
    return n,clauses,sha,path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default='ltm10_results')
    args=ap.parse_args()
    root=pathlib.Path(args.out)
    if root.exists():raise RuntimeError('Output exists: prevent stale-memory leakage')
    root.mkdir();cases=root/'cases';cases.mkdir()
    # Train and test disjoint from each other and LTM9 WIDE indices 311..320.
    train_indices=(501,502,503,504)
    hold_indices=(601,602,603,604,605,606,607,608,609,610)
    assert set(train_indices).isdisjoint(hold_indices)
    train={}
    train_sha=set()
    with (root/'training.jsonl').open('w') as log:
        for family in CATEGORIES:
            for idx in train_indices:
                n,clauses,sha,path=case(idx,family,cases);train_sha.add(sha)
                bucket=features(n,clauses)
                for name,policy in POLICIES.items():
                    r=trial(path,n,clauses,policy,cap=2,seed=17)
                    row=dict(stage='train',sha256=sha,bucket=bucket,policy=name,**r)
                    log.write(json.dumps(row)+'\n');log.flush()
                    if r['status'] in ('INVALID_SAT','ERROR'):raise RuntimeError(str(row))
                    train.setdefault(bucket,{}).setdefault(name,[]).append(r['PAR2_reported_s'])
    # Minimum evidence and >=10% improvement required before selecting nondefault.
    memory={}
    for bucket,arms in train.items():
        base=statistics.median(arms['conservative'])
        candidates={k:statistics.median(v) for k,v in arms.items() if len(v)>=3}
        # Sparse buckets are expected: default safely rather than crashing.
        best=min(candidates,key=candidates.get) if candidates else 'conservative'
        chosen=best if best!='conservative' and candidates[best]<base*.9 else 'conservative'
        memory[bucket]=dict(policy=chosen,observations=len(arms['conservative']),medians=candidates)
    (root/'frozen_memory.json').write_text(json.dumps(memory,indent=2,sort_keys=True))
    rows=[];test_sha=set()
    with (root/'results.jsonl').open('w') as log:
        for family in CATEGORIES:
            for idx in hold_indices:
                n,clauses,sha,path=case(idx,family,cases);test_sha.add(sha)
                bucket=features(n,clauses)
                policy=memory.get(bucket,{}).get('policy','conservative')
                for rep,seed in enumerate((17,29,43)):
                    # Paired comparison: frozen learned strategy vs fixed baseline.
                    for arm,choice in (('LTM9_FIXED','conservative'),('LTM10_LEARNED',policy)):
                        r=trial(path,n,clauses,POLICIES[choice],cap=5,seed=seed)
                        row=dict(arm=arm,family=family,sha256=sha,rep=rep,bucket=bucket,policy=choice,**r)
                        rows.append(row);log.write(json.dumps(row)+'\n');log.flush()
                        if r['status'] in ('INVALID_SAT','ERROR'):raise RuntimeError(str(row))
    assert len(test_sha)==100 and len(train_sha)==40 and not train_sha&test_sha
    totals={}
    for arm in ('LTM9_FIXED','LTM10_LEARNED'):
        rr=[r for r in rows if r['arm']==arm]
        totals[arm]=dict(trials=len(rr),SAT_verified=sum(r['status']=='SAT_VERIFIED' for r in rr),
                         UNSAT_unverified=sum(r['status']=='UNSAT_UNVERIFIED' for r in rr),
                         php_markers=sum(r['php_marker'] for r in rr),
                         PAR2_reported_s=round(sum(r['PAR2_reported_s'] for r in rr),6),
                         PAR2_verified_s=round(sum(r['PAR2_verified_s'] for r in rr),6))
    result=dict(train_unique=len(train_sha),holdout_unique=len(test_sha),frozen_memory=memory,
                totals=totals,UNSAT_independent_proof=False,
                note='Synthetic generator only; persistent learned policy is frozen JSON artifact; no proof of autonomous theorem discovery.')
    (root/'summary.json').write_text(json.dumps(result,indent=2))
    print('LTM10_FINAL '+json.dumps(result),flush=True)
if __name__=='__main__':main()
