#!/usr/bin/env python3
"""Replay the original 116-case Hall2 audit through the complete hybrid solver."""
import collections,json,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
import benchmark as B
sys.path.insert(0,str(ROOT/'research/pcmax_capacity'))
from random_unsat_probe import SEED,cases,write_cnf

def main():
    B.pin();out=ROOT/'hall3_recovery';out.mkdir(exist_ok=False)
    rows=[]
    for i,c in enumerate(cases(random.Random(SEED))):
        p=out/(c['name']+'.cnf');write_cnf(p,c['clauses'],c['nvars'])
        source=dict(id=i,family=c['family'],path=str(p.relative_to(ROOT)),sha256=B.sha(p))
        r=B.trial(source,'HALL3_ON',0,out/c['name'],cap=4)
        if r['verified']:
            assert r['status']==c['expected']+'_VERIFIED',(c['name'],r)
        rows.append(r)
    summary=dict(total=len(rows),verified=sum(r['verified'] for r in rows),
        sat=sum(r['status']=='SAT_VERIFIED' for r in rows),
        unsat=sum(r['status']=='UNSAT_VERIFIED' for r in rows),
        certificate_kinds=dict(collections.Counter(r['certificate_kind'] for r in rows)),
        unknown=sum(not r['verified'] for r in rows),false_results=0)
    B.save(out/'summary.json',summary);B.emit('HALL3_RECOVERY_PASS',summary)

if __name__=='__main__':main()
