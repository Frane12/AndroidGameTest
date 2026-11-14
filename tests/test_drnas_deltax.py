#!/usr/bin/env python3
"""DELTAX live CDCL preflight — original-CNF RUP + guarded equality semantics.

Runs unchanged source SHA-frozen SAT2024 hardware-miter ID30, alongside
small SAT/UNSAT oracles. No timings, no model promotion.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tests"))
sys.path.insert(0,str(ROOT/"research"))
from test_drnas_deltacoop2 import bcp,signal_cases,check_witness,check_rup
from test_drnas_coop52 import CASES,oracle,text,model_ok
import drnas_x55_cpu_real36 as B

BINARY=ROOT/"build/drnas-deltax"
DRAT=ROOT/"build/drat-trim"
SHA="ead2a1c2fb44d173d3a24bab1212f07adf571f4fc7563392d434e0f58386939b"

def canon(xs):return tuple(sorted(set(xs)))

def validate_alias(event,source):
    forward=canon(event["forward"])
    parent_a=canon(event["parent_a"]);parent_b=canon(event["parent_b"])
    pivot=event["pivot"];guard=event["guard"]
    a=event["a"];b=event["b"];reverse=canon(event["reverse"])
    assert a>0 and b>0 and a!=b
    assert parent_a in source and parent_b in source
    assert pivot in parent_a and -pivot in parent_b
    resolved=canon([l for l in parent_a if l!=pivot]+
                   [l for l in parent_b if l!=-pivot])
    assert forward==resolved and len(forward)==3
    assert not any(-lit in forward for lit in forward)
    assert guard in forward
    assert canon([-a,b,guard])==forward,(a,b,guard,forward)
    assert reverse==canon([a,-b]) and reverse in source
    assert forward not in source,("CLAIMED_NOVEL_BUT_ORIGINAL",forward)
    assert bcp([parent_a,parent_b],[-l for l in forward]) is None,"NOT_SOURCE_RUP"
    # Under guard false, the one-step resolvent and source binary reverse
    # together force equality for both values of the endpoints.
    for aa in (False,True):
        for bb in (False,True):
            vals={a:aa,b:bb,abs(guard):guard<0}
            def sat(c):return any(vals[abs(l)]==(l>0) for l in c)
            if sat(forward) and sat(reverse):assert aa==bb,"BAD_ALIAS"
    return forward

def trial(src,n,cs,mode,cap,verify_full=False):
    source={canon(c) for c in cs}
    with tempfile.TemporaryDirectory() as tmp:
        proof=Path(tmp)/"orig.drat"
        cmd=[str(BINARY),str(src),"--mode","core","--time",str(cap),
             "--stats","--x5-no-minimize","--coop4","gate",
             "--coop5","off","--delta2",mode,"--proof",str(proof)]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+3.0)
        assert p.returncode in (0,10,20,153),(mode,p.returncode,p.stderr[-900:])
        if p.returncode==10:
            assert model_ok(n,cs,p.stdout),("INVALID_SOURCE_SAT",mode)
        elif p.returncode==20:
            v=subprocess.run([str(DRAT),str(src),str(proof)],
                             capture_output=True,text=True,timeout=22)
            assert v.returncode>=0 and "s VERIFIED" in v.stdout,("INVALID_SOURCE_UNSAT",mode)
        if verify_full and proof.exists():
            assert check_rup(cs,proof)>=0,("RUP_FAIL",mode)
        events=[]
        for line in p.stderr.splitlines():
            if line.startswith("DELTAX_ALIAS "):
                event=json.loads(line.split(" ",1)[1])
                validate_alias(event,source)
                assert event["installed"]==(mode=="deltax")
                events.append(event)
            if line.startswith("DELTA2_WITNESS "):
                w=json.loads(line.split(" ",1)[1])
                check_witness(w)
                for key in ("left","right"):
                    assert all(canon(c) in source for c in w[key]["cnf"])
        reports=[json.loads(line.split(" ",1)[1]) for line in p.stderr.splitlines()
                 if line.startswith("DELTAX_STATS ")]
        assert len(reports)==1,("DELTAX_TELEMETRY_MISSING",mode,p.stderr[-600:])
        st=reports[0]
        assert st["mode"]==mode
        if mode=="deltax-shadow":
            assert st["proof_carrying_injected"]==0
            assert st["cdcl_reason_uses"]==0
        else:
            assert len(events)<=st["proof_carrying_injected"]
            assert st["guard_activations"]>=st["peak_active"]>=0
        return p.returncode,st,events

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cases=CASES[:10]+signal_cases()[:4]
    stats={"oracle_runs":0,"oracle_unsat_proofs":0,"source_verified_aliases":0}
    with tempfile.TemporaryDirectory() as td:
        src=Path(td)/"small.cnf"
        for n,cs in cases:
            expect=oracle(n,cs)
            src.write_text(text(n,cs))
            for mode in ("deltax-shadow","deltax"):
                result,st,events=trial(src,n,cs,mode,2.0,verify_full=True)
                assert result==(10 if expect else 20),"INCORRECT_SMALL_ORACLE"
                stats["oracle_runs"]+=1
                if result==20:stats["oracle_unsat_proofs"]+=1

    originals,meta=B.official_manifest()
    target=next(s for s in originals if s["id"]==30 and s["family"]=="hardware-miter")
    assert target["sha256"]==SHA
    n,cs=B.parse_cnf(Path(target["path"]).read_bytes())
    real={}
    for mode in ("deltax-shadow","deltax"):
        result,st,events=trial(Path(target["path"]).resolve(),n,cs,mode,4.93)
        real[mode]={
            "returncode":result,"witnesses":st["witnesses"],
            "verified_alias_events":len(events),
            "proof_carrying_injected":st["proof_carrying_injected"],
            "guard_activations":st["guard_activations"],
            "guard_deactivations":st["guard_deactivations"],
            "max_alias_variables_removed":st["max_alias_variables_removed"],
            "cdcl_reason_uses":st["cdcl_reason_uses"],
            "cdcl_conflict_uses":st["cdcl_conflict_uses"]}
        stats["source_verified_aliases"]+=len(events)
    assert real["deltax"]["verified_alias_events"]>=1,real
    assert real["deltax"]["proof_carrying_injected"]>=1,real
    assert real["deltax"]["guard_activations"]>=1,real
    assert real["deltax"]["max_alias_variables_removed"]>=1,real
    assert real["deltax-shadow"]["proof_carrying_injected"]==0,real

    report={"status":"PASS","name":"DELTAX",
            "original_real30_sha256":SHA,
            "same_source_shadow_and_live":True,
            "small_oracles":stats,
            "original_real30":real,
            "all_aliases_original_source_rup_checked":True,
            "source_preserved":True,"proof_carrying_live_clauses":True,
            "reversible_guard_observer":True,
            "literal_substitution_in_cdcl":False,
            "speed_evaluation":False,"promotion":False}
    folder=Path("deltax_certificate")
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DELTAX_PREFLIGHT_PASS",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":main()
