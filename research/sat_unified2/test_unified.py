#!/usr/bin/env python3
"""Independent exact SAT-model checks for UNIFIED2. Not a blind benchmark."""
import itertools,json,random,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"build/drnas-sat-construct"
FUSED=ROOT/"build/drnas-sat-native-x59"
def is_sat(n,clauses,values):
    return all(any(values[abs(l)-1]==(l>0) for l in c) for c in clauses)
def check(n,clauses,expect_sat=None,tag=""):
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"x.cnf"
        p.write_text(f"p cnf {n} {len(clauses)}\n"+
            "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        for exe,flags in ((BIN,["--max-ms","80","--stats"]),
                          (FUSED,["--mode","core","--time","0.75","--sat-construct-ms","80","--stats"])):
            proc=subprocess.run([str(exe),str(p),*flags],
                capture_output=True,text=True,timeout=2)
            if proc.returncode not in (0,10,20):
                raise RuntimeError((tag,"NATIVE_CRASH",proc.returncode,proc.stderr[-300:]))
            if exe==BIN and proc.returncode==20:
                raise RuntimeError(("constructor must never assert UNSAT",tag))
            if proc.returncode==10:
                assign={}
                for row in proc.stdout.splitlines():
                    if row.startswith("v "):
                        for w in row[2:].split():
                            lit=int(w)
                            if not lit:continue
                            if abs(lit) in assign and assign[abs(lit)]!=(lit>0):
                                raise RuntimeError(("duplicate inconsistent",tag))
                            assign[abs(lit)]=(lit>0)
                if len(assign)!=n or not is_sat(n,clauses,[assign[i] for i in range(1,n+1)]):
                    raise RuntimeError(("INVALID_SAT",tag,exe))
            if expect_sat is False and proc.returncode==10:
                raise RuntimeError(("false SAT for proven UNSAT",tag))
            if expect_sat is True and exe==BIN and proc.returncode!=10:
                raise RuntimeError(("failed required positive category",tag,proc.stderr[-200:]))
        return True

def main():
    assert BIN.is_file() and FUSED.is_file()
    rng=random.Random(0xFC261115)
    counts={}
    samples=[
      ("renamable_horn",6,[[1],[-1,-2],[2,-3,4],[-4,5],[-5,-6]],True),
      ("pure_mixed",6,[[1,2,3],[-4,-5,-6],[1,-4]],True),
      ("unit_and_pure",6,[[1],[-1,2,3],[-2,4,5]],True),
      ("small_general",5,[[1,2,3],[-1,4,5],[-2,-3,5],[2,-4,-5]],True),
      ("unsat_simple",3,[[1,2,3],[-1],[-2],[-3]],False),
    ]
    # Non-interacting classes: one 3-XOR block plus one positive exact-one
    # resource assignment block. Only a component-aware solution can naturally
    # combine independently generated submodels.
    clause_a=[]
    for assignment in itertools.product((0,1),repeat=3):
        if sum(assignment)%2==0:continue
        clause_a.append([( -v if bit else v) for v,bit in zip((1,2,3),assignment)])
    clauses_b=[[4,5],[6,7],[-4,-5],[-6,-7],
              [-4,-6],[-5,-7]] # match 4 with 7, 5 with 6.
    samples.append(("mixed_components",7,clause_a+clauses_b,True))
    for name,n,clauses,valid in samples:
        check(n,clauses,expect_sat=valid,tag=name)
        counts[name]=1
    # Exhaustive oracle on n<=9: every SAT claim must match brute truth.
    for i in range(110):
        n=5+(i%5);clauses=[]
        model=[rng.randrange(2)==1 for _ in range(n)]
        for j in range(5+n*2):
            width=2+(j%3)
            vs=rng.sample(range(1,n+1),width)
            c=[v if rng.randrange(2) else -v for v in vs]
            clauses.append(c)
        truth=any(is_sat(n,clauses,values) for values in
                  itertools.product((False,True),repeat=n))
        check(n,clauses,expect_sat=False if not truth else None,tag=f"fuzz_{i}")
        counts["fuzz"] = counts.get("fuzz",0)+1
    print("SAT_UNIFIED2_CONTROLS "+json.dumps(dict(counts=counts,violations=0)),flush=True)
if __name__=="__main__":main()
