#!/usr/bin/env python3
"""COOP5.2 exact SAT/UNSAT oracle and REAL36 larger-source activation preflight."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import random

R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"research/drnas_coop1"))
sys.path.insert(0,str(R/"research"))
from synthetic import encode,oracle,text,model_ok
import drnas_x55_cpu_real36 as B

BIN=("drnas-coop52-cap24k","drnas-coop52-fallback")
CASES=[(0,[]),(0,[[]]),(1,[[1],[-1]]),(3,[[1,2],[-1,3],[-2,-3]])]
for mask in range(32):
    CASES.append((3,encode([1,2,3],lambda bits:bool(mask&(1<<sum(v<<i for i,v in enumerate(bits)))))))
rng=random.Random(520052)
for _ in range(35):
    n=rng.randrange(2,10)
    cs=[]
    for _ in range(rng.randrange(n,5*n)):
        vars_=rng.sample(range(1,n+1),rng.randrange(1,min(n,4)+1))
        cs.append([v*rng.choice((-1,1)) for v in vars_])
    CASES.append((n,cs))

def verify(src,p,expected,proof,clauses,n):
    if expected is None:
        assert p.returncode in (0,10,20,153),p.returncode
    else:
        assert p.returncode==(10 if expected else 20),(p.returncode,p.stderr[-350:])
    if p.returncode==10:
        assert model_ok(n,clauses,p.stdout)
    elif p.returncode==20:
        t=subprocess.run([str(R/"build/drat-trim"),str(src),str(proof)],
                         capture_output=True,text=True,timeout=18)
        assert t.returncode in (0,20) and "s VERIFIED" in t.stdout,(t.stdout[-250:],t.stderr[-250:])
    stats=[json.loads(s.split(" ",1)[1]) for s in p.stderr.splitlines()
           if s.startswith("COOP52_GATE ")]
    assert len(stats)==1,p.stderr[-700:]
    return stats[0]

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    count=0;unsat_proofs=0
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);source=td/"test.cnf";proof=td/"proof.drat"
        for name in BIN:
            binary=R/"build"/name
            assert binary.exists()
            for i,(n,clauses) in enumerate(CASES):
                source.write_text(text(n,clauses))
                expected=oracle(n,clauses)
                for mode in ("off","on"):
                    p=subprocess.run(
                      [str(binary),str(source),"--mode","core","--time","1.0",
                       "--x5-no-minimize","--stats","--coop4","on",
                       "--coop5",mode,"--proof",str(proof)],
                      capture_output=True,text=True,timeout=3)
                    stats=verify(source,p,expected,proof,clauses,n)
                    assert stats["algebra_disabled"] is False
                    assert stats["originals_retained"]==len(clauses)
                    assert stats["fallback_policy"]==(name=="drnas-coop52-fallback")
                    if p.returncode==20:unsat_proofs+=1
                    count+=1
        originals,_=B.official_manifest()
        selected=next(x for x in originals if x["id"]==5)
        assert selected["nvars"]==2672 and selected["nclauses"]==16408
        n,cs=B.parse_cnf(Path(selected["path"]).read_bytes())
        assert n==2672 and len(cs)==16408
        for name in BIN:
            binary=R/"build"/name
            p=subprocess.run(
               [str(binary),str(selected["path"]),"--mode","core",
                "--time","0.4","--x5-no-minimize","--stats",
                "--coop4","on","--coop5","on","--proof",str(proof)],
                capture_output=True,text=True,timeout=3)
            st=verify(Path(selected["path"]),p,None,proof,cs,n)
            assert not st["algebra_disabled"],st
            assert st["originals_retained"]==16408,st
            print("COOP52_PLANNING_COLLECTOR_PASS",name,json.dumps(st,sort_keys=True),flush=True)
    print("COOP52_SAFETY_PASS",json.dumps({
       "tiny_oracle_cases":len(CASES),"oracle_trials":count,
       "unsat_proofs_independent":unsat_proofs,
       "planning_real36_id":5,"planning_clauses_retained":16408,
       "binary_variants":list(BIN),
       "no_false_SAT_or_UNSAT":True},sort_keys=True),flush=True)
if __name__=="__main__":
    main()
