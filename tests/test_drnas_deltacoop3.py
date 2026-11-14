#!/usr/bin/env python3
"""DELTA3 independent original-CNF checks and hardware-miter replay.

The generated short lemma is a one-step resolvent of two ORIGINAL clauses.
Never credit a model/proof from a timed-out or unchecked solver result.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"research"))
sys.path.insert(0,str(R/"tests"))
import drnas_x55_cpu_real36 as B
from test_drnas_coop52 import CASES, oracle, text, model_ok
from test_drnas_deltacoop2 import signal_cases, check_rup, bcp, check_witness

BIN=R/"build/drnas-deltacoop3"
CHECK=R/"build/drat-trim"

def canon(c):return tuple(sorted(set(c)))

def validate_lemma(row,source):
    left=canon(row["left"]);right=canon(row["right"])
    pivot=row["pivot"];actual=canon(row["clause"])
    assert left in source and right in source,("NOT_ORIGINAL_PARENTS",row)
    assert pivot in left and -pivot in right,("WRONG_RESOLUTION_PIVOT",row)
    expected=canon([x for x in left if x!=pivot]+[x for x in right if x!=-pivot])
    assert expected==actual,("WRONG_RESOLVENT",row)
    assert not any(-l in actual for l in actual),("TAUTOLOGY",row)
    assert len(actual)<=3 and actual not in source,("NONNOVEL_OR_LONG",row)
    # This is an independent UP/RUP check: assumption not(clause) forces
    # opposite unit propagations through the two original parent clauses.
    assert bcp([left,right],[-l for l in actual]) is None,("NOT_RUP",row)

def run(src,n,clauses,mode,cap,full_proof=True):
    with tempfile.TemporaryDirectory() as tmp:
        proof=Path(tmp)/"delta3.drat"
        cmd=[str(BIN),str(src),"--mode","core","--time",str(cap),
             "--stats","--x5-no-minimize","--coop4","gate","--coop5","off",
             "--delta2",mode,"--proof",str(proof)]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+2.8)
        assert p.returncode in (0,10,20,153),(mode,p.returncode,p.stderr[-900:])
        if p.returncode==10:
            assert model_ok(n,clauses,p.stdout),("INVALID_ORIGINAL_SAT_MODEL",mode)
        if p.returncode==20:
            q=subprocess.run([str(CHECK),str(src),str(proof)],
                             capture_output=True,text=True,timeout=25)
            assert q.returncode>=0 and "s VERIFIED" in q.stdout,("UNVERIFIED_UNSAT",mode,q.stdout[-500:],q.stderr[-500:])
        if full_proof:
            assert proof.exists() and check_rup(clauses,proof)>=0
        telemetry=[json.loads(l.split(" ",1)[1]) for l in p.stderr.splitlines()
                   if l.startswith("DELTA2_JOIN ")]
        assert len(telemetry)==1,("MISSING_TELEMETRY",mode,p.stderr[-700:])
        lemmas=[json.loads(l.split(" ",1)[1]) for l in p.stderr.splitlines()
                if l.startswith("DELTA3_LEMMA ")]
        source={canon(c) for c in clauses}
        for lemma in lemmas:validate_lemma(lemma,source)
        for line in p.stderr.splitlines():
            if line.startswith("DELTA2_WITNESS "):
                w=json.loads(line.split(" ",1)[1])
                check_witness(w)
                for side in ("left","right"):
                    assert all(canon(c) in source for c in w[side]["cnf"])
        st=telemetry[0]
        if mode=="bridge-shadow":
            assert st["bridge_injected"]==0 and not lemmas
        if mode=="bridge":
            assert len(lemmas)<=st["bridge_injected"]
        return p.returncode,st,len(lemmas)

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    count=0;unsat=0;emitted=0
    totals={m:{"cases":0,"bridge_injected":0,"bridge_witnesses":0}
            for m in ("join","bridge-shadow","bridge")}
    with tempfile.TemporaryDirectory() as tmp:
        src=Path(tmp)/"oracle.cnf"
        for n,cs in CASES[:16]+signal_cases()[:6]:
            expected=oracle(n,cs)
            src.write_text(text(n,cs))
            for mode in totals:
                rc,st,num=run(src,n,cs,mode,1.8)
                assert rc==(10 if expected else 20),("ORACLE_MISMATCH",mode,rc)
                totals[mode]["cases"]+=1
                totals[mode]["bridge_injected"]+=st.get("bridge_injected",0)
                totals[mode]["bridge_witnesses"]+=st.get("bridge_witnesses",0)
                emitted+=num;unsat+=int(rc==20);count+=1

        originals,meta=B.official_manifest()
        target=next(z for z in originals if z["id"]==30 and z["family"]=="hardware-miter")
        assert B.sha(Path(target["path"]).read_bytes())==target["sha256"]
        n,cs=B.parse_cnf(Path(target["path"]).read_bytes())
        source={canon(c) for c in cs}
        # Fixed, externally checkable original-source discovery control.
        known={"clause":[-1,772,777],
               "left":[-1,-3,777],
               "right":[-1,3,772],
               "pivot":-3}
        validate_lemma(known,source)
        real={}
        for mode in ("bridge-shadow","bridge"):
            rc,stats,num=run(Path(target["path"]).resolve(),n,cs,mode,4.93,False)
            real[mode]={"returncode":rc,"bridge_injected":stats["bridge_injected"],
                        "bridge_witnesses":stats["bridge_witnesses"],
                        "bridge_active_candidates":stats["bridge_active_candidates"],
                        "recorded_lemmas":num}
        report={"oracle_runs":count,"oracle_unsat_independent_proofs":unsat,
                "oracle_logged_original_rup_lemmas":emitted,
                "modes":totals,"real30_sha256":target["sha256"],
                "real30_short_clause_original_rup":True,
                "real30_one_step_source_resolution":True,
                "real30_solver":real,"one_cpu":True}
        print("DELTA3_PREFLIGHT_PASS",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":main()
