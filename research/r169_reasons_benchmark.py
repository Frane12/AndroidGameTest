#!/usr/bin/env python3
"""R169: CAUSAL source-certified GF2/CDCL *used* reason, not mere proposals.

Precommitted modes on the same 8 original, SHA-frozen, PREVIOUSLY SEEN R155 CNFs:
 clean                 CDCL only
 direct_full           source certified XOR units, no Gaussian two-way
 direct_two_way        frozen R168 cadence; emits source and residual GF2 units
 direct_two_way_early  512 assignment cadence; emits source and residual
 direct_two_way_newonly 512 cadence; Gaussian units MUST require 2+ source rows
                       and not be present as a unit in any source row
 direct_two_way_shadow identical novel-only detection but NEVER emit derived unit

Source-only propagation is still enabled in shadow, so comparison isolates
*derived residual unit publication*, NOT the full GF2 subsystem. R168 result
telemetry was extended on a separate R169 branch with frozen algorithm source.
All original CNF bytes SHA checked, original SAT witnesses independently checked,
and source XOR equation certificates independently replayed.

No blind holdout, no independent UNSAT LRAT/FRAT, no world-ranking assertion.
"""
import argparse,collections,hashlib,json,os,pathlib,random,statistics,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r165_component_benchmark as base

ROOT=pathlib.Path("r169")
base.ROOT=ROOT
base.FROZEN=ROOT/"frozen"
MODES=("clean","direct_full","direct_two_way","direct_two_way_early",
       "direct_two_way_newonly","direct_two_way_shadow")
GF2_MODES=set(MODES)-{"clean","direct_full"}
REPS=2
SHARDS=4
PROTO="DRNAS-R169-CAUSAL-GAUSSIAN-UNIT-REASON-ABLAT-20261106-v1"
COUT=("two_way_sweeps","two_way_row_xors","two_way_proposals","two_way_candidates",
      "two_way_multi_source_candidates","two_way_source_duplicate_units",
      "two_way_shadow_candidates","two_way_used_reasons",
      "two_way_abstentions","two_way_ns","direct_proposals",
      "reason_clauses_completed","propagate_ns","assignment_notify_ns",
      "backtrack_notify_ns")
def need(ok,reason):
    if not ok:raise RuntimeError("R169_FAIL_CLOSED "+str(reason))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def trial(c,mode,rep,prep,binary):
    src=base.FROZEN/(c["id"]+".cnf")
    need(sha(src)==c["sha256"],"original SHA drift")
    if mode in ("clean","direct_full"):
        raw=base.trial(c,mode,rep,prep,binary)
        raw.update({k:0 for k in COUT if k not in raw})
        raw["r169_protocol"]=PROTO
        return raw
    tsv=ROOT/("full-"+c["id"]+".tsv")
    need(sha(tsv)==prep["full_tsv_sha"],"GF2 source certificate TSV drift")
    cap=30.0 if c["cohort"]=="mixed_residual" else 5.0
    charge=prep["preprocessing_s"]
    need(1.0<=cap-charge,"GF2 preprocessor cap exceeded")
    start=time.perf_counter()
    try:
        p=subprocess.run([str(binary.resolve()),mode,str(src.resolve()),
                          str(tsv.resolve()),str(cap-charge)],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=cap+12)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("R169 external/native safety cap violation "+c["id"]) from e
    elapsed=time.perf_counter()-start+charge
    need(p.returncode in (0,10,20),
         "native binary exit "+str(p.returncode)+" "+p.stderr[-750:].decode(errors="replace"))
    txt,native,stats,source,derived=base.parse_native(p.stdout,mode)
    need(source==prep["full_rows"],"source certified row mismatch")
    status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[native["status"]]
    need(p.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],
         "incorrect exit vs SAT status")
    need(abs(float(native["solver_s"])-(elapsed-charge))<0.5,
         "wall elapsed and native elapsed diverge")
    if status=="SAT":
        need(native["source_sat_witness_checked"]=="1",
             "original SAT witness not self-checked")
        base.sat_check(src,txt)
    metrics={k:int(native[k]) for k in COUT}
    need(metrics["two_way_used_reasons"]<=metrics["two_way_proposals"],
         "derived actual-used reasons exceed proposed")
    need(metrics["two_way_multi_source_candidates"]<=metrics["two_way_candidates"],
         "multi-source candidates exceed total candidates")
    need(metrics["two_way_shadow_candidates"]<=metrics["two_way_candidates"],
         "shadow candidate accounting exceeds candidates")
    need(metrics["reason_clauses_completed"]>=metrics["two_way_used_reasons"],
         "used reasons not counted in external native CDCL reason callbacks")
    if mode=="direct_two_way_shadow":
        need(metrics["two_way_proposals"]==metrics["two_way_used_reasons"]==0,
             "shadow MUST NOT propagate any derived Gaussian unit")
    else:
        need(metrics["two_way_shadow_candidates"]==0,
             "active Gaussian unexpectedly suppressed")
    if c["cohort"]=="mixed_residual":
        need(stats.get("conflicts") is not None and stats.get("decisions") is not None,
             "missing genuine CaDiCaL conflict/decision metrics")
    return dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],family=c["family"],
       mode=mode,repeat=rep,status=status,
       elapsed=round(elapsed,6),cap=cap,
       par2=round(2*cap if status=="TIMEOUT" else min(cap,elapsed),6),
       charged_preprocess_s=charge,source_rows=source,derived_rows=derived,
       native_stats=stats,proof="SOURCE_SAT_INDEPENDENT_CHECK" if status=="SAT"
             else "UNSAT_NOT_INDEPENDENT_LRAT" if status=="UNSAT" else "TIMEOUT",
       r169_protocol=PROTO,**metrics)
