#!/usr/bin/env python3
"""DRNAS T3: negative-control audit of a certified-GF(2)-unit activation gate.

This is an OFFLINE COUNTERFACTUAL over the already completed TD 440-trial run.
It does not invoke a solver or claim an experimentally measured speedup.
Source CNFs and all 11 measured arm results remain frozen/unmodified.
The gate depends on proof metadata only, NOT SAT/UNSAT labels or solver timings.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import math
import pathlib

SOURCE_RUN = 42356438634
SOURCE_MANIFEST = "2e6169009e985555e43e81d9b534f3bb307cef93963329694ef42459bef3c2e2"
PROTO = "DRNAS-T3-GF2-CERTIFIED-UNIT-IMPACT-COUNTERFACTUAL-v1"
EXPECTED_MODES = {
    "r153", "t_clean", "t_shadow", "t_source", "t_adaptive",
    "t_derived", "t2_derived_rows", "t2_derived_units",
    "t2_derived_incremental", "t2_derived_shadow", "td_lazy_source",
}

def need(condition, message):
    if not condition:
        raise RuntimeError("T3_AUDIT_FAIL_CLOSED " + str(message))

def source_hash_ok(value):
    return isinstance(value, str) and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )

def gate_active(unit_row):
    """Necessary potential root impact, not proof CDCL actually consumed it."""
    gate = unit_row.get("t_gate") or {}
    return bool(gate.get("eligible")) and int(gate.get("derived_units") or 0) > 0

def project(clean, units):
    """Estimated result if certified unit exists, else Clean plus probe charge.

    The selected Unit arm is an actual paired observation. The abstention branch
    is estimated, NOT measured; no benefit may be inferred from this estimate.
    """
    need(clean["sha256"] == units["sha256"] and
         clean["rep"] == units["rep"], "unpaired modes")
    cap = float(clean["cap_s"])
    need(float(units["cap_s"]) == cap, "unequal cap")
    gate = units.get("t_gate") or {}
    prep = float(gate.get("prep_s") or 0.0)
    need(0 <= prep <= cap, "invalid preparation charge")
    if gate_active(units):
        return (units["status"], float(units["par2_s"]), True, prep)
    if clean["status"] == "TIMEOUT":
        return ("TIMEOUT", 2*cap, False, prep)
    estimate = float(clean["elapsed_s"]) + prep
    if estimate >= cap:
        return ("TIMEOUT", 2*cap, False, prep)
    return (clean["status"], estimate, False, prep)

def selftest():
    common = dict(sha256="a"*64, rep=0, cap_s=20.0)
    c = dict(common, status="SAT", par2_s=1.0, elapsed_s=1.0)
    u = dict(common, status="TIMEOUT", par2_s=40.0, elapsed_s=20.0,
             t_gate=dict(eligible=True, derived_units=1, prep_s=.2))
    need(project(c,u)[:3] == ("TIMEOUT",40.0,True),"active uses measured paired arm")
    u["t_gate"]["derived_units"] = 0
    status,par2,active,_ = project(c,u)
    need(status=="SAT" and not active and abs(par2-1.2)<1e-9,
         "abstention must pay certification")
    u["t_gate"]["prep_s"] = 19.5
    need(project(c,u)[:3] == ("TIMEOUT",40.0,False),
         "over-cap abstention censored")
    u["t_gate"]["prep_s"]=.2
    u["t_gate"]["eligible"]=False
    u["t_gate"]["derived_units"]=3
    need(not gate_active(u),"ineligible source never injected")
    print("T3_OFFLINE_GATE_SELFTEST_PASS",flush=True)

def audit(input_dir,output_dir):
    input_dir=pathlib.Path(input_dir)
    output_dir=pathlib.Path(output_dir)
    report=json.loads((input_dir/"report.json").read_text())
    need(report["status"] == "ULTIMATE_TD_LAZY_SOURCE_AUDIT_PASS_NONBLIND",
         "not the pinned TD final")
    need(report["original_manifest_sha"] == SOURCE_MANIFEST,
         "original R2 source manifest changed")
    need(report["attempts"] == 440 and report["source_count"] == 20,
         "wrong source benchmark shape")
    need(report["original_cnfs_unchanged"] and
         report["source_XOR_independently_replayed"] and
         report["models_checked_original"],"missing source correctness audit")
    need(not report["blind_holdout"] and
         not report["independent_native_LRAT"],"unexpected audit contract")
    rows=json.loads((input_dir/"all-trials.json").read_text())
    need(len(rows)==440,"trials missing")
    observed={}
    for row in rows:
        s=row["sha256"]
        need(source_hash_ok(s) and row["mode"] in EXPECTED_MODES,"invalid SHA/mode")
        cap=20.0 if row["cohort"]=="development" else 30.0
        need(row["cohort"] in ("development","new_to_r1"),"unknown cohort")
        need(float(row["cap_s"]) == cap,"cap policy changed")
        need(row["rep"] in (0,1) and row["status"] in
             ("SAT","UNSAT","TIMEOUT"),"invalid rep/answer")
        expected=2*cap if row["status"]=="TIMEOUT" else float(row["elapsed_s"])
        need(math.isclose(float(row["par2_s"]),expected,abs_tol=2e-5),
             "trial PAR2 inconsistent")
        if row["status"]=="SAT":
            need(row["proof"]=="SAT_WITNESS_CHECKED_ORIGINAL_SHA",
                 "original CNF SAT witness not audited")
        gate=row.get("t_gate") or {}
        if gate:
            need(gate["source_sha256"]==s,"GF2 gate SHA mismatch")
        key=(s,row["rep"])
        observed.setdefault(key,{})
        need(row["mode"] not in observed[key],"duplicate arm")
        observed[key][row["mode"]]=row
    need(len(observed)==40 and all(set(v)==EXPECTED_MODES for v in
         observed.values()),"incomplete 40 source-repetition pairs")
    need(len({k[0] for k in observed})==20,"not 20 immutable original sources")
    # Compare raw trials against the original independent FINAL audit.
    for mode in EXPECTED_MODES:
        raw=[r for r in rows if r["mode"]==mode]
        reference=report["results"]["all"][mode]
        need(len(raw)==reference["n"] and
             sum(r["status"]!="TIMEOUT" for r in raw)==reference["solved"],
             "source FINAL solved count mismatch "+mode)
        need(math.isclose(sum(r["par2_s"] for r in raw),
                          reference["par2_s"],abs_tol=.0005),
             "source FINAL PAR2 mismatch "+mode)
    per=collections.defaultdict(lambda:collections.defaultdict(float))
    detail=[]
    for (_,rep),arms in sorted(observed.items()):
        clean=arms["t_clean"]
        units=arms["t2_derived_units"]
        cohort=clean["cohort"]
        status,est,active,prep=project(clean,units)
        z=per["all"]
        q=per[cohort]
        for agg in (z,q):
            agg["n"]+=1
            agg["eligible_unit_candidates"]+=int(active)
            agg["clean_solved"]+=int(clean["status"]!="TIMEOUT")
            agg["unit_solved"]+=int(units["status"]!="TIMEOUT")
            agg["estimated_solved"]+=int(status!="TIMEOUT")
            agg["clean_par2_s"]+=clean["par2_s"]
            agg["unit_par2_s"]+=units["par2_s"]
            agg["estimated_par2_s"]+=est
            agg["gate_prep_s"]+=prep
        if active:
            detail.append({
                "source_sha256":clean["sha256"],
                "id":clean["id"],"cohort":cohort,"rep":rep,
                "derived_units":units["t_gate"]["derived_units"],
                "certification_s":prep,
                "clean_status":clean["status"],"unit_status":units["status"],
                "clean_par2_s":clean["par2_s"],
                "unit_par2_s":units["par2_s"],
                "native_started":units.get("native_started"),
                "native_terminal_observed":units.get("native_mode") is not None,
            })
    summary={}
    for cohort,metrics in per.items():
        d=dict(metrics)
        d["estimated_regression_vs_clean_s"]=round(
            d["estimated_par2_s"]-d["clean_par2_s"],6)
        for k in list(d):
            if k.endswith("_s"):
                d[k]=round(d[k],6)
            else:
                d[k]=int(d[k])
        summary[cohort]=d
    need(summary["all"]["n"]==40 and
         summary["new_to_r1"]["n"]==24 and
         summary["development"]["n"]==16,"scope mismatch")
    output_dir.mkdir(parents=True,exist_ok=True)
    result={
      "protocol":PROTO,"source_run_id":SOURCE_RUN,
      "source_manifest_sha256":SOURCE_MANIFEST,
      "source_final_sha256":hashlib.sha256(
          (input_dir/"all-trials.json").read_bytes()).hexdigest(),
      "status":"T3_GATE_COUNTERFACTUAL_AUDIT_PASS_NOT_MEASURED",
      "simulation_only":True,"not_blind":True,"new_solver_runs":0,
      "independent_native_LRAT":False,"cohorts":summary,
      "positive_evidence":detail,
      "hypothesis":"Only activate independently replayed Gaussian-derived "
                   "new units; otherwise use clean CDCL and charge proof time",
      "falsification":"No new solves, and root-certified unit selection "
                      "cannot amortize proof cost on the frozen TD corpus",
      "limitations":"Selection uses measured GF2 source metadata only; "
                    "the abstain route Clean+prep is an estimate, not a "
                    "real timed execution; timeout races cannot be inferred. "
                    "One old development source has the only unit gate. "
                    "TD terminal_missing prevents proving injected units "
                    "affected CDCL. New blind SAT/UNSAT holdout needed.",
    }
    (output_dir/"report.json").write_text(json.dumps(result,indent=2,
                                               sort_keys=True)+"\n")
    a=summary["all"]
    (output_dir/"summary.md").write_text(
       "# DRNAS T3 - selective certified unit gate, offline falsification\n\n"
       "This is a **post-hoc counterfactual**, not a benchmark run or a "
       "verified solver speedup. Uses TD 440 original SHA-paired trials.\n\n"
       f"- Certified-unit positive gates: {a['eligible_unit_candidates']}/40 "
       f"attempts; all in one development source\n"
       f"- New-to-R1 positive gates: "
       f"{summary['new_to_r1']['eligible_unit_candidates']}/24\n"
       f"- Measured Clean: {a['clean_solved']}/40, "
       f"PAR2 {a['clean_par2_s']:.6f} s\n"
       f"- Measured Derived Units: {a['unit_solved']}/40, "
       f"PAR2 {a['unit_par2_s']:.6f} s\n"
       f"- Estimated root-only gate: {a['estimated_solved']}/40, "
       f"PAR2 {a['estimated_par2_s']:.6f} s "
       f"(+{a['estimated_regression_vs_clean_s']:.6f} s versus Clean)\n\n"
       "Root-unit screening is insufficient. Future experiment must detect "
       "actual CDCL trail-critical certified reasons or source-replayed "
       "0=1 contradictions, using fresh SHA-disjoint originals, equal "
       "caps and paired Clean/Shadow/active ablations.\n")
    print("T3_GATE_COUNTERFACTUAL_AUDIT_PASS",json.dumps({
        "positive_gates":a["eligible_unit_candidates"],
        "estimated_solved":a["estimated_solved"],
        "estimated_par2_s":a["estimated_par2_s"],
        "estimated_regression_vs_clean_s":
          a["estimated_regression_vs_clean_s"],
    },sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--output",default="t3/out")
    args=parser.parse_args()
    if args.selftest:
        selftest()
    else:
        need(args.input is not None,"--input required")
        audit(args.input,args.output)
