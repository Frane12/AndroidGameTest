#!/usr/bin/env python3
"""Constructed DELTAX SAT test with exact tiny oracles and actual CDCL reasons.

Every case runs JOIN (control), DELTAX shadow, DELTAX live on one logical
CPU with the same compiled instrumented binary. SAT models are checked
against the ORIGINAL CNF, every UNSAT has independently checked original
DRAT, and every logged alias has original-source parents + RUP validation.
Only a genuine CDCL enqueue with a DELTAX-origin reason counts as causal use.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"research/drnas_deltax"))
sys.path.insert(0,str(R/"research"))
sys.path.insert(0,str(R/"tests"))
from synthetic_formulas import write,BASE
from test_drnas_coop52 import oracle,model_ok
from test_drnas_deltacoop2 import check_rup,bcp
from test_drnas_deltax import validate_alias,canon

BINARY=R/"build/drnas-deltax-causal"
CHECK=R/"build/drat-trim"
MODES=("join","deltax-shadow","deltax")

def run_case(case,mode,cap,folder):
    src=R/case["path"]
    clauses=[]
    for line in src.read_text().splitlines():
        if line.startswith("p ") or not line.strip():continue
        clauses.append([int(x) for x in line.split() if x!="0"])
    expected=oracle(case["n"],clauses)
    with tempfile.TemporaryDirectory() as td:
        proof=Path(td)/"proof.drat"
        cmd=[str(BINARY),str(src),"--mode","core","--time",str(cap),
             "--x5-no-minimize","--stats","--coop4","gate",
             "--coop4-eager","--coop5","off",
             "--delta2",mode,"--proof",str(proof)]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+3.0)
        assert p.returncode==(10 if expected else 20),(
            "ORACLE_MISMATCH",case["name"],mode,p.returncode,p.stderr[-700:])
        if p.returncode==10:
            assert model_ok(case["n"],clauses,p.stdout),(
                "INVALID_ORIGINAL_MODEL",case["name"],mode)
        if p.returncode==20:
            ch=subprocess.run([str(CHECK),str(src),str(proof)],
                capture_output=True,text=True,timeout=20)
            assert ch.returncode>=0 and "s VERIFIED" in ch.stdout,(
                "INVALID_ORIGINAL_UNSAT_PROOF",case["name"],mode,
                ch.stdout[-400:],ch.stderr[-400:])
        assert proof.exists()
        additions=check_rup(clauses,proof)
        alias=[]
        causal=[]
        for line in p.stderr.splitlines():
            if line.startswith("DELTAX_ALIAS "):
                e=json.loads(line.split(" ",1)[1])
                validate_alias(e,{canon(c) for c in clauses})
                assert e["installed"]==(mode=="deltax")
                alias.append(e)
            elif line.startswith("DELTAX_CAUSAL_PROPAGATION "):
                e=json.loads(line.split(" ",1)[1])
                causal.append(e)
        report=[json.loads(line.split(" ",1)[1]) for line in p.stderr.splitlines()
                if line.startswith("DELTAX_STATS ")]
        causal_reports=[json.loads(line.split(" ",1)[1]) for line in p.stderr.splitlines()
                if line.startswith("DELTAX_CAUSAL_STATS ")]
        assert len(report)==len(causal_reports)==1,("MISSING_TELEMETRY",case["name"])
        st=report[0];ct=causal_reports[0]
        assert st["mode"]==mode
        if mode!="deltax":
            assert st["proof_carrying_injected"]==0
            assert ct["real_enqueues_with_deltax_reason"]==0 and not causal
        else:
            assert len(alias)<=st["proof_carrying_injected"]
            assert ct["real_enqueues_with_deltax_reason"]>=len(causal)
            derived={canon(x["forward"]) for x in alias}
            for ev in causal:
                assert canon(ev["reason_clause"]) in derived,(
                    "PROPAGATION_REASON_NOT_DELTAX",ev,case["name"])
                assert ev["literal"] in ev["reason_clause"],(
                    "PROPAGATION_LITERAL_NOT_IN_REASON",ev)
        result={
            "case":case["name"],"category":case["group"],"mode":mode,
            "sha256":case["sha256"],"nvars":case["n"],"clauses":len(clauses),
            "status":"SAT_VERIFIED" if p.returncode==10 else "UNSAT_CERTIFIED",
            "original_proof_rup_additions":additions,
            "nonlinear_witnesses":st["witnesses"],
            "alias_proof_candidates":len(alias),
            "injected":st["proof_carrying_injected"],
            "cdcl_causal_enqueues":ct["real_enqueues_with_deltax_reason"],
            "cdcl_causal_logged":len(causal),
            "cdcl_reason_analysis_uses":st["cdcl_reason_uses"],
            "guard_activations":st["guard_activations"],
            "guard_deactivations":st["guard_deactivations"],
            "max_alias_reduction":st["max_alias_variables_removed"],
        }
        (folder/(case["name"]+"-"+mode+".json")).write_text(
            json.dumps({"trial":result,"alias":alias,"causal":causal},
                       indent=2,sort_keys=True)+"\n")
        print("DELTAX_SYNTH_TRIAL",json.dumps(result,sort_keys=True),flush=True)
        return result

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cases=write("deltax_synthetic_inputs")
    root=R/"deltax_synthetic_result"
    root.mkdir(parents=True,exist_ok=True)
    trials=[]
    for case in cases:
        for mode in MODES:
            trials.append(run_case(case,mode,2.0,root))
    assert len(trials)==len(cases)*len(MODES)
    bymode={mode:[t for t in trials if t["mode"]==mode] for mode in MODES}
    positive=[t for t in bymode["deltax"] if t["category"]=="positive"]
    negative=[t for t in bymode["deltax"] if t["category"]=="negative"]
    certs=sum(t["alias_proof_candidates"] for t in positive)
    injected=sum(t["injected"] for t in positive)
    causal=sum(t["cdcl_causal_enqueues"] for t in positive)
    control_causal=sum(t["cdcl_causal_enqueues"] for mode in ("join","deltax-shadow")
                       for t in bymode[mode])
    assert control_causal==0
    # A missing causal event is a useful negative scientific finding, not a
    # fake PASS. We don't force a solver to use a redundant learned reason.
    report={
        "status":"COMPLETE",
        "same_executable_three_modes":True,
        "sources":len(cases),"trials":len(trials),
        "positive_sources":len(positive),"negative_controls":len(negative),
        "certified_alias_events":certs,"proof_carrying_injections":injected,
        "actual_cdcl_propagations_using_deltax_clause":causal,
        "negative_controls_with_alias_events":
            sum(t["alias_proof_candidates"]>0 for t in negative),
        "control_causal_enqueues":control_causal,
        "causal_milestone_reached":causal>0,
        "all_original_sat_models_and_unsat_proofs_checked":True,
        "all_logged_resolvents_original_rup_checked":True,
        "no_speed_claim":True,"no_promotion":True}
    (root/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    (root/"trials.json").write_text(json.dumps(trials,indent=2,sort_keys=True)+"\n")
    print("DELTAX_SYNTH_FINISHED",json.dumps(report,sort_keys=True),flush=True)
    # Avoid accepting an experiment that never tested a genuine alias.
    assert certs>0 and injected>0,("NO_CAUSAL_CANDIDATE_TESTED",report)

if __name__=="__main__":main()
