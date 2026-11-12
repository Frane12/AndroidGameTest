#!/usr/bin/env python3
"""REX1-C: gated relational decision research with disjoint calibration and holdout.
No SAT solving claims: probes only, never an end-to-end CDCL benchmark.
"""
import argparse,hashlib,json,pathlib,statistics,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import drnas_atlas13_generator as G
import drnas_rex1_probe as P

def evaluate(n,clauses,gate,top,budget):
    candidates,freq,neighbors=P.rank(clauses,n,top)
    baseline=candidates[0] if candidates else 0
    # Cheap, deterministic structure gate; do not use holdout labels.
    structural=max((len(neighbors[v]) for v in candidates),default=0)
    density=len(clauses)/max(1,n)
    eligible=bool(candidates) and structural>=gate and density>=2.0
    if not eligible:return dict(baseline=baseline,selected=baseline,changed=False,enabled=False,scans=0,probes=0,conflicts=0)
    best=baseline;bestscore=float('-inf');scans=0;probes=0;bestconflicts=0
    for v in candidates:
        outcomes=[P.propagate(clauses,{v:polarity},budget) for polarity in (False,True)]
        cost=sum(x[2] for x in outcomes);scans+=cost;probes+=2
        conflicts=sum(x[0] is False for x in outcomes)
        implied=sum(max(0,x[1]-1) for x in outcomes)
        score=1000*conflicts+implied+0.01*len(neighbors[v])-0.0001*cost
        if score>bestscore:bestscore=score;best=v;bestconflicts=conflicts
    return dict(baseline=baseline,selected=best,changed=best!=baseline,enabled=True,scans=scans,probes=probes,conflicts=bestconflicts)

def make(indices):
    rows=[]
    for family in G.CATEGORIES:
        for idx in indices:
            n,clauses,_=G.build(family,idx)
            sha=hashlib.sha256((str(n)+repr(clauses)).encode()).hexdigest()
            rows.append((family,idx,n,clauses,sha))
    return rows

def run(rows,gate,top,budget):
    output=[]
    for family,idx,n,clauses,sha in rows:
        start=time.perf_counter()
        result=evaluate(n,clauses,gate,top,budget)
        output.append(dict(family=family,index=idx,sha256=sha,variables=n,clauses=len(clauses),
                           elapsed_s=round(time.perf_counter()-start,6),**result))
    return output

def aggregate(rows):
    return dict(cases=len(rows),enabled=sum(r['enabled'] for r in rows),changed=sum(r['changed'] for r in rows),
                conflicts_seen=sum(r['conflicts'] for r in rows),scans=sum(r['scans'] for r in rows),
                probes=sum(r['probes'] for r in rows),probe_s=round(sum(r['elapsed_s'] for r in rows),6))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--train',default='101,102,103,104')
    p.add_argument('--holdout',default='91,92,93,94,95,96,97,98')
    p.add_argument('--top',type=int,default=6)
    p.add_argument('--budget',type=int,default=5000)
    p.add_argument('--output',default='rex1c')
    a=p.parse_args()
    train=make([int(x) for x in a.train.split(',')])
    holdout=make([int(x) for x in a.holdout.split(',')])
    assert len({x[4] for x in train})==len(train)
    assert len({x[4] for x in holdout})==len(holdout)
    assert not ({x[4] for x in train}&{x[4] for x in holdout})
    # Calibrate on structural decision differences and probe cost only; no SAT labels.
    candidates=[]
    for gate in (0,8,16,32,64):
        rows=run(train,gate,a.top,a.budget)
        stats=aggregate(rows)
        # Prefer changes, but discourage gratuitous scans; penalize all-on gating.
        objective=stats['changed']*10000-stats['scans']*0.01
        candidates.append((objective,gate,stats))
        print('REX1C_TRAIN '+json.dumps(dict(gate=gate,objective=round(objective,3),**stats)),flush=True)
    _,gate,_=max(candidates,key=lambda x:(x[0],x[1]))
    results=run(holdout,gate,a.top,a.budget)
    for row in results:print('REX1C_HOLDOUT '+json.dumps(row),flush=True)
    base=pathlib.Path(a.output)
    base.with_suffix('.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in results))
    summary=dict(gate=gate,train_cases=len(train),holdout_disjoint=True,top=a.top,budget=a.budget,
                 **aggregate(results),verified_SAT_UNSAT=0,CDCL_integrated=False,PAR2_available=False)
    base.with_name(base.name+'-summary.json').write_text(json.dumps(summary,indent=2))
    print('REX1C_FINAL '+json.dumps(summary),flush=True)
if __name__=='__main__':main()
