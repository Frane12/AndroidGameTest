#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research/drnas_coop1"))
from synthetic import xor, text as cnf_text, model_ok
BINARY=ROOT/"build/drnas-coop4-audit";DRAT=ROOT/"build/drat-trim"
def check(name,n,cs,expected):
    with tempfile.TemporaryDirectory() as t:
        p=pathlib.Path(t);cnf=p/"source.cnf";cnf.write_text(cnf_text(n,cs))
        for mode in ("off","algebra","on","fresh"):
            proof=p/(mode+".drat")
            cmd=[str(BINARY),str(cnf),"--mode","core","--time","2","--stats",
                 "--x5-no-minimize","--proof",str(proof),"--coop4",("on" if mode=="fresh" else mode)]
            if mode=="fresh":cmd.append("--coop4-audit-fresh")
            r=subprocess.run(cmd,capture_output=True,text=True,timeout=5)
            assert r.returncode==expected,(name,mode,r.returncode,r.stderr[-1000:])
            if expected==10:assert model_ok(n,cs,r.stdout),(name,mode)
            else:
                z=subprocess.run([str(DRAT),str(cnf),str(proof)],capture_output=True,text=True,timeout=5)
                assert z.returncode==0 and "s VERIFIED" in z.stdout,(name,mode,z.stdout[-400:])
            t=[json.loads(x.split(" ",1)[1]) for x in r.stderr.splitlines()
               if x.startswith("COOP4_HINT_AUDIT ")]
            assert len(t)==1 and t[0]["fresh"]==(mode=="fresh"),(name,mode,t)
            if mode=="fresh":assert t[0]["stale_overrides"]==0
def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    check("simple_sat",3,[[1,2],[-1,3]],10)
    check("xor_sat",4,xor([1,2,3],0)+xor([1,2,4],1),10)
    check("unit_unsat",1,[[1],[-1]],20)
    check("all_unsat",2,[[1,2],[1,-2],[-1,2],[-1,-2]],20)
    print('COOP4_HINT_AUDIT_SAFETY_PASS {"sources":4,"verified_results":16,"fresh_shields_stale":true}',flush=True)
if __name__=="__main__":main()
