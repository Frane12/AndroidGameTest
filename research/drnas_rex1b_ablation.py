#!/usr/bin/env python3
"""REX1-B decision-selection ablation: graph-only vs bounded UP lookahead.
This is an instrumented research benchmark, NOT a native CDCL integration.
"""
import argparse,json,pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import drnas_atlas13_generator as G
import drnas_rex1_probe as P

def choose(n,clauses,top,budget):
    candidates,freq,neighbors=P.rank(clauses,n,top)
    baseline=candidates[0] if candidates else 0
    best=baseline;bestscore=float('-inf');total_scans=0;conflicts=0;probes=0
    for v in candidates:
        result=[]
        for value in (False,True):
            status,assigned,scans=P.propagate(clauses,{v:value},budget)
            result.append((status,assigned,scans));total_scans+=scans;probes+=1
        local_scans=sum(scans for _,_,scans in result)
        local_conflicts=sum(status is False for status,_,_ in result)
        implied=sum(max(0,assigned-1) for _,assigned,_ in result)
        # Cost-aware: penalize the exact work expended by the probes.
        score=1000*local_conflicts+implied+0.01*len(neighbors[v])-local_scans*0.0001
        if score>bestscore:bestscore=score;best=v;conflicts=local_conflicts
    return dict(baseline=baseline,selected=best,changed=best!=baseline,
                conflicts=conflicts,scans=total_scans,probes=probes)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--indices',default='93,94')
    p.add_argument('--top',type=int,default=8)
    p.add_argument('--budget',type=int,default=12000)
    p.add_argument('--output',default='rex1b-results.jsonl')
    a=p.parse_args()
    rows=[]
    for family in G.CATEGORIES:
        for idx in map(int,a.indices.split(',')):
            n,clauses,_=G.build(family,idx)
            started=time.perf_counter()
            result=choose(n,clauses,a.top,a.budget)
            row=dict(family=family,index=idx,variables=n,clauses=len(clauses),
                     elapsed_s=round(time.perf_counter()-started,6),**result)
            rows.append(row);print('REX1B_TRIAL '+json.dumps(row),flush=True)
    pathlib.Path(a.output).write_text(''.join(json.dumps(r)+'\n' for r in rows))
    print('REX1B_FINAL '+json.dumps(dict(cases=len(rows),changed=sum(r['changed'] for r in rows),
        total_scans=sum(r['scans'] for r in rows),total_probe_s=round(sum(r['elapsed_s'] for r in rows),6),
        verified_SAT_UNSAT=0,CDCL_integrated=False)),flush=True)
if __name__=='__main__':main()
