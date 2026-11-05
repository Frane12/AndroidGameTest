#!/usr/bin/env python3
"""Strict R135S-vs-R135 existing-400-CNF paired replica audit; NO solver reruns."""
import collections,csv,json,pathlib,statistics,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r135s_400_paired as bm

ROOT=bm.ROOT
MODES=bm.MODES
def need(v,msg):
    if not v:raise RuntimeError("R135S400_AUDIT_REFUSED "+str(msg))
def audit():
    source_sha,cases=bm.setup()
    shards=[json.loads((ROOT/f"shard-{i}.json").read_text()) for i in range(bm.SHARDS)]
    need(all(x["protocol"]==bm.PROTO and x["source_manifest_sha256"]==source_sha
             and x["original_cnf_unchanged"] for x in shards),"shard source manifest mismatch")
    hashes=[json.dumps(x["pinned_sha256"],sort_keys=True) for x in shards]
    need(len(set(hashes))==1,"pinned original binaries or R135S detector differ between shards")
    need(len(set(h["runner_cpu"] for h in shards))>=1,"missing CPU model evidence")
    rows=[r for sh in shards for r in sh["rows"]]
    need(len(rows)==400*bm.REPS*len(MODES),"expected 4000 paired measurements")
    bysha={x["sha256"]:x for x in cases}
    idx={}
    for r in rows:
        c=bysha.get(r["sha256"])
        need(c is not None and r["id"]==c["id"] and r["cohort"]==c["cohort"],
             "formula SHA/id/cohort identity drift")
        need(r["mode"] in MODES and r["repeat"] in range(bm.REPS),"unexpected mode/repeat")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid status")
        need(0<=r["seconds"]<=bm.CAP+1e-5,"wall outside 15s cap")
        need(abs(r["par2"]-(30.0 if r["status"]=="TIMEOUT" else r["seconds"]))<1e-4,
             "invalid PAR2 penalty")
        if r["status"]=="SAT":
            need(r["proof"]=="source_SAT_witness_verified","SAT model verification missing")
        if r["status"]=="UNSAT":
            need(r["proof"]=="UNSAT_without_independent_LRAT_proof","false UNSAT certification")
        if r["mode"]=="r135s":
            need(r["route"] in ("KISSAT","CADICAL"),"invalid R135S selector route")
            need(r["observed_clauses"]>=0,"invalid sample count")
            need(r["detector_s"]>=0,"invalid detector cost")
        if r["mode"]=="r135":
            need(r["selector_target"] in ("kissat","cadical"),"invalid original R135 route")
            need(r["selector_cost_s"]>=0,"original R135 detector missing")
        key=(r["sha256"],r["repeat"],r["mode"])
        need(key not in idx,"duplicate case-repetition-mode")
        idx[key]=r
    for c in cases:
        for rep in range(bm.REPS):
            statuses={idx[(c["sha256"],rep,m)]["status"] for m in MODES}-{"TIMEOUT"}
            need(len(statuses)<=1,"SAT/UNSAT disagreement "+c["sha256"])
    summary={}
    for mode in MODES:
        a=[r for r in rows if r["mode"]==mode]
        done=[r["seconds"] for r in a if r["status"]!="TIMEOUT"]
        summary[mode]=dict(trials=len(a),solved=len(done),
            SAT=sum(r["status"]=="SAT" for r in a),
            UNSAT=sum(r["status"]=="UNSAT" for r in a),
            timeouts=sum(r["status"]=="TIMEOUT" for r in a),
            par2_total_s=round(sum(r["par2"] for r in a),6),
            total_wall_s=round(sum(r["seconds"] for r in a),6),
            median_solved_s=round(statistics.median(done),6) if done else None)
    comparisons={}
    for mode in ("cadical","r118","r135","r135s"):
        comparisons[mode]=dict(
            gain_vs_kissat_percent=round(100*(summary["kissat"]["par2_total_s"]/summary[mode]["par2_total_s"]-1),6),
            faster_formulas=sum(sum(idx[(x["sha256"],rep,mode)]["par2"] for rep in range(bm.REPS))<
                                sum(idx[(x["sha256"],rep,"kissat")]["par2"] for rep in range(bm.REPS))-1e-5 for x in cases),
            slower_formulas=sum(sum(idx[(x["sha256"],rep,mode)]["par2"] for rep in range(bm.REPS))>
                                sum(idx[(x["sha256"],rep,"kissat")]["par2"] for rep in range(bm.REPS))+1e-5 for x in cases),
            regressions_2x=sum(sum(idx[(x["sha256"],rep,mode)]["par2"] for rep in range(bm.REPS))>=
                               2*sum(idx[(x["sha256"],rep,"kissat")]["par2"] for rep in range(bm.REPS)) for x in cases))
    compared=[]
    for c in cases:
        sha=c["sha256"]
        totals={m:round(sum(idx[(sha,rep,m)]["par2"] for rep in range(bm.REPS)),6) for m in MODES}
        rs=idx[(sha,0,"r135s")]
        ro=idx[(sha,0,"r135")]
        sr=rs["route"].lower()
        orig=ro["selector_target"]
        compared.append(dict(sha256=sha,id=c["id"],cohort=c["cohort"],
            r135s_route=sr,r135_route=orig,routes_disagree=sr!=orig,
            r135s_binary_fraction=rs["binary_fraction"],r135s_horn_fraction=rs["horn_fraction"],
            r135_binary_fraction=ro["binary_ratio"],r135_horn_fraction=ro["horn_ratio"],
            r135s_prefix_limited=rs["prefix_limited"],
            **{m+"_par2_s":totals[m] for m in MODES},
            r135s_vs_r135_delta_s=round(totals["r135s"]-totals["r135"],6),
            r135s_vs_kissat_delta_s=round(totals["r135s"]-totals["kissat"],6)))
    def summarize_by(groupname,group):
        return dict(formulas=len(group),par2_s={mode:round(sum(x[mode+"_par2_s"] for x in group),6) for mode in MODES},
            r135s_vs_r135_delta_s=round(sum(x["r135s_vs_r135_delta_s"] for x in group),6))
    by_cohort={name:summarize_by(name,[x for x in compared if x["cohort"]==name])
        for name in sorted({x["cohort"] for x in compared})}
    head_to_head=dict(
        r135s_gain_vs_r135_percent=round(100*(summary["r135"]["par2_total_s"]/summary["r135s"]["par2_total_s"]-1),6),
        r135s_faster_formulas=sum(x["r135s_vs_r135_delta_s"]<-.00001 for x in compared),
        r135_faster_formulas=sum(x["r135s_vs_r135_delta_s"]>.00001 for x in compared),
        r135s_regressions_2x_vs_r135=sum(x["r135s_par2_s"]>=2*x["r135_par2_s"] for x in compared),
        r135s_wins_2x_vs_r135=sum(x["r135_par2_s"]>=2*x["r135s_par2_s"] for x in compared),
        disagreements=sum(x["routes_disagree"] for x in compared),
        disagree_r135s_better=sum(x["routes_disagree"] and x["r135s_vs_r135_delta_s"]<-.00001 for x in compared),
        disagree_r135_better=sum(x["routes_disagree"] and x["r135s_vs_r135_delta_s"]>.00001 for x in compared))
    orig=[r for r in rows if r["mode"]=="r135"]
    mini=[r for r in rows if r["mode"]=="r135s"]
    report=dict(protocol=bm.PROTO,source_manifest_sha256=source_sha,
        source_original_R135_400=True,original_SHA_verified=True,
        formulas=400,measurements=len(rows),repeats=bm.REPS,shards=bm.SHARDS,cap_s=bm.CAP,
        design="POST-HOC PAIRED REPLICATION of already-used 400 SHA-frozen original CNFs; NOT a new blind holdout",
        original_CNF_modified=False,source_previously_measured=True,
        r135_frozen_rule="full-or-prefix 8MiB/120000 clauses; incomplete -> Kissat; 0.30 binary or 0.55 Horn -> Kissat; else CaDiCaL",
        r135s_frozen_rule="128KiB/2000-clauses prefix; >=32 and binary <0.20 and Horn <0.50 -> CaDiCaL; else Kissat",
        original_solver_versions_pinned=True,detector_wall_included=True,
        detector=dict(
            r135_median_s=round(statistics.median(x["selector_cost_s"] for x in orig),6),
            r135_total_s=round(sum(x["selector_cost_s"] for x in orig),6),
            r135s_median_s=round(statistics.median(x["detector_s"] for x in mini),6),
            r135s_total_s=round(sum(x["detector_s"] for x in mini),6),
            r135s_route_counts=dict(collections.Counter(x["route"] for x in mini)),
            r135_route_counts=dict(collections.Counter(x["selector_target"] for x in orig))),
        head_to_head=head_to_head,by_cohort=by_cohort,
        summary=summary,comparisons=comparisons,
        runner_cpu_models=[x["runner_cpu"] for x in shards],
        independent_unsat_proofs=False,independent_blind_replication=False,
        verdict="COMPARATIVE_ONLY_NO_PROMOTION_REQUIRES_INDEPENDENT_UNSAT_AND_NEW_BLIND_HOLDOUT")
    bm.write(ROOT/"report.json",report)
    cols=sorted({k for x in rows for k in x})
    with (ROOT/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
    cols=sorted({k for x in compared for k in x})
    with (ROOT/"per_formula.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(compared)
    print("R135S400_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":audit()
