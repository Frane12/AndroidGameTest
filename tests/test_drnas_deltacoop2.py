#!/usr/bin/env python3
"""Independent exhaustive semantics, affine countermodels and RUP validation."""
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile

R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'tests'))
from test_drnas_coop52 import CASES,oracle,text,model_ok
sys.path.insert(0,str(R/'research/drnas_coop1'))
from synthetic import encode

def signal_cases():
    out=[]
    for seed in range(12):
        rng=random.Random(26021114+seed)
        p=list(range(1,10));rng.shuffle(p)
        signs={v:rng.choice((-1,1)) for v in range(1,10)}
        a=encode([1,2,3,4,5,6],lambda b:sum(b[j]<<j for j in range(3)) in {0,1,2,4})
        b=encode([1,2,3,7,8,9],lambda b:sum(b[j]<<j for j in range(3)) in {1,3,5,6})
        cs=a+b
        if seed%3==1:cs+=[[-1]]
        if seed%3==2:cs+=[[-1,10],[-10,11]]
        cs=[[p[abs(l)-1]*signs[abs(l)]*(1 if l>0 else -1) if abs(l)<=9 else l for l in c] for c in cs]
        rng.shuffle(cs)
        out.append((11 if seed%3==2 else 9,cs))
    return out

def bcp(clauses,assumptions):
    vals={}
    for l in assumptions:
        if abs(l) in vals and vals[abs(l)]!=(l>0):return None
        vals[abs(l)]=l>0
    changed=True
    while changed:
        changed=False
        for c in clauses:
            if any(abs(l) in vals and vals[abs(l)]==(l>0) for l in c):continue
            free=[l for l in c if abs(l) not in vals]
            if not free:return None
            if len(free)==1:
                l=free[0];vals[abs(l)]=l>0;changed=True
    return vals

def check_rup(clauses,path):
    active={tuple(sorted(c)) for c in clauses}
    additions=0
    for line in path.read_text().splitlines():
        if not line.strip():continue
        tokens=line.split();delete=tokens[0]=='d'
        c=tuple(sorted(map(int,tokens[int(delete):-1])))
        if delete:active.discard(c);continue
        if c not in active:
            assert bcp(active,[-l for l in c]) is None,('NON_RUP_ADDITION',c)
        active.add(c);additions+=1
    return additions

def points(block,assumptions):
    vs=block['vars'];clauses=block['cnf'];a={abs(l):l>0 for l in assumptions}
    return [x for x in range(1<<len(vs))
            if all(bool(x&(1<<j))==a[v] for j,v in enumerate(vs) if v in a)
            and all(any(bool(x&(1<<vs.index(abs(l))))==(l>0) for l in c) for c in clauses)]

def hull_points(ps):
    if not ps:return set()
    span={0}
    for p in ps:span|={v^(p^ps[0]) for v in list(span)}
    return {v^ps[0] for v in span}

def check_witness(w):
    vs=w['union_vars'];a=w['left'];b=w['right'];unit=w['unit'];x=w['affine_countermodel']
    ap=points(a,w['assumptions']);bp=points(b,w['assumptions'])
    def proj(y,bs):return sum(((y>>vs.index(v))&1)<<j for j,v in enumerate(bs))
    ah=hull_points(ap);bh=hull_points(bp)
    assert proj(x,a['vars']) in ah and proj(x,b['vars']) in bh
    if w.get('kind')=='tuple':
        blocked=w['blocked_left_tuple']
        assert proj(x,a['vars'])==blocked and blocked in ap
        assert not any(proj(y,a['vars'])==blocked and proj(y,b['vars']) in bp for y in range(1<<len(vs)))
        return True
    assert not unit or bool(x&(1<<vs.index(abs(unit))))!=(unit>0)
    joint=[y for y in range(1<<len(vs)) if proj(y,a['vars']) in ap and proj(y,b['vars']) in bp]
    if not unit:assert not joint
    else:
        assert joint
        assert all(bool(y&(1<<vs.index(abs(unit))))==(unit>0) for y in joint)
        for bl,ps in ((a,ap),(b,bp)):
            if abs(unit) in bl['vars']:
                assert len({bool(y&(1<<bl['vars'].index(abs(unit)))) for y in ps})==2
    return True

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cases=CASES+signal_cases()
    totals={'solver_runs':0,'unsat_proofs':0,'rup_additions':0,'affine_witnesses':0,'nonlinear_certified':0,'cascade_forces':0}
    with tempfile.TemporaryDirectory() as td:
        src=Path(td)/'original.cnf';proof=Path(td)/'proof.drat'
        for index,(n,cs) in enumerate(cases):
            src.write_text(text(n,cs));expected=oracle(n,cs)
            controls={}
            for mode in ('off','local','shadow','join'):
                cmd=[str(R/'build/drnas-deltacoop2'),str(src),'--mode','core','--time','2','--stats',
                     '--x5-no-minimize','--coop4','off' if mode=='off' else 'gate',
                     '--coop4-eager','--coop5','off','--delta2','local' if mode=='off' else mode,
                     '--proof',str(proof)]
                p=subprocess.run(cmd,capture_output=True,text=True,timeout=4)
                assert p.returncode==(10 if expected else 20),(index,mode,p.stderr[-500:])
                if expected:assert model_ok(n,cs,p.stdout),(index,mode)
                else:
                    q=subprocess.run([str(R/'build/drat-trim'),str(src),str(proof)],capture_output=True,text=True,timeout=20)
                    assert q.returncode>=0 and 's VERIFIED' in q.stdout,(index,mode,q.stderr[-300:],q.stdout[-300:])
                    totals['unsat_proofs']+=1
                totals['rup_additions']+=check_rup(cs,proof)
                stats=json.loads(next(l.split(' ',1)[1] for l in p.stderr.splitlines() if l.startswith('DELTA2_JOIN ')))
                delta=json.loads(next(l.split(' ',1)[1] for l in p.stderr.splitlines() if l.startswith('DELTA_COOP1 ')))
                core=json.loads(next(l.split(' ',1)[1] for l in p.stderr.splitlines() if l.startswith('X41_STATS ')))
                controls[mode]=(core['decisions'],core['conflicts'])
                if mode in ('off','shadow'):assert delta['certified_lemmas']==0
                if mode=='local':assert stats['pair_evaluations']==0
                totals['nonlinear_certified']+=stats['join_nonlinear_certified']
                totals['cascade_forces']+=delta['cascade_forces']
                for line in p.stderr.splitlines():
                    if line.startswith('DELTA2_WITNESS '):
                        check_witness(json.loads(line.split(' ',1)[1]));totals['affine_witnesses']+=1
                totals['solver_runs']+=1
            assert controls['off']==controls['shadow'],('SHADOW_CHANGED_SEARCH',index,controls)
    assert totals['nonlinear_certified']>0 and totals['affine_witnesses']>0 and totals['cascade_forces']>0,totals
    out=R/'delta2_preflight';out.mkdir(exist_ok=True)
    (out/'report.json').write_text(json.dumps(totals,indent=2)+'\n')
    print('DELTA2_PREFLIGHT_PASS',json.dumps(totals,sort_keys=True),flush=True)

if __name__=='__main__':main()
