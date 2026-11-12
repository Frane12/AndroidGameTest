#!/usr/bin/env python3
"""REX1: bounded relational decision-probe research prototype (not a CDCL solver)."""
import argparse, json, pathlib, statistics, sys, time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import drnas_atlas13_generator as G

def propagate(clauses, assignments, budget=50000):
    a=dict(assignments); scans=0
    while scans<budget:
        changed=False
        for clause in clauses:
            scans+=1
            if scans>budget: return None,len(a),scans
            unknown=[]; satisfied=False
            for lit in clause:
                v=abs(lit)
                if v in a:
                    if a[v]==(lit>0): satisfied=True;break
                else:unknown.append(lit)
            if satisfied:continue
            if not unknown:return False,len(a),scans
            if len(unknown)==1:
                lit=unknown[0];v=abs(lit);val=lit>0
                if v in a and a[v]!=val:return False,len(a),scans
                if v not in a:a[v]=val;changed=True
        if not changed:return True,len(a),scans
    return None,len(a),scans

def rank(clauses,n,top=12):
    freq=[0]*(n+1);neighbors=[set() for _ in range(n+1)]
    for c in clauses:
        vs=list(set(abs(x) for x in c))
        for v in vs:freq[v]+=1
        if len(vs)<=12:
            for v in vs:neighbors[v].update(u for u in vs if u!=v)
    candidates=sorted(range(1,n+1),key=lambda v:(freq[v],len(neighbors[v])),reverse=True)[:top]
    return candidates,freq,neighbors

def evaluate(n,clauses,top=12,budget=50000):
    candidates,freq,neighbors=rank(clauses,n,top)
    start=time.perf_counter()
    baseline=propagate(clauses,{},budget)
    if baseline[0] is False:return dict(status='root_conflict',best=0,probes=0,elapsed=time.perf_counter()-start)
    best=None;scored=[]
    for v in candidates:
        outcomes=[propagate(clauses,{v:b},budget) for b in (False,True)]
        conflicts=sum(o[0] is False for o in outcomes)
        implied=sum(max(0,o[1]-1) for o in outcomes)
        score=1000*conflicts+implied+0.01*len(neighbors[v])
        scored.append((score,v,conflicts,implied,sum(o[2] for o in outcomes)))
    if scored:best=max(scored)
    return dict(status='diagnostic_only',best=best[1] if best else 0,score=best[0] if best else 0,
                conflicts=best[2] if best else 0,implications=best[3] if best else 0,
                probes=len(scored)*2,scans=sum(x[4] for x in scored),
                elapsed=round(time.perf_counter()-start,6),
                max_degree=max((len(neighbors[v]) for v in candidates),default=0))

def main():
    p=argparse.ArgumentParser();p.add_argument('--indices',default='90,91');p.add_argument('--top',type=int,default=8)
    p.add_argument('--budget',type=int,default=12000);p.add_argument('--output',default='rex1-results.jsonl')
    args=p.parse_args();rows=[]
    for family in G.CATEGORIES:
        for index in map(int,args.indices.split(',')):
            n,clauses,_=G.build(family,index)
            r=evaluate(n,clauses,args.top,args.budget)
            row=dict(family=family,index=index,variables=n,clauses=len(clauses),**r)
            rows.append(row);print('REX1_PROBE '+json.dumps(row),flush=True)
    pathlib.Path(args.output).write_text(''.join(json.dumps(r)+'\n' for r in rows))
    print('REX1_SUMMARY '+json.dumps(dict(cases=len(rows),diagnostic_only=True,
        total_probe_s=round(sum(r['elapsed'] for r in rows),4),
        total_probes=sum(r.get('probes',0) for r in rows),
        median_probe_s=round(statistics.median(r['elapsed'] for r in rows),6))),flush=True)
if __name__=='__main__':main()
