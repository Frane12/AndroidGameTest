#!/usr/bin/env python3
"""Verify COOP55 proof-carrying failed literal learning vs shadow.

All SAT models checked on original formula; all UNSAT results require
independent original-CNF DRAT verifier, including parity/PHP cases.
"""
import itertools,json,os,pathlib,subprocess,sys,tempfile
R=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"tests"))
from test_drnas_coop52 import CASES, oracle, text, model_ok
ARMS=("drnas-coop55-shadow","drnas-coop55-active")
def pigeonholes(p,h):
    n=p*h
    def var(i,j):return i*h+j+1
    clauses=[]
    for i in range(p):clauses.append([var(i,j) for j in range(h)])
    for j in range(h):
        for i,k in itertools.combinations(range(p),2):
            clauses.append([-var(i,j),-var(k,j)])
    return n,clauses
def validate(binary,src,clauses,n,expected,cap,proof):
    proof.unlink(missing_ok=True)
    cmd=[str(R/"build"/binary),str(src),"--mode","core",
         "--time",str(cap),"--stats","--x5-no-minimize",
         "--coop4","on","--coop5","on","--proof",str(proof)]
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=cap+2.0)
    if p.returncode not in (0,10,20,153):
        raise RuntimeError((binary,p.returncode,p.stderr[-1000:]))
    if expected is not None and p.returncode in (10,20):
        assert p.returncode==(10 if expected else 20)
    if p.returncode==10:
        assert model_ok(n,clauses,p.stdout),("BAD_ORIGINAL_SAT",binary)
    elif p.returncode==20:
        q=subprocess.run([str(R/"build/drat-trim"),str(src),str(proof)],
                         text=True,capture_output=True,timeout=20)
        assert "s VERIFIED" in q.stdout,("UNSOUND_RUP",binary,q.stdout[-600:],q.stderr[-400:])
    rows=[json.loads(x.partition(" ")[2]) for x in p.stderr.splitlines()
          if x.startswith("COOP55_RUP ")]
    assert len(rows)==1,(binary,p.stderr[-700:])
    r=rows[0]
    assert r["learn_enabled"]==(binary=="drnas-coop55-active")
    assert 0<=r["learned_nogoods"]<=32
    assert r["forced_literals"]==r["learned_nogoods"]
    if binary.endswith("-shadow"):assert r["learned_nogoods"]==0
    return {"status":p.returncode,"stats":r}
def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    totals={name:{"trials":0,"sat":0,"unsat_verified":0,"learned":0,
                  "failed_probe_conflicts":0} for name in ARMS}
    with tempfile.TemporaryDirectory() as td:
        d=pathlib.Path(td);cnf=d/"input.cnf";proof=d/"proof.drat"
        for index,(n,clauses) in enumerate(CASES):
            expected=oracle(n,clauses)
            cnf.write_text(text(n,clauses))
            for name in ARMS:
                result=validate(name,cnf,clauses,n,expected,2.0,proof)
                out=totals[name]
                out["trials"]+=1
                out["sat"]+=int(result["status"]==10)
                out["unsat_verified"]+=int(result["status"]==20)
                out["learned"]+=result["stats"]["learned_nogoods"]
                out["failed_probe_conflicts"]+=result["stats"]["failed_probe_conflicts"]
        for pigeons,holes in ((4,3),(5,4),(6,5)):
            n,clauses=pigeonholes(pigeons,holes)
            cnf.write_text(text(n,clauses))
            for name in ARMS:
                result=validate(name,cnf,clauses,n,False,2.0,proof)
                out=totals[name]
                out["trials"]+=1
                out["sat"]+=int(result["status"]==10)
                out["unsat_verified"]+=int(result["status"]==20)
                out["learned"]+=result["stats"]["learned_nogoods"]
                out["failed_probe_conflicts"]+=result["stats"]["failed_probe_conflicts"]
    print("COOP55_PROOF_SAFETY_PASS",json.dumps({
        "policy":"bounded failed literal RUP, independent DRAT proofs",
        "one_logical_cpu":True,
        "all_original_models_verified":True,
        "no_false_SAT_UNSAT":True,
        "cases_per_variant":len(CASES)+3,
        "arms":totals},sort_keys=True),flush=True)
if __name__=="__main__":main()
