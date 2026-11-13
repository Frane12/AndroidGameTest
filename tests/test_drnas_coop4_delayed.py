#!/usr/bin/env python3
"""Delayed COOP4 gate: fast-path CDCL must be untouched and proof-correct."""
import json, os, pathlib, subprocess, tempfile, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"research/drnas_coop1"))
from synthetic import text, model_ok, xor

ROOT=pathlib.Path(__file__).resolve().parents[1]
BIN=ROOT/"build/drnas-coop4"
DRAT=ROOT/"build/drat-trim"

def run(cnf,cs,n,mode,eager=False):
    proof=cnf.parent/(mode+("_eager" if eager else "")+".drat")
    cmd=[str(BIN),str(cnf),"--mode","core","--time","3","--stats",
         "--proof",str(proof),"--coop4",mode]
    if eager:cmd+=["--coop4-eager"]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=6)
    assert p.returncode in (10,20),(mode,p.returncode,p.stderr[-1200:])
    if p.returncode==10:
        assert model_ok(n,cs,p.stdout),(cnf,mode)
    else:
        c=subprocess.run([str(DRAT),str(cnf),str(proof)],capture_output=True,text=True,timeout=10)
        assert c.returncode==0 and "s VERIFIED" in c.stdout,(mode,c.stdout,c.stderr)
    stats=json.loads(next(line.split(" ",1)[1] for line in p.stderr.splitlines()
                          if line.startswith("COOP4_STATS ")))
    assert stats["mode"]==mode
    assert stats["delayed"]==(not eager)
    return p.returncode,stats

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cases=[
        ("simple_sat",4,[[1,2],[-1,3],[-3,4]],10),
        ("parity",4,xor([1,2,3],0)+xor([1,2,4],1),10),
        ("unsat",2,[[1,2],[1,-2],[-1,2],[-1,-2]],20),
        ("unsat_units",1,[[1],[-1]],20),
    ]
    checks=0
    with tempfile.TemporaryDirectory() as td:
        path=pathlib.Path(td)
        for name,n,cs,expected in cases:
            cnf=path/(name+".cnf");cnf.write_text(text(n,cs))
            baseline=None
            for mode in ("off","observe","algebra","on","gate","retain"):
                rc,stats=run(cnf,cs,n,mode)
                assert rc==expected,(name,mode,rc,expected)
                assert stats["prepared"] is False,(name,mode,"unexpected eager preparation")
                assert stats["lemmas"]==0,(name,mode,"unexpected lemma before conflict gate")
                if baseline is None:baseline=rc
                else:assert rc==baseline
                checks+=1
    print("COOP4_DELAYED_SAFETY_PASS "+json.dumps(
       {"sources":len(cases),"certified_results":checks,
        "fast_path_preparation_skipped":True,"disabled_until_conflict":64},sort_keys=True))
if __name__=="__main__":main()
