#!/usr/bin/env python3
"""GF2 width5/6 soundness and explicit full source verification."""
import itertools,json,random,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"build/drnas-sat-construct"
FUSED=ROOT/"build/drnas-sat-native-x59"
def encoded_xor(vars,bits):
    p=sum(bits[v-1] for v in vars)&1
    clauses=[]
    for a in itertools.product((0,1),repeat=len(vars)):
        if (sum(a)&1)==p:continue
        clauses.append([-v if bit else v for v,bit in zip(vars,a)])
    return clauses
def check_case(n,clauses,expected=True):
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/"x.cnf"
        path.write_text(f"p cnf {n} {len(clauses)}\n"+"".join(
            " ".join(map(str,c))+" 0\n" for c in clauses))
        for binary,args in ((BIN,["--max-ms","120","--stats"]),
                            (FUSED,["--mode","core","--time","2",
                                    "--sat-construct-ms","120","--stats"])):
            p=subprocess.run([str(binary),str(path),*args],
                             capture_output=True,text=True,timeout=3)
            if p.returncode not in (0,10,20):raise RuntimeError(p.stderr[-500:])
            if binary==BIN and p.returncode==20:raise RuntimeError("native asserted UNSAT")
            if expected and p.returncode!=10:raise RuntimeError(
                f"known pure XOR SAT must be constructible rc={p.returncode} err={p.stderr[-250:]}")
            if p.returncode!=10:continue
            model={}
            for row in p.stdout.splitlines():
                if row.startswith("v "):
                    for w in row[2:].split():
                        v=int(w)
                        if not v:continue
                        if abs(v) in model and model[abs(v)]!=(v>0):
                            raise RuntimeError("contradictory model")
                        model[abs(v)]=(v>0)
            assert len(model)==n
            assert all(any(model[abs(v)]==(v>0) for v in c) for c in clauses)
            if binary==BIN:
                meta=next(json.loads(x.split(" ",1)[1]) for x in p.stderr.splitlines()
                          if x.startswith("SAT_NATIVE_STATS "))
                if meta["method"]!="GF2":raise RuntimeError(("wrong method",meta))
def main():
    rng=random.Random(202611150061)
    cases=0
    for width in (5,6):
        for i in range(40):
            n=width+3+i%5
            bits=[rng.getrandbits(1) for _ in range(n)]
            clauses=[]
            for eq in range(n+8):
                vars=sorted(rng.sample(range(1,n+1),width))
                clauses.extend(encoded_xor(vars,bits))
            rng.shuffle(clauses)
            check_case(n,clauses)
            cases+=1
    print("GF2_WIDE_SOURCE_VERIFIED "+json.dumps(dict(widths=[5,6],
          source_cases=cases,implementations=["standalone_C++","X59_native"],
          invalid_answers=0)),flush=True)
if __name__=="__main__":main()
