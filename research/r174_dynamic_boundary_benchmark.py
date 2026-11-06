#!/usr/bin/env python3
"""R174 measured first-used-reason replay on 25 previously exposed frozen SHA cases.
Development replay only, not blind; original SHA-frozen CNFs are unchanged.
A completed GF2 reason is a real IPASIR-UP reason callback, not necessarily a
saved conflict. Compare 180s end-to-end solve, PAR2, conflicts, and decisions.
Do not claim causal speedup from conflict-count differences at a timeout.
"""
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, sys, time
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r165_component_benchmark as base

ROOT=pathlib.Path("r174")
base.ROOT=ROOT
base.FROZEN=ROOT/"frozen"
PROTO="DRNAS-R174-DYNAMIC-BOUNDARY-25-SHA-PAIRED-20261106-v1"
REPS=2
SHARDS=5
def cap_for(case):
    return 60.0 if case["cohort"]=="mixed_residual" else 15.0
MODES=("clean","direct_two_way_newonly","direct_two_way_budget","direct_two_way_dynamic")
COUNTERS=("two_way_sweeps","two_way_row_xors","two_way_proposals","two_way_candidates",
          "two_way_multi_source_candidates","two_way_source_duplicate_units",
          "two_way_shadow_candidates","two_way_used_reasons",
          "two_way_abstentions","two_way_ns","direct_proposals",
          "reason_clauses_completed","propagate_ns","assignment_notify_ns",
          "backtrack_notify_ns")
DYNAMIC=("r174_dirty_events","r174_component_skips","r174_boundary_skips",
         "r174_sweeps_total","r174_feedback_resets")
FIRST=("r170_first_proposal_ms","r170_first_used_ms",
       "r170_first_proposal_notifications","r170_first_used_notifications")
def need(condition,reason):
    if not condition:raise RuntimeError("R174_FAIL_CLOSED "+str(reason))
def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,data):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def cases():
    manifest=json.loads((base.FROZEN/"manifest.json").read_text())
    selected=sorted(manifest["cases"],key=lambda c:c["sha256"])
    need(len(selected)==25 and len({c["sha256"] for c in selected})==25,
         "expected 25 frozen original CNF sources")
    need(sum(c["cohort"]=="mixed_residual" for c in selected)==4,
         "frozen cohort drift")
    for c in selected:
        need(sha(base.FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "original SHA drift "+c["id"])
    return selected
def trial(case,mode,rep,prep,binary):
    original=base.FROZEN/(case["id"]+".cnf")
    proof=ROOT/("full-"+case["id"]+".tsv")
    need(sha(original)==case["sha256"],"original CNF SHA drift")
    need(sha(proof)==prep["full_tsv_sha"],"certified XOR TSV drift")
    cap=cap_for(case)
    charged=0.0 if mode=="clean" else prep["preprocessing_s"]
    effective=cap-charged
    need(effective>=1.0,"preprocessing over budget")
    start=time.perf_counter()
    try:
        proc=subprocess.run([str(binary.resolve()),mode,
              str(original.resolve()),str(proof.resolve()),str(effective)],
              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=cap+12.0)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("R174_UNGRACEFUL_NATIVE_TIMEOUT "+case["id"]) from exc
    elapsed=time.perf_counter()-start+charged
    need(proc.returncode in (0,10,20),
         "native exit code "+str(proc.returncode)+" "+proc.stderr[-600:].decode(errors="replace"))
    text,native,stats,source_rows,derived=base.parse_native(proc.stdout,mode)
    status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[native["status"]]
    need(proc.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],
         "native exit/status mismatch")
    expected_rows=0 if mode=="clean" else prep["full_rows"]
    need(source_rows==expected_rows,"source row count changed")
    need(abs(float(native["solver_s"])-(elapsed-charged))<0.5,
         "wall versus native solve time mismatch")
    if status=="SAT":
        need(native["source_sat_witness_checked"]=="1","native SAT model not checked")
        base.sat_check(original,text)
    m={key:int(native[key]) for key in COUNTERS+FIRST+DYNAMIC}
    need(0<=m["two_way_used_reasons"]<=m["two_way_proposals"],
         "consumed reason count invalid")
    need(m["two_way_multi_source_candidates"]<=m["two_way_candidates"],
         "multi-source candidates inconsistent")
    need(m["two_way_shadow_candidates"]<=m["two_way_candidates"],
         "shadow candidates inconsistent")
    need(m["reason_clauses_completed"]>=m["two_way_used_reasons"],
         "GF2 reason callbacks not counted")
    if mode=="direct_two_way_dynamic":
        need(m["r174_sweeps_total"]==m["two_way_sweeps"],
             "dynamic sweep count mismatch")
        need(m["r174_feedback_resets"]<=m["r174_sweeps_total"],
             "feedback resets exceed sweeps")
    for suffix,count in (("proposal","two_way_proposals"),("used","two_way_used_reasons")):
        ms=m["r170_first_"+suffix+"_ms"]
        nt=m["r170_first_"+suffix+"_notifications"]
        need((ms>=0 and nt>=0)==(m[count]>0),
             "first event marker inconsistent for "+suffix)
        if ms>=0:need(ms<=cap*1000+1000,"event timestamp outside cap")
    if m["two_way_used_reasons"]:
        need(m["r170_first_used_ms"]>=m["r170_first_proposal_ms"],
             "used GF2 reason before GF2 proposal")
    if mode=="direct_two_way_shadow":
        need(m["two_way_proposals"]==m["two_way_used_reasons"]==0,
             "shadow derived-unit leaked to CDCL")
    if mode in ("clean","direct_full"):
        need(m["two_way_proposals"]==0 and m["two_way_used_reasons"]==0,
             "control mode emitted Gaussian units")
    if mode in ("direct_two_way","direct_two_way_newonly","direct_two_way_budget","direct_two_way_dynamic"):
        need(m["two_way_shadow_candidates"]==0,"active GF2 units suppressed")
    need(stats.get("conflicts") is not None and stats.get("decisions") is not None,
         "missing genuine CaDiCaL conflict/decision counters")
    return dict(id=case["id"],sha256=case["sha256"],cohort=case["cohort"],
         mode=mode,repeat=rep,status=status,cap=cap,elapsed=round(elapsed,6),
         par2=round(2*cap if status=="TIMEOUT" else min(cap,elapsed),6),
         charged_preprocess_s=charged,source_rows=source_rows,derived_rows=derived,
         proof="ORIGINAL_SAT_MODEL_INDEPENDENT_CHECK" if status=="SAT"
               else "UNSAT_NATIVE_NOT_LRAT" if status=="UNSAT" else "TIMEOUT",
         native_stats=stats,protocol=PROTO,**m)
