#!/usr/bin/env python3
"""Audit ONLY, no solvers: strict SHA, complete pairs, SAT witness tier and PAR2."""
import collections,csv,json,pathlib,statistics,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r148_new_real_blind_benchmark as b
ROOT=b.ROOT;MODES=b.MODES
def need(x,why):
    if not x:raise RuntimeError("R148_BLIND_AUDIT_REFUSED "+str(why))
def audit():
    manifest_sha,cs,m=b.setup()
    shards=[json.loads((ROOT/f"shard-{k}.json").read_text()) for k in range(b.SHARDS)]
    need(all(s["protocol"]==b.PROTO and s["manifest_sha256"]==manifest_sha for s in shards),
         "wrong original source manifest")
    pins=[json.dumps(x["pinned_sha256"],sort_keys=True) for x in shards]
    need(len(set(pins))==1,"reference binaries or R148 native gate SHA differ")
    rows=[r for s in shards for r in s["rows"]]
    need(len(rows)==len(cs)*b.REPS*len(MODES),"missing rows")
    by_sha={c["sha256"]:c for c in cs}
    idx={}
    for x in rows:
        src=by_sha.get(x["sha256"])
        need(src is not None and x["id"]==src["id"] and x["cohort"]==src["cohort"],
             "original CNF identity drift")
        need(x["mode"] in MODES and x["repeat"] in (0,1),"wrong mode or repeat")
        need(x["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid result")
        need(0<=x["seconds"]<=b.CAP+1e-5,"invalid 15s cap")
        need(abs(x["par2"]-(30.0 if x["status"]=="TIMEOUT" else x["seconds"]))<1e-4,"PAR2 cap wrong")
        if x["status"]=="SAT":
            need(x["proof"]=="source_SAT_witness_verified","original SAT model not verified")
        if x["status"]=="UNSAT":
            need(x["proof"]=="UNSAT_without_independent_LRAT_proof","false UNSAT proof claim")
        if x["mode"] in ("r135","r148"):
            need(x["selector_target"] in ("kissat","cadical"),"unknown route")
            need(x["selector_cost_s"]>=0,"unmeasured detection")
        key=(x["sha256"],x["repeat"],x["mode"])
        need(key not in idx,"duplicate paired row")
        idx[key]=x
    for c in cs:
        for rep in range(b.REPS):
            seen={idx[(c["sha256"],rep,mode)]["status"] for mode in MODES}-{"TIMEOUT"}
            need(len(seen)<=1,"SAT/UNSAT disagreement "+c["sha256"])
            need(idx[(c["sha256"],rep,"r135")]["selector_target"]==
                 idx[(c["sha256"],rep,"r148")]["selector_target"],
                 "new source route parity false")
    summary={}
    for mode in MODES:
        r=[v for v in rows if v["mode"]==mode]
        solved=[v["seconds"] for v in r if v["status"]!="TIMEOUT"]
        summary[mode]=dict(trials=len(r),solved=len(solved),
            SAT=sum(v["status"]=="SAT" for v in r),
            UNSAT_unverified=sum(v["status"]=="UNSAT" for v in r),
            timeouts=sum(v["status"]=="TIMEOUT" for v in r),
            PAR2_total_s=round(sum(v["par2"] for v in r),6),
            median_solved_s=round(statistics.median(solved),6) if solved else None,
            detector_total_s=round(sum(v.get("selector_cost_s") or 0 for v in r),6),
            detector_median_s=round(statistics.median(v["selector_cost_s"] for v in r),6)
                if mode in ("r135","r148") else None)
    comparisons={}
    for mode in ("cadical","r118","r135","r148"):
        diffs=[sum(idx[(c["sha256"],rep,mode)]["par2"]-
                   idx[(c["sha256"],rep,"kissat")]["par2"] for rep in range(b.REPS))
               for c in cs]
        comparisons[mode]=dict(
            gain_vs_kissat_percent=round(100*(summary["kissat"]["PAR2_total_s"]/
                    summary[mode]["PAR2_total_s"]-1),6),
            formula_wins=sum(d<-0.00001 for d in diffs),
            formula_losses=sum(d>0.00001 for d in diffs),
            regressions_2x=sum(
                sum(idx[(c["sha256"],rep,mode)]["par2"] for rep in range(b.REPS)) >=
                2*sum(idx[(c["sha256"],rep,"kissat")]["par2"] for rep in range(b.REPS))
                for c in cs))
    by_cohort={}
    for co in sorted({c["cohort"] for c in cs}):
        group={c["sha256"] for c in cs if c["cohort"]==co}
        by_cohort[co]=dict(formulas=len(group),
            par2={mode:round(sum(x["par2"] for x in rows if x["sha256"] in group and x["mode"]==mode),6)
                  for mode in MODES},
            solved={mode:sum(x["status"]!="TIMEOUT" for x in rows if x["sha256"] in group and x["mode"]==mode)
                    for mode in MODES})
    deltas=[]
    for c in cs:
        x=c["sha256"];p={mode:round(sum(idx[(x,rep,mode)]["par2"] for rep in range(b.REPS)),6)
                         for mode in MODES}
        deltas.append(dict(id=c["id"],sha256=x,cohort=c["cohort"],
            r135_target=idx[(x,0,"r135")]["selector_target"],
            r148_target=idx[(x,0,"r148")]["selector_target"],
            r148_minus_r135_PAR2_s=round(p["r148"]-p["r135"],6),**p))
    report=dict(protocol=b.PROTO,source_manifest_sha256=manifest_sha,
        original_source_SHA_verified=True,source_phase=m["phase"],
        original_CNF_unchanged=True,source_excludes_previous_400_132_135_135s=True,
        formulas=len(cs),measurements=len(rows),shards=b.SHARDS,repeats=b.REPS,cap_s=b.CAP,
        evaluation="PROSPECTIVE PRE-FROZEN REAL SAT SHA/URL/GBD-EXCLUDED HOLDOUT",
        no_performance_based_candidate_selection=True,
        source_indexes=m["index_provenance"],cohort_counts=m["cohort_counts"],
        summary=summary,comparisons=comparisons,by_cohort=by_cohort,
        r148_vs_r135_PAR2_gain_pct=round(100*(summary["r135"]["PAR2_total_s"]/
              summary["r148"]["PAR2_total_s"]-1),6),
        r148_vs_r135_faster_formulas=sum(d["r148_minus_r135_PAR2_s"]<-.00001 for d in deltas),
        r148_vs_r135_slower_formulas=sum(d["r148_minus_r135_PAR2_s"]>.00001 for d in deltas),
        selector_route_disagreements=sum(d["r148_target"]!=d["r135_target"] for d in deltas),
        CPU_models=[x["runner_cpu"] for x in shards],
        independent_UNSAT_proof=False,
        verdict="AUDIT_ONLY_NO_PROMOTION_BEFORE_INDEPENDENT_UNSAT_CERTIFICATION_AND_FURTHER_REPLICATION")
    b.write(ROOT/"report.json",report)
    with (ROOT/"paired.csv").open("w",newline="") as f:
        fieldnames=sorted({key for x in rows for key in x})
        w=csv.DictWriter(f,fieldnames=fieldnames);w.writeheader();w.writerows(rows)
    with (ROOT/"per_formula.csv").open("w",newline="") as f:
        fieldnames=sorted({key for x in deltas for key in x})
        w=csv.DictWriter(f,fieldnames=fieldnames);w.writeheader();w.writerows(deltas)
    print("R148_NEW_REAL_BLIND_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":audit()
