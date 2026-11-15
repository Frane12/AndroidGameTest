#!/usr/bin/env python3
"""Native local hybrid: deterministic SAT-positive mixed formulas, conflicting
source controls, independent complete original-model checks, ON/OFF/SHADOW."""
import itertools
import json
import random
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
X59=ROOT/"build/drnas-sat-local-x59"
NATIVE=ROOT/"build/drnas-sat-construct"

def xor3(vs,parity):
    out=[]
    for bits in itertools.product((0,1),repeat=3):
        if sum(bits)%2==parity:
            continue
        out.append([v if b==0 else -v for v,b in zip(vs,bits)])
    return out

def fixture(seed,connected=False,unsat=False):
    r=random.Random(seed)
    clauses=[
        [1],[-1,2],[-2,3],              # closed Horn component
        [4,5],[-4,5],[4,-5],          # closed 2-SAT component
        [9,10],[11,12],[-9,-10],[-11,-12],[-9,-11],[-10,-12] # MATCH
    ]
    clauses+=xor3([6,7,8],0)            # closed XOR component
    n=12
    if connected:
        n=13
        clauses+=[[-6,9,13],[-3,4,13],[13]] # three components joined by 13
        # Connected via clauses, but the 3-variable signed XOR remains intact.
        clauses+=[[-5,6,13]]
    if unsat:
        clauses+=[[4],[-4]]
    # Randomly remap all names and randomize original clause ordering; no
    # generator metadata ever reaches the solver.
    mapping=list(range(1,n+1))
    r.shuffle(mapping)
    clauses=[[mapping[abs(l)-1]*(1 if l>0 else -1) for l in c]
             for c in clauses]
    r.shuffle(clauses)
    return n,clauses

def dimacs(n,clauses):
    return (f"p cnf {n} {len(clauses)}\n"+
            "".join(" ".join(map(str,c))+" 0\n" for c in clauses))

def model(n,cs,stdout):
    d={}
    for line in stdout.splitlines():
        if not line.startswith("v "):
            continue
        for term in line[2:].split():
            l=int(term)
            if not l:
                continue
            if abs(l)>n or (abs(l) in d and d[abs(l)]!=(l>0)):
                return False
            d[abs(l)]=l>0
    return len(d)==n and all(any(d[abs(l)]==(l>0) for l in c) for c in cs)

def run(path,mode,limit=2):
    flags={
        "OFF":[],
        "SHADOW":["--sat-local-ms","15","--sat-local-shadow"],
        "ACTIVE":["--sat-local-ms","15"],
    }[mode]
    p=subprocess.run([str(X59),str(path),"--mode","core","--time",str(limit),
                      "--stats",*flags],capture_output=True,text=True,timeout=limit+1)
    if p.returncode not in (0,10,20):
        raise RuntimeError((mode,p.returncode,p.stderr[-1000:]))
    rows=[json.loads(l.split(" ",1)[1]) for l in p.stderr.splitlines()
          if l.startswith("SAT_LOCAL_STATS ")]
    assert len(rows)==1,(p.stderr,mode)
    return p,rows[0]

def main():
    assert X59.exists() and NATIVE.exists()
    seen,counts=0,{}
    legacy_solved=0
    for connected in (False,True):
        for seed in range(24):
            n,cs=fixture(10000+seed,connected)
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/"source.cnf"
                path.write_text(dimacs(n,cs))
                for mode in ("OFF","SHADOW","ACTIVE"):
                    p,t=run(path,mode)
                    assert p.returncode==10 and model(n,cs,p.stdout),(
                        seed,connected,mode,p.returncode,p.stdout,p.stderr)
                    if mode=="ACTIVE" and not connected:
                        assert t["full"] and t["solved_components"]>=4,(seed,t)
                        assert t["components"]>=4,(seed,t)
                    if mode=="ACTIVE" and connected:
                        assert t["xor_patterns"]>=1 and t["hints"]>=3,(seed,t)
                    if mode=="SHADOW":
                        assert t["shadow"] and not t["full"],t
                # Global legacy constructor was not designed for mixed forms.
                legacy=subprocess.run([str(NATIVE),str(path),"--max-ms","15"],
                                      capture_output=True,text=True,timeout=1)
                assert legacy.returncode in (0,10),legacy.stderr
                if legacy.returncode==10:
                    assert model(n,cs,legacy.stdout),("invalid legacy model",seed)
                    legacy_solved+=1
            seen+=1
            counts["CONNECTED" if connected else "CLOSED_COMPONENTS"]=counts.get(
                "CONNECTED" if connected else "CLOSED_COMPONENTS",0)+1
    for seed in range(8):
        n,cs=fixture(20000+seed,connected=True,unsat=True)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"source.cnf"
            path.write_text(dimacs(n,cs))
            for mode in ("OFF","SHADOW","ACTIVE"):
                p,_=run(path,mode)
                assert p.returncode==20 and "s UNSATISFIABLE" in p.stdout,(seed,mode,p.stderr)
        counts["UNSAT_NEGATIVE"]=counts.get("UNSAT_NEGATIVE",0)+1
    print("LOCAL_HYBRID_SELFTEST "+json.dumps(
        dict(cases=seen+8,solver_trials=seen*3+8*3,
             counts=counts,violations=0,standalone_legacy_sat=legacy_solved,
             standalone_legacy_unknown=48-legacy_solved)),flush=True)

if __name__=="__main__":
    main()
