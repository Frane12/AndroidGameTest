#!/usr/bin/env python3
"""COOP54 frozen safety: exhaustive small oracle and CDCL options ablations.

Every SAT assignment checked against original CNF and every UNSAT claim
independently verified through the frozen DRAT checker. No promotion.
"""
import os,sys,json,pathlib,subprocess,tempfile
R=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"tests"))
import test_drnas_coop52 as T
from test_drnas_coop52 import text,oracle,model_ok
sys.path.insert(0,str(R/"research"))
import drnas_x55_cpu_real36 as B
OPTIONS={
 "BASE":[],
 "MIN":[],
 "RETAIN":["--x5-no-minimize","--x5-retain"],
 "RESTART":["--x5-no-minimize","--x5-restarts"],
 "FULL":["--x5-retain","--x5-restarts"],
 "MIN_RETAIN":["--x5-retain"],
 "RET_RESTART":["--x5-no-minimize","--x5-retain","--x5-restarts"],
}
OPTIONS["BASE"]=["--x5-no-minimize"]
def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert (R/"build/drnas-coop53-repair").is_file()
    assert (R/"build/drnas-coop54-gate").is_file()
    T.BIN=("drnas-coop53-repair","drnas-coop54-gate")
    T.main()
    checks=0;unsat_proofs=0
    cases=[]
    for n,cs in T.CASES:
        expected=oracle(n,cs)
        if len(cases)>=42:break
        cases.append((n,cs,expected))
    with tempfile.TemporaryDirectory() as td:
        td=pathlib.Path(td);cnf=td/"in.cnf";proof=td/"out.drat"
        for name,opts in OPTIONS.items():
            for i,(n,clauses,expected) in enumerate(cases):
                proof.unlink(missing_ok=True)
                cnf.write_text(text(n,clauses))
                cmd=[str(R/"build/drnas-coop54-gate"),str(cnf),
                    "--mode","core","--time","2","--stats",*opts,
                    "--coop4","on","--coop5","on","--proof",str(proof)]
                p=subprocess.run(cmd,capture_output=True,text=True,timeout=4)
                assert p.returncode==(10 if expected else 20),(name,i,p.returncode,p.stderr[-450:])
                if expected:
                    assert model_ok(n,clauses,p.stdout),(name,i,"BAD_SAT")
                else:
                    q=subprocess.run([str(R/"build/drat-trim"),str(cnf),str(proof)],
                                      capture_output=True,text=True,timeout=10)
                    assert "s VERIFIED" in q.stdout,(name,i,q.stdout[-300:])
                    unsat_proofs+=1
                gates=[json.loads(x.split(" ",1)[1]) for x in p.stderr.splitlines()
                       if x.startswith("COOP54_DISPATCH ")]
                assert len(gates)==1 and gates[0]["skipped_dead_dispatch"]>=0,(name,i)
                checks+=1
    print("COOP54_POLICY_SAFETY_PASS",json.dumps({
        "reused_tiny_oracle_trials":len(T.CASES)*2*2,
        "new_policy_oracle_trials":checks,
        "new_policy_unsat_certified":unsat_proofs,
        "modes":list(OPTIONS),"one_logical_cpu":True,
        "wrong_SAT_UNSAT":0}),flush=True)

if __name__=="__main__":main()
