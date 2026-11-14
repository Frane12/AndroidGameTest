#!/usr/bin/env python3
"""ΔCOOP1 preflight: exact tiny oracles + original-CNF SAT/UNSAT certificates."""
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tests"))
from test_drnas_coop52 import CASES, oracle, text, model_ok

MODES=("off","observe","gate")
BINARY=ROOT/"build/drnas-deltacoop1"
DRAT=ROOT/"build/drat-trim"

def xor_cnf(variables,rhs):
    out=[]
    for values in itertools.product((0,1),repeat=len(variables)):
        if sum(values)%2==rhs:
            continue
        out.append([-v if bit else v for v,bit in zip(variables,values)])
    return out

# Two overlapping affine constraints logically fix z, but plain root BCP
# cannot discover it without a decision. This is the ΔCOOP1 activation case.
core=xor_cnf([1,2,3],0)+xor_cnf([1,2],0)
EXTRA=[
    (3,core),
    (3,core+[[3]]),
    (4,core+[[3,4]]),
    (3,xor_cnf([1,2,3],1)+xor_cnf([1,2],0)),
    (3,xor_cnf([1,2,3],1)+xor_cnf([1,2],0)+[[-3]]),
]
# Keep the preflight short; cover exhaustive three-variable functions,
# random CNFs, and explicit algebra/BCP integration counterexamples.
SUITE=CASES[:38]+EXTRA

def execute(cnf,proof,clauses,n,expected,mode):
    proof.unlink(missing_ok=True)
    cmd=[str(BINARY),str(cnf),"--mode","core","--time","1.5",
         "--stats","--x5-no-minimize","--coop4",mode,"--coop5","off",
         "--coop4-eager","--proof",str(proof)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=3.0)
    if p.returncode!=(10 if expected else 20):
        raise AssertionError(("SAT_ORACLE_MISMATCH",mode,p.returncode,p.stderr[-750:]))
    if p.returncode==10:
        assert model_ok(n,clauses,p.stdout),("INVALID_ORIGINAL_MODEL",mode)
    else:
        q=subprocess.run([str(DRAT),str(cnf),str(proof)],
                         capture_output=True,text=True,timeout=15)
        assert "s VERIFIED" in q.stdout,("INVALID_ORIGINAL_UNSAT_PROOF",mode,q.stdout[-800:],q.stderr[-800:])
    marks=[json.loads(line.split(" ",1)[1]) for line in p.stderr.splitlines()
           if line.startswith("DELTA_COOP1 ")]
    assert len(marks)==1,("MISSING_DELTA_TELEMETRY",mode,p.stderr[-800:])
    stats=marks[0]
    assert stats["mode"]==mode,(mode,stats)
    if mode!="gate":
        assert stats["certified_lemmas"]==0
        assert stats["direct_forces"]==0
        assert stats["same_level_new_assignments"]==0
        assert stats["live_bridge_conflicts"]==0
    assert stats["same_level_new_assignments"]>=stats["cascade_forces"]
    assert stats["candidate_unit_events"]>=0
    return p.returncode,stats

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    counts={m:{"cases":0,"sat":0,"proof_checked_unsat":0,
               "candidate_unit_events":0,"certified_lemmas":0,
               "direct_forces":0,"cascade_forces":0} for m in MODES}
    with tempfile.TemporaryDirectory() as tmp:
        temp=Path(tmp)
        src=temp/"original.cnf"
        proof=temp/"original.drat"
        for n,clauses in SUITE:
            src.write_text(text(n,clauses))
            expected=oracle(n,clauses)
            for mode in MODES:
                rc,stats=execute(src,proof,clauses,n,expected,mode)
                acc=counts[mode]
                acc["cases"]+=1
                acc["sat"]+=int(rc==10)
                acc["proof_checked_unsat"]+=int(rc==20)
                for key in ("candidate_unit_events","certified_lemmas",
                            "direct_forces","cascade_forces"):
                    acc[key]+=stats[key]
    # Explicitly guard that the new experiment is not only a telemetry no-op.
    assert counts["observe"]["candidate_unit_events"]>0,counts
    assert counts["gate"]["direct_forces"]>0,counts
    print("DELTA_COOP1_PREFLIGHT_PASS",json.dumps({
        "same_binary_three_modes":True,"source_oracle_cases":len(SUITE),
        "all_original_sat_and_unsat_certified":True,
        "one_logical_cpu":True,"arms":counts},sort_keys=True),flush=True)

if __name__=="__main__":
    main()
