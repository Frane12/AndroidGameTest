#!/usr/bin/env python3
"""Adversarial source-clause proof regression for Hall slot bundles."""
import argparse
import json
import os
from itertools import combinations
from pathlib import Path
from test_clause_hall import run,write,negative_checks
from check_clause_hall import check

def make_case(n=22,width=40,make_gap=False):
    gs=[[1+j*width+i for i in range(width)] for j in range(n)]
    clauses=[tuple(g) for g in gs]
    for group in gs:
        for a,b in combinations(group,2):clauses.append((-a,-b))
    for j,k in combinations(range(n),2):
        for t in range(width):
            for dt in (-1,0,1):
                u=t+dt
                if 0<=u<width:
                    if make_gap and j==0 and k==1 and t==0 and u==1:
                        continue
                    clauses.append((-gs[j][t],-gs[k][u]))
    if make_gap:
        picked={gs[0][0],gs[1][1]}
        picked.update(gs[j][2*j-1] for j in range(2,n))
        assert len(picked)==n and all(any(
            l>0 and l in picked or l<0 and -l not in picked
            for l in c) for c in clauses), 'SAT gap witness invalid'
    return clauses

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    a.output.mkdir(parents=True,exist_ok=False)
    outcomes=[]
    for name,n,gap,unsat in [('bundle_unsat22',22,False,True),
                             ('bundle_sat20',20,False,False),
                             ('bundle_gap_sat21',21,True,False)]:
        cnf=a.output/f'{name}.cnf'
        raw=write(cnf,make_case(n,40,gap))
        proof=a.output/f'{name}.json'
        r=run(a.binary,cnf,proof,budget=500)
        if unsat:
            assert r['rc']==20 and proof.exists(),(name,r)
            witness=json.loads(proof.read_text())
            assert check(raw,witness)['status']=='UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED'
            negative_checks(raw,witness)
            status='UNSAT_VERIFIED'
        else:
            assert r['rc']==0 and not proof.exists(),(name,r)
            status='UNKNOWN_SAFELY'
        entry={'case':name,'status':status,'native_s':r['seconds'],
               'n':n,'width':40,'reason':r['telemetry'].get('reason')}
        outcomes.append(entry)
        print('CLAUSE_HALL2_BUNDLE '+json.dumps(entry),flush=True)
    (a.output/'report.json').write_text(json.dumps(
        {'cases':outcomes,'single_cpu':cpu},indent=2)+'\n')
    print('CLAUSE_HALL2_BUNDLE_SUMMARY '+json.dumps(
        {'pass_count':len(outcomes)}),flush=True)

if __name__=='__main__':main()