def shard(index,binary):
    need(0<=index<SHARDS,"invalid shard")
    need(binary.is_file(),"missing native R174 executable")
    pin=json.loads((ROOT/"build-pin.json").read_text())
    need(pin["binary_sha256"]==sha(binary),"single binary SHA drift")
    need(pin["source_commit"]==os.getenv("GITHUB_SHA",pin["source_commit"]),
         "R174 runner commit drift")
    if hasattr(os,"sched_getaffinity"):
        cores=os.sched_getaffinity(0)
        if cores:os.sched_setaffinity(0,{min(cores)})
    selected=cases()[index::SHARDS]
    rows=[]
    for case in selected:
        prep=base.prepare(case)
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+case["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                r=trial(case,mode,rep,prep,binary)
                rows.append(r)
                save(ROOT/("shard-"+str(index)+".json"),rows)
                print("R174_TRIAL",json.dumps(dict(
                    id=r["id"],cohort=r["cohort"],mode=mode,rep=rep,
                    status=r["status"],par2=r["par2"],elapsed=r["elapsed"],
                    used_reasons=r["two_way_used_reasons"],
                    first_used_ms=r["r170_first_used_ms"]),sort_keys=True),flush=True)
    need(len(rows)==len(selected)*REPS*len(MODES),"incomplete R174 shard")
    print("R174_SHARD_PASS",index,len(rows),flush=True)
def audit():
    selected=cases()
    rows=[]
    for i in range(SHARDS):
        path=ROOT/("shard-"+str(i)+".json")
        need(path.is_file(),"missing paired shard")
        piece=json.loads(path.read_text())
        need(len(piece)==len(selected[i::SHARDS])*REPS*len(MODES),"shard count mismatch")
        rows+=piece
    need(len(rows)==len(selected)*REPS*len(MODES)==200,
         "expected 200 frozen-source paired trials")
    keys={(r["sha256"],r["mode"],r["repeat"]) for r in rows}
    need(len(keys)==len(rows),"duplicate source-mode-repeat trial")
    bysha={c["sha256"]:c for c in selected}
    for case in selected:
        prep=json.loads((ROOT/("prep-"+case["id"]+".json")).read_text())
        need(prep["source_sha256"]==case["sha256"],"source SHA changed")
        need(sha(ROOT/("full-"+case["id"]+".tsv"))==prep["full_tsv_sha"],
             "certified XOR TSV changed")
        evidence=json.loads((ROOT/("cert-"+case["id"]+".json")).read_text())
        base.independent_cert(case,evidence)
    for r in rows:
        need(r["sha256"] in bysha and r["id"]==bysha[r["sha256"]]["id"],
             "paired source not in frozen manifest")
        cap=cap_for(bysha[r["sha256"]])
        need(r["protocol"]==PROTO and r["cap"]==cap,
             "paired research protocol drift")
        need(abs(r["par2"]-(2*cap if r["status"]=="TIMEOUT"
             else min(cap,r["elapsed"])))<0.00001,"PAR2 mismatch")
    pair=[]
    for case in selected:
        for rep in range(REPS):
            arm={r["mode"]:r for r in rows if r["sha256"]==case["sha256"]
                 and r["repeat"]==rep}
            need(set(arm)==set(MODES),"missing identical original SHA control")
            need(len({r["status"] for r in arm.values()
                      if r["status"]!="TIMEOUT"})<=1,"SAT/UNSAT disagreement")
            for mode in MODES[1:]:
                a,b=arm["clean"],arm[mode]
                uncensored=a["status"]!="TIMEOUT" and b["status"]!="TIMEOUT"
                pair.append(dict(source_sha256=case["sha256"],cohort=case["cohort"],
                    repeat=rep,mode=mode,baseline_status=a["status"],
                    variant_status=b["status"],delta_PAR2_s=round(a["par2"]-b["par2"],6),
                    finite_speedup=round(a["elapsed"]/b["elapsed"],6)
                       if uncensored and b["elapsed"]>0 else None,
                    gf2_reasons_consumed=b["two_way_used_reasons"]))
    summary={}
    for mode in MODES:
        group=[r for r in rows if r["mode"]==mode]
        summary[mode]=dict(trials=len(group),
          solved=sum(r["status"]!="TIMEOUT" for r in group),
          SAT=sum(r["status"]=="SAT" for r in group),
          UNSAT=sum(r["status"]=="UNSAT" for r in group),
          PAR2_s=round(sum(r["par2"] for r in group),6),
          wall_s=round(sum(r["elapsed"] for r in group),6),
          cdcl_conflicts=sum(r["native_stats"]["conflicts"] for r in group),
          two_way_sweeps=sum(r["two_way_sweeps"] for r in group),
          two_way_used_reasons=sum(r["two_way_used_reasons"] for r in group),
          GF2_processing_ns=sum(r["two_way_ns"] for r in group),
           r174_dirty_events=sum(r["r174_dirty_events"] for r in group),
           r174_component_skips=sum(r["r174_component_skips"] for r in group),
           r174_boundary_skips=sum(r["r174_boundary_skips"] for r in group),
           r174_feedback_resets=sum(r["r174_feedback_resets"] for r in group),
          solved_by_cohort={cohort:sum(r["status"]!="TIMEOUT" for r in group
                                        if r["cohort"]==cohort)
                            for cohort in sorted(set(c["cohort"] for c in selected))})
    report=dict(status="R174_RESEARCH_PAIRED_AUDIT_PASS_NOT_BLIND",
      protocol=PROTO,original_formulas=25,attempts=200,
      hypothesis="R174 dynamic changed-component selection with residual CNF links, reversible backtracking and consumed CDCL reasons",
      source_certificates_replayed=True,original_sha_verified=True,
      independent_UNSAT_LRAT_available=False,
      source_R155_frozen_run=42112755104,preexposed_development_set=True,
      one_pinned_native_binary=True,results=summary,
      paired_comparisons=pair,records=rows)
    save(ROOT/"report.json",report)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R174 — general original SHA CNF utility-budget GF2 experiment\n\n")
        f.write("**Research only, not blind.** All 25 original SHA CNFs, 2 repeats, 4 modes; 60s mixed / 15s other.\n\n")
        f.write("| Mode | Solved | PAR-2 s | Wall s | Conflicts | Gaussian sweeps | Consumed GF2 reasons |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for mode,x in summary.items():
            f.write(f'| {mode} | {x["solved"]}/50 | {x["PAR2_s"]:.3f} | {x["wall_s"]:.3f} | {x["cdcl_conflicts"]} | {x["two_way_sweeps"]} | {x["two_way_used_reasons"]} |\n')
        f.write("\nOnly both-solved pairs permit finite speedup. External UNSAT LRAT absent.\n")
    print("R174_FINAL",json.dumps(dict(status=report["status"],
      attempts=200,formulas=25,summary=summary),sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r170/r170-native")
    args=p.parse_args()
    shard(args.shard,pathlib.Path(args.binary)) if args.action=="shard" else audit()