def shard(index,binary):
    need(0<=index<SHARDS,"invalid shard")
    need(binary.is_file(),"missing frozen native R169 binary")
    pin=json.loads((ROOT/"build-pin.json").read_text())
    need(pin["binary_sha256"]==sha(binary),"R169 binary hash mismatch")
    need(pin["source_commit"]==os.environ.get("GITHUB_SHA",pin["source_commit"]),
         "runner and source build commit mismatch")
    if hasattr(os,"sched_getaffinity"):
        allowed=os.sched_getaffinity(0)
        if allowed:os.sched_setaffinity(0,{min(allowed)})
    cases=base.sources()
    need(len(cases)==8,"expected 8 original old development CNFs")
    rows=[]
    for i,c in enumerate(cases):
        if i%SHARDS!=index:continue
        prep=base.prepare(c)
        for rep in range(REPS):
            order=list(MODES)
            random.Random("R169-PAIRED-"+c["sha256"]+"-"+str(rep)).shuffle(order)
            for mode in order:
                result=trial(c,mode,rep,prep,binary)
                rows.append(result)
                save(ROOT/("shard-%d.json"%index),rows)
                print("R169_TRIAL",json.dumps({
                    "id":c["id"],"cohort":c["cohort"],"mode":mode,
                    "repeat":rep,"status":result["status"],"par2":result["par2"],
                    "two_way_proposals":result["two_way_proposals"],
                    "used_reasons":result["two_way_used_reasons"],
                    "multi_source_candidates":result["two_way_multi_source_candidates"],
                    "shadow_candidates":result["two_way_shadow_candidates"]},
                    sort_keys=True),flush=True)
    need(len(rows)==2*REPS*len(MODES),"incomplete shard trials")
    print("R169_SHARD_PASS",index,len(rows),flush=True)
