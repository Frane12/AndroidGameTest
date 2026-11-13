#!/usr/bin/env python3
"""X4.5: truth-table oracle + predecision feature invariants + label audit."""
from __future__ import annotations
import hashlib,itertools,json,random,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,'research')
import drnas_x45_counterfactual as X


def exhaustive(n,clauses):
    return any(all(any(bits[abs(l)-1]==(l>0) for l in c) for c in clauses)
               for bits in itertools.product((False,True),repeat=n))

def call(binary,path,k,sign,cap=1.0):
    r=subprocess.run([str(binary),str(path),'--mode','core','--time',str(cap),
         '--stats','--checkpoint',str(k),'--force-polarity',str(sign)],
         capture_output=True,text=True,timeout=cap+2)
    if r.returncode not in (0,10,20):raise AssertionError((r.returncode,r.stderr[-700:]))
    stats=None;cp=None
    tag='X45' if 'x45' in binary.name else 'X44'
    for line in r.stderr.splitlines():
        if line.startswith(tag+'_STATS '):stats=json.loads(line[len(tag+'_STATS '):])
        if line.startswith(tag+'_CHECKPOINT '):cp=json.loads(line[len(tag+'_CHECKPOINT '):])
    assert stats is not None
    return r,stats,cp

def run_test():
    x45=Path('build/drnas-x45');x44=Path('build/drnas-x44')
    if not x45.exists() or not x44.exists():raise RuntimeError('build X44 and X45')
    rng=random.Random(20261113)
    verified=0;prestates=0;unchanged=0
    with tempfile.TemporaryDirectory() as td:
        for i in range(220):
            n=rng.randrange(2,10)
            cl=[[rng.choice((-1,1))*rng.randrange(1,n+1) for _ in range(rng.randrange(1,5))]
                for _ in range(rng.randrange(3,27))]
            if i%5==0:cl.extend([[1,-1],[2,-2]])
            path=Path(td)/f'tiny_{i}.cnf'
            path.write_text(f'p cnf {n} {len(cl)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cl))
            expected=10 if exhaustive(n,cl) else 20
            a,sa,_=call(x44,path,-1,0)
            b,sb,_=call(x45,path,-1,0)
            assert a.returncode==b.returncode==expected,(i,expected,a.returncode,b.returncode)
            for key in ('decisions','conflicts','propagations','learnt','restarts'):
                assert sa[key]==sb[key],(i,key,sa[key],sb[key])
            unchanged+=1
            if expected==10:assert X.independent_witness(path,b.stdout,n)
            if sa['decisions']:
                p,ps,pc=call(x45,path,0,1)
                q,qs,qc=call(x45,path,0,-1)
                assert pc is not None and qc is not None
                X.assert_same_prestate(pc,qc,dict(formula_id=str(i)))
                assert pc['prestate_fingerprint']==qc['prestate_fingerprint']
                for result in (p,q):
                    assert result.returncode==expected,(i,result.returncode,expected)
                    if expected==10:assert X.independent_witness(path,result.stdout,n)
                # Repeated plus must have deterministic complete features/state.
                r,rs,rc=call(x45,path,0,1)
                X.assert_same_prestate(pc,rc,dict(formula_id=str(i)))
                assert r.returncode==expected
                prestates+=1
            verified+=1
        # Test frozen 300-CNF source selection & reproducible SHA without outcomes.
        X.ROOT=Path(td)/'frozen'
        X.OLD.ROOT=X.ROOT
        s,sha=X.manifest()
        assert len(s)==300 and len(set(x['sha256'] for x in s))==300
        for split,fs in X.OLD.G.SPLITS.items():
            assert sum(x['split']==split for x in s)==len(fs)*30
        assert hashlib.sha256((X.ROOT/'manifest.json').read_bytes()).hexdigest()==sha
    print('X45_ORACLE_PASS '+json.dumps(dict(tiny_sources=verified,unchanged_core=unchanged,
        matching_prestate_checks=prestates,manifest_sources=len(s),family_disjoint=True)))

if __name__=='__main__':run_test()
