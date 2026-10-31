#!/usr/bin/env python3
"""Exact matched in-process A/B v0.2 versus NeuroFlow v0.3, plus CryptoMiniSat.

160 previously unmodified SATLIB *instances* (same canonical CNF for both)
plus 24 separately reported manufactured renamable Horn controls.
"""
import csv,random,statistics,subprocess,time,json
from pathlib import Path
from drnas_np_lab import read_dimacs,normalize,solve,check
from neuroflow_v03 import NeuroFlowPolicy
ROOT=Path(__file__).resolve().parent

def control(n,seed,sat):
    rng=random.Random(seed)
    flips=[bool(rng.getrandbits(1)) for _ in range(n)]
    horn=[]
    for _ in range(n*3):
        vs=rng.sample(range(1,n+1),3)
        pos=rng.choice((-1,0,1,2))
        horn.append(tuple(v if i==pos else -v for i,v in enumerate(vs)))
    if not sat:horn.extend([(1,),(-1,)])
    clauses=normalize(n,[tuple(-l if flips[abs(l)-1] else l for l in c) for c in horn])
    return clauses

def cms(path):
    p=subprocess.run(['cryptominisat5','--verb','0',str(path)],
       capture_output=True,text=True,timeout=2)
    if 's UNSATISFIABLE' in p.stdout:return 'UNSAT'
    if 's SATISFIABLE' in p.stdout:return 'SAT'
    raise RuntimeError('CMS invalid result on '+str(path)+p.stderr[-500:])

def run():
    dest=ROOT/'neuroflow_results';dest.mkdir(exist_ok=True)
    cases=[]
    with (ROOT/'external_cases/manifest.csv').open() as f:manifest=list(csv.DictReader(f))
    for rec in manifest:
        path=ROOT/'external_cases'/(rec['case_id']+'.cnf')
        n,clauses=read_dimacs(path)
        cases.append((rec['case_id'],'SATLIB',rec['family'],n,clauses,path,rec['expected']))
    for n in (30,60,100):
        for i in range(4):
            for sat in (True,False):
                name=f'control_{n}_{i}_{int(sat)}'
                clauses=control(n,20261031+100*n+i,sat)
                path=dest/(name+'.cnf')
                with path.open('w') as f:
                    f.write(f'p cnf {n} {len(clauses)}\n')
                    for c in clauses:f.write(' '.join(map(str,c))+' 0\n')
                cases.append((name,'constructed_control','renamable_horn',n,clauses,path,'SAT' if sat else 'UNSAT'))
    assert len(cases)==184 and len(manifest)==160
    random.Random(31337).shuffle(cases)
    policy=NeuroFlowPolicy('adaptive',probe_cap_ms=8,recheck_every=5)
    shadow=NeuroFlowPolicy('shadow',probe_cap_ms=8,recheck_every=5)
    rows=[]
    for i,(cid,origin,family,n,clauses,path,expected) in enumerate(cases):
        t=time.perf_counter();base=solve(n,clauses,budget=1.5);base_ms=(time.perf_counter()-t)*1000
        t=time.perf_counter();r=policy.solve(n,clauses,budget=1.5);adaptive_ms=(time.perf_counter()-t)*1000
        t=time.perf_counter();shadow_result=shadow.solve(n,clauses,budget=1.5);shadow_ms=(time.perf_counter()-t)*1000
        outcome=cms(path)
        assert base.status==r.status==shadow_result.status==outcome==expected,(cid,base.status,r.status,shadow_result.status,outcome,expected)
        for model in (base.assignment,r.assignment,shadow_result.assignment):
            if outcome=='SAT':
                assert model is not None and check(clauses,model),(cid,'bad model')
        policy.record_paired_gain(r.cache_bucket,base_ms,adaptive_ms)
        rows.append(dict(case_id=cid,origin=origin,family=family,n=n,m=len(clauses),
            outcome=outcome,baseline_ms=round(base_ms,3),
            adaptive_ms=round(adaptive_ms,3),shadow_ms=round(shadow_ms,3),
            probe_ms=round(r.prep_ms,3),method=r.method,probe_status=r.probe_status,
            fallback=r.fallback_used,bucket=r.cache_bucket))
        if (i+1)%20==0:print(f'CHECKED {i+1}/184',flush=True)
    with (dest/'results.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary=[]
    for origin in ('SATLIB','constructed_control'):
        for family in sorted(set(r['family'] for r in rows if r['origin']==origin)):
            rs=[r for r in rows if r['origin']==origin and r['family']==family]
            summary.append(dict(origin=origin,family=family,count=len(rs),
               baseline_median_ms=round(statistics.median(r['baseline_ms'] for r in rs),3),
               adaptive_median_ms=round(statistics.median(r['adaptive_ms'] for r in rs),3),
               shadow_median_ms=round(statistics.median(r['shadow_ms'] for r in rs),3),
               adaptive_wins=sum(r['adaptive_ms']<r['baseline_ms'] for r in rs),
               recognized=sum(r['method']=='renamable Horn + 2-SAT flips' for r in rs),
               probes_skipped=sum(r['probe_status']=='skipped' for r in rs)))
    with (dest/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    policy.save(dest/'policy_counters.json')
    (dest/'protocol.json').write_text(json.dumps({'external':'160 SATLIB CNFs already inspected in v0.2',
        'control':'24 NEW constructed renamable-Horn CNFs, NOT independent benchmark',
        'time':'in-process Python time for v0.2/v0.3/shadow, no startup',
        'CMS':'actual CryptoMiniSat invoked for status validation', 'seed':31337,
        'repeats':1,'status':'mathematical exactness checked; not proof of novel complexity'},indent=2))
    print('FINAL SUMMARY',flush=True)
    for s in summary:print(s,flush=True)
if __name__=='__main__':run()