def audit():
    cases=base.sources()
    rows=[];source_proofs={}
    for i in range(SHARDS):
        p=ROOT/("shard-%d.json"%i)
        need(p.is_file(),"missing shard "+str(i))
        data=json.loads(p.read_text())
        need(len(data)==2*REPS*len(MODES),"incomplete shard "+str(i))
        rows+=data
    need(len(rows)==8*REPS*len(MODES),"R169 expected 96 attempts")
    keys={(r["sha256"],r["repeat"],r["mode"]) for r in rows}
    need(len(keys)==len(rows),"duplicate attempts")
    for c in cases:
        subset=[r for r in rows if r["sha256"]==c["sha256"]]
        need(len(subset)==REPS*len(MODES),"missing formula arms")
        expected={r["status"] for r in subset if r["status"]!="TIMEOUT"}
        need(len(expected)<=1,"contradictory native SAT/UNSAT")
        proof=json.loads((ROOT/("cert-"+c["id"]+".json")).read_text())
        base.independent_cert(c,proof)
        prep=json.loads((ROOT/("prep-"+c["id"]+".json")).read_text())
        need(prep["source_sha256"]==c["sha256"]==
             sha(base.FROZEN/(c["id"]+".cnf")),"source SHA drift")
        source_proofs[c["id"]]=dict(source_sha256=c["sha256"],
            source_cert_sha256=sha(ROOT/("cert-"+c["id"]+".json")),
            charged_preprocessing_s=prep["preprocessing_s"])
        for r in subset:
            need(r["r169_protocol"]==PROTO,"wrong source benchmark policy")
            need(r["cohort"]==c["cohort"],"wrong cohort")
            need(abs(r["par2"]-(2*r["cap"] if r["status"]=="TIMEOUT"
                else min(r["cap"],r["elapsed"])))<1e-4,
                "incorrect censored PAR2")
            if r["status"]=="SAT":
                need(r["proof"]=="SOURCE_SAT_INDEPENDENT_CHECK",
                     "SAT source witness unverified")
            need(r["two_way_used_reasons"]<=r["two_way_proposals"],
                 "more consumed than emitted GF2 reasons")
    summary={}
    cohorts=["all"]+sorted({x["cohort"] for x in rows})
    for coh in cohorts:
        vals=[x for x in rows if coh=="all" or x["cohort"]==coh]
        summary[coh]={}
        for mode in MODES:
            a=[x for x in vals if x["mode"]==mode]
            summary[coh][mode]=dict(trials=len(a),
                solved=sum(x["status"]!="TIMEOUT" for x in a),
                SAT=sum(x["status"]=="SAT" for x in a),
                UNSAT=sum(x["status"]=="UNSAT" for x in a),
                PAR2_s=round(sum(x["par2"] for x in a),6),
                actual_wall_s=round(sum(x["elapsed"] for x in a),6),
                derived_candidates=sum(x["two_way_candidates"] for x in a),
                novel_2plus_row_candidates=sum(x["two_way_multi_source_candidates"] for x in a),
                derived_emitted=sum(x["two_way_proposals"] for x in a),
                actually_consumed_reasons=sum(x["two_way_used_reasons"] for x in a),
                shadow_novel_candidates=sum(x["two_way_shadow_candidates"] for x in a),
                source_duplicate_units_rejected=sum(x["two_way_source_duplicate_units"] for x in a),
                cdcl_conflicts=sum((x["native_stats"].get("conflicts") or 0) for x in a),
                cdcl_decisions=sum((x["native_stats"].get("decisions") or 0) for x in a),
                GF2_processing_ns=sum(x["two_way_ns"] for x in a),
                full_external_reason_callbacks=sum(x["reason_clauses_completed"] for x in a))
    saved=dict(protocol=PROTO,status="RESEARCH_AUDIT_PASS_NOT_BLIND",
        original_formulas=8,attempts=len(rows),source_immutable=True,
        source_certificate_replayed=True,all_SAT_models_rechecked=True,
        independent_UNSAT_LRAT_available=False,
        exact_native_binary_source_sha_pinned=True,
        modes=MODES,
        R169_early_gap_notifications=512,
        R168_original_gap_notifications=8192,
        causal_design="clean vs source-only vs original two-way vs early vs novel-only vs derived-shadow",
        shadow_keeps_source_unit_propagations=True,
        attribution="multi-source Gaussian units emitted versus CDCL callback reason actually consumed",
        precommitted_previous_dev_cases_not_blind=True,
        source_proofs=source_proofs,
        results=summary,records=rows,
        caveats=["The 8 original CNFs were previously evaluated by R155/R168.",
                "Shadow suppresses only derived two-way GF2 publications, not source row units.",
                "No independent LRAT for CDCL UNSAT, only cross-solver consistency.",
                "Unsolved formulas have PAR2 censored penalty; no exact speedup ratio.",
                "Same-source same-shard shuffled paired CPU affinity; CPUs can vary by shard.",
                "Less CDCL conflicts cannot substitute for end-to-end wall-time or additional solves."])
    save(ROOT/"report.json",saved)
    with (ROOT/"summary.md").open("w") as out:
        out.write("# DRNAS R169 — causal GF2/CDCL novel-unit and USED-reason audit\n\n")
        out.write("**Research development replay, NOT blind. 8 original R155 CNFs; 96 trials.**\n\n")
        out.write("| Mode | Solved | PAR-2 s | Novel 2+row candidates | Emitted GF2 units | Consumed CDCL reasons | Shadow candidates |\n")
        out.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for mode in MODES:
            d=summary["all"][mode]
            out.write(f'| {mode} | {d["solved"]}/{d["trials"]} | {d["PAR2_s"]:.3f} | {d["novel_2plus_row_candidates"]} | {d["derived_emitted"]} | {d["actually_consumed_reasons"]} | {d["shadow_novel_candidates"]} |\n')
        out.write("\nNo solver breakthrough claim without independent new SHA holdout and SAT/UNSAT proof controls.\n")
    print("R169_FINAL",json.dumps({"status":saved["status"],
        "formulas":8,"attempts":96,"summary":summary["all"]},
        sort_keys=True),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    parser.add_argument("--binary",default="r169/r169-native")
    a=parser.parse_args()
    shard(a.shard,pathlib.Path(a.binary)) if a.action=="shard" else audit()
