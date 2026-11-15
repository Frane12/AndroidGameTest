#!/usr/bin/env python3
"""TRAIL1: deterministic gated mixed CNFs whose components become visible
only AFTER a CDCL decision, plus UNSAT negative and independent SAT checks."""
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/sat_local1"))
from selftest import fixture,dimacs,model
BINARY=ROOT/"build/drnas-sat-trail-x59"

def gated(seed,unsat=False):
    n,source=fixture(seed,connected=False)
    aux=24
    gate=1
    clauses=[[-gate]+[(1 if l>0 else -1)*(abs(l)+1) for l in c]
             for c in source]
    # Clauses (g or z) and (g or not z) logically force the gate TRUE,
    # but require a CDCL decision or propagation to discover that fact.
    # The gate is the most frequent literal, with positive phase.
    for v in range(n+2,n+aux+2):
        clauses.extend([[gate,v],[gate,-v]])
    if unsat:
        clauses.extend([[-gate,7],[-gate,-7]])
    total=1+n+aux
    rng=random.Random(seed+847)
    # Identical logical family, independent anonymous variable IDs/order.
    renaming=list(range(1,total+1))
    rng.shuffle(renaming)
    transformed=[[renaming[abs(l)-1]*(1 if l>0 else -1) for l in c]
                 for c in clauses]
    rng.shuffle(transformed)
    return total,transformed

def run(n,clauses,mode):
    flags={"OFF":[],"SHADOW":["--sat-trail-ms","12","--sat-trail-shadow"],
           "ACTIVE":["--sat-trail-ms","12"]}[mode]
    with tempfile.TemporaryDirectory() as directory:
        d=Path(directory)
        cnf=d/"source.cnf"
        cnf.write_text(dimacs(n,clauses))
        proof=d/"proof.drat"
        cmd=[str(BINARY),str(cnf),"--mode","core","--time","2",
             "--proof",str(proof),"--stats",*flags]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=3)
        if p.returncode not in (10,20):
            raise AssertionError((mode,"unknown_or_error",p.returncode,p.stderr[-1200:]))
        if p.returncode==10:
            assert "s SATISFIABLE" in p.stdout
            assert model(n,clauses,p.stdout),("BAD SAT model",mode,p.stdout)
        else:
            assert "s UNSATISFIABLE" in p.stdout
            assert proof.exists() and proof.stat().st_size>0
        rows=[json.loads(line.partition(" ")[2]) for line in p.stderr.splitlines()
              if line.startswith("SAT_TRAIL_STATS ")]
        assert len(rows)==1,(mode,p.stderr)
        return p.returncode,rows[0]

def main():
    assert BINARY.is_file()
    results={"SAT":0,"UNSAT":0,"ACTIVE_FULL":0,
             "SHADOW_FULL_CANDIDATES":0,"TRAIL_ATTEMPTS":0,"PHASE_USES":0}
    for seed in range(20):
        n,clauses=gated(18000+seed)
        for mode in ("OFF","SHADOW","ACTIVE"):
            rc,data=run(n,clauses,mode)
            assert rc==10,("known_SAT",seed,mode,rc)
            if mode=="SHADOW":
                assert data["shadow"] and not data["full"]
                results["SHADOW_FULL_CANDIDATES"]+=data["full_candidates"]
            if mode=="ACTIVE":
                results["ACTIVE_FULL"]+=int(data["full"])
                results["TRAIL_ATTEMPTS"]+=data["attempts"]
                results["PHASE_USES"]+=data["phase_uses"]
        results["SAT"]+=1
    for seed in range(10):
        n,clauses=gated(24000+seed,unsat=True)
        for mode in ("OFF","SHADOW","ACTIVE"):
            rc,data=run(n,clauses,mode)
            assert rc==20,("known_UNSAT",seed,mode,rc)
            assert not data["full"],data
        results["UNSAT"]+=1
    if results["ACTIVE_FULL"]==0:
        raise AssertionError(("no residual SAT constructed after trail decision",results))
    print("SAT_TRAIL_SELFTEST "+json.dumps(
        dict(cases=30,trials=90,violations=0,results=results)),flush=True)

if __name__=="__main__":main()
