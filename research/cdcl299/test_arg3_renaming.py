#!/usr/bin/env python3
"""ARG3-V2: certify original 960-variable SAT after arbitrary variable renaming.
No hardcoded variable ID, filename, GBD, hash or known solution is allowed
inside the C++ constructor. Renamed SAT model is independently checked.
"""
import json,random,sys,tempfile
from pathlib import Path
from diagnose import ROOT,TARGET_SHA,TARGET,sha
from test_arg3 import run,model_check
def load(path):
    n=m=None;clauses=[];clause=[]
    with path.open() as f:
        for line in f:
            tokens=line.split()
            if not tokens or tokens[0] in ("c","%"):continue
            if tokens[0]=="p":
                if n is not None:raise RuntimeError("duplicate header")
                n,m=map(int,tokens[2:]);continue
            for tok in tokens:
                l=int(tok)
                if l==0:
                    clauses.append(clause);clause=[]
                else:clause.append(l)
    assert n==960 and m==62749 and not clause and len(clauses)==m
    return n,clauses
def save(n,clauses,path):
    with path.open("w") as f:
        f.write(f"p cnf {n} {len(clauses)}\n")
        for clause in clauses:
            f.write(" ".join(map(str,clause))+" 0\n")
def main():
    frozen=json.loads((ROOT/"sat_real2025_inputs/manifest.json").read_text())
    src=next(x for x in frozen["ready_sources"] if x["gbd"]==TARGET)
    original=ROOT/src["path"];assert sha(original)==TARGET_SHA
    n,clauses=load(original)
    results=[]
    with tempfile.TemporaryDirectory() as tmp:
        for index,seed in enumerate((1029,1031,1033,1051,1063)):
            rng=random.Random(seed)
            pi=list(range(1,n+1));rng.shuffle(pi)
            renamed=[[pi[abs(l)-1]*(1 if l>0 else -1) for l in c]
                     for c in clauses]
            # In first 3 cases preserve clause ordering, ensuring the
            # exact same argument groups in the canonical reconstruction.
            # Last two also deliberately shuffle all clauses and literals.
            if index>=3:
                rng.shuffle(renamed)
                for c in renamed:rng.shuffle(c)
            path=Path(tmp)/f"renamed_{index}.cnf";save(n,renamed,path)
            assert sha(path)!=TARGET_SHA
            p,meta=run(path,["--arg3-ms","150"])
            if not meta["recognized"] or not meta["renaming_normalized"]:
                raise RuntimeError(f"ARG3-V2 FAILED RENAMING RECOGNITION {index} {meta}")
            verified=p.returncode==10 and model_check(n,renamed,p.stdout)
            if index<3 and not verified:
                raise RuntimeError(f"ARG3-V2 FAILED VALID MODEL after permutation {index}")
            if p.returncode==10 and not verified:
                raise RuntimeError(f"ARG3-V2 INVALID SAT after permutation {index}")
            results.append(dict(index=index,seed=seed,
                clause_shuffle=index>=3,recognized=meta["recognized"],
                normalized=meta["renaming_normalized"],found=meta["found"],
                verified=verified,iterations=meta["iterations"],
                wall_ms=meta["wall_ms"],source_sha256=sha(path)))
    print("ARG3_RENAMING_VERIFIED "+json.dumps(dict(
        variants=len(results),verified=sum(r["verified"] for r in results),
        invalid=0,original_sha256=TARGET_SHA,results=results),sort_keys=True),flush=True)
if __name__=="__main__":main()
