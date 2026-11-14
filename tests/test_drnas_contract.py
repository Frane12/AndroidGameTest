#!/usr/bin/env python3
"""Source-matched proof-safe CDCL ↔ COOP contract preflight.

Runs a small exact SAT oracle (including UNSAT DRAT) through both variants,
checks bridge/probe invariants, and checks real original-CNF outcomes. No
performance gains are claimed by this test.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"tests"))
sys.path.insert(0,str(R/"research"))
import test_drnas_coop52 as T
import drnas_x55_cpu_real36 as B

BIN=("drnas-coop53-audit","drnas-coop53-repair")
IDS=(0,5,8,11,16,23)

def call(binary,source,proof,cap):
    cmd=[str(R/"build"/binary),str(source),"--mode","core",
         "--time",str(cap),"--stats","--x5-no-minimize",
         "--coop4","on","--coop5","on","--proof",str(proof)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+1.5)
    if p.returncode not in (0,10,20,153):
        raise RuntimeError((binary,source,p.returncode,p.stderr[-900:]))
    contract=[json.loads(t.split(" ",1)[1]) for t in p.stderr.splitlines()
              if t.startswith("COOP53_CONTRACT ")]
    if len(contract)!=1:
        raise RuntimeError(("COOP53_MISSING_CONTRACT",binary,p.stderr[-800:]))
    c=contract[0]
    assert c["repair"]==(binary.endswith("-repair"))
    assert c["probe_rollback_checks"]>=0
    assert c["bridge_calls"]>=0
    assert c["bridge_hints_invalidated"]>=0
    assert c["known_keys_forgotten_after_cdcl_deletion"]>=0
    if not c["repair"]:
        assert c["bridge_hints_invalidated"]==0
        assert c["known_keys_forgotten_after_cdcl_deletion"]==0
    return p,c

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    T.BIN=BIN
    T.main()  # 71 tiny exact SAT/UNSAT sources x 2 modes x 2 variants
    originals,_=B.official_manifest()
    byid={row["id"]:row for row in originals}
    assert all(i in byid for i in IDS)
    totals={b:{"originals":0,"verified_SAT":0,"verified_UNSAT":0,
               "rollbacks_sampled":0,"hints_stale_observed":0,
               "hints_invalidated":0,"known_keys_forgotten":0,
               "component_lemmas_tracked":0} for b in BIN}
    with tempfile.TemporaryDirectory() as tmp:
        proof=Path(tmp)/"trial.drat"
        for ident in IDS:
            row=byid[ident]
            cnf=Path(row["path"]).resolve()
            raw=cnf.read_bytes()
            assert B.sha(raw)==row["sha256"]
            n,clauses=B.parse_cnf(raw)
            per_case={}
            for b in BIN:
                proof.unlink(missing_ok=True)
                proc,st=call(b,cnf,proof,2.0)
                if proc.returncode==10:
                    if not B.check_sat(proc.stdout,clauses,n):
                        raise RuntimeError(("WRONG_ORIGINAL_SAT_MODEL",ident,b))
                    totals[b]["verified_SAT"]+=1
                    status="SAT_VERIFIED"
                elif proc.returncode==20:
                    q=subprocess.run([str(R/"build/drat-trim"),str(cnf),str(proof)],
                                     capture_output=True,text=True,timeout=15)
                    if "s VERIFIED" not in q.stdout:
                        raise RuntimeError(("WRONG_ORIGINAL_UNSAT_PROOF",ident,b,q.stdout[-500:]))
                    totals[b]["verified_UNSAT"]+=1
                    status="UNSAT_CERTIFIED"
                else:
                    status="UNKNOWN"
                totals[b]["originals"]+=1
                for key,field in (
                    ("rollbacks_sampled","probe_rollback_checks"),
                    ("hints_stale_observed","bridge_hints_stale_observed"),
                    ("hints_invalidated","bridge_hints_invalidated"),
                    ("known_keys_forgotten","known_keys_forgotten_after_cdcl_deletion"),
                    ("component_lemmas_tracked","component_lemmas_tracked"),
                ):
                    totals[b][key]+=st[field]
                per_case[b]={"status":status,"contract":st}
            print("COOP53_CONTRACT_REAL",json.dumps(
                {"id":ident,"family":row["family"],"variants":per_case},
                sort_keys=True),flush=True)
    print("COOP53_CONTRACT_PREFLIGHT_PASS",json.dumps(
          {"strict_oracle_checks":len(T.CASES)*2*len(BIN),
           "real_originals":len(IDS),
           "one_logical_cpu":True,
           "variants":totals,
           "no_unchecked_SAT_or_UNSAT":True},sort_keys=True),flush=True)

if __name__=="__main__":
    main()
