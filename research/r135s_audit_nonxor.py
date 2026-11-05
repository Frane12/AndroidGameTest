#!/usr/bin/env python3
"""Strict R135 audit of immutable SHA-disjoint paired solver measurements."""
import collections,csv,json,pathlib,statistics
import r135s_run_nonxor as b
ROOT=pathlib.Path("r135s")
MODES=b.MODES
REPS=b.REPS
SHARDS=b.SHARDS
PROTO=b.PROTO
def need(v,m):
    if not v:raise RuntimeError("R135S_AUDIT_REFUSED "+str(m))
def audit():
    cs=b.selected()
    manifest_sha=b.sha(b.SOURCES/"manifest.json")
    shards=[json.loads((ROOT/f"shard-{i}.json").read_text()) for i in range(SHARDS)]
    need(all(x["protocol"]==PROTO and x["source_manifest_sha256"]==manifest_sha for x in shards),"source drift")
    need(len({json.dumps(x["binary_sha256"],sort_keys=True) for x in shards})==1,"pinned binary drift")
    rows=[y for sh in shards for y in sh["rows"]]
    probes=[y for sh in shards for y in sh["probes"]]
    need(len(rows)==len(cs)*REPS*len(MODES),"missing measurements")
    need(len(probes)==len(cs),"missing probes")
    cases={x["sha256"]:x for x in cs}
    idx={}
    for x in rows:
        c=cases.get(x["sha256"])
        need(c and c["id"]==x["id"],"formula identity mismatch")
        need(x["mode"] in MODES and x["repeat"] in range(REPS),"unexpected mode/repeat")
        need(x["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid solver status")
        if x["status"]=="SAT":need(x["proof"]=="source_SAT_witness_verified","SAT model not verified")
        if x["status"]=="UNSAT":need(x["proof"]=="UNSAT_without_independent_LRAT_proof","false independent UNSAT claim")
        need(abs(x["par2"]-(30 if x["status"]=="TIMEOUT" else x["seconds"]))<1e-5,"bad PAR2")
        key=(x["sha256"],x["repeat"],x["mode"])
        need(key not in idx,"duplicate paired measurement")
        idx[key]=x
    for sha in cases:
        for rep in range(REPS):
            statuses={idx[(sha,rep,m)]["status"] for m in MODES}-{"TIMEOUT"}
            need(len(statuses)<=1,"SAT/UNSAT contradiction")
    summary={}
    for mode in MODES:
        x=[r for r in rows if r["mode"]==mode]
        done=[r["seconds"] for r in x if r["status"]!="TIMEOUT"]
        summary[mode]=dict(trials=len(x),solved=len(done),
            SAT=sum(r["status"]=="SAT" for r in x),
            UNSAT=sum(r["status"]=="UNSAT" for r in x),
            timeout=sum(r["status"]=="TIMEOUT" for r in x),
            PAR2_total_s=round(sum(r["par2"] for r in x),6),
            median_solved_wall_s=round(statistics.median(done),6) if done else None,
            GF2_solved=sum(r["GF2_solved"] for r in x))
    comparisons={}
    for mode in MODES:
        if mode=="kissat":continue
        pairs=[(sum(idx[(sha,rep,mode)]["par2"] for rep in range(REPS)),
                sum(idx[(sha,rep,"kissat")]["par2"] for rep in range(REPS))) for sha in cases]
        comparisons[mode]=dict(
            gain_vs_kissat_percent=round(100*(summary["kissat"]["PAR2_total_s"]/summary[mode]["PAR2_total_s"]-1),5),
            faster_formula_pairs=sum(a+1e-5<b for a,b in pairs),
            slower_formula_pairs=sum(b+1e-5<a for a,b in pairs),
            wins_2x=sum(b>=2*a for a,b in pairs),
            regressions_2x=sum(a>=2*b for a,b in pairs))
    sel=[r for r in rows if r["mode"]=="r135"]
    cohorts=sorted({c["cohort"] for c in cs})
    report=dict(protocol=PROTO,
        phase="FROZEN_SHA_DISJOINT_UNSEEN_R135S_NONXOR_PORTFOLIO",
        original_manifest_sha256=manifest_sha,source_sha_verified=True,
        formulas=len(cs),measurements=len(rows),repeats=REPS,CAP_s=b.CAP,
        original_CNF_unchanged=True,
        frozen_selector="observed>=32 and binary_fraction<0.20 and horn_fraction<0.50 -> CaDiCaL, otherwise Kissat; max 128KiB/2000 clauses",
        all_detector_overhead_included=True,
        detector_median_s=round(statistics.median(r["detector_s"] for r in sel),6),
        detector_total_s=round(sum(r["detector_s"] for r in sel),6),
        selector_routes=dict(collections.Counter(r["route"] for r in sel)),
        detector_reasons=dict(collections.Counter(r["detector_reason"] for r in sel)),
        source_cohorts=dict(collections.Counter(c["cohort"] for c in cs)),
        by_cohort={co:dict(formulas=sum(c["cohort"]==co for c in cs),
               par2={m:round(sum(r["par2"] for r in rows if r["cohort"]==co and r["mode"]==m),6) for m in MODES},
               solved={m:sum(r["status"]!="TIMEOUT" for r in rows if r["cohort"]==co and r["mode"]==m) for m in MODES}) for co in cohorts},
        summary=summary,comparisons=comparisons,
        runner_cpu_models=[x["runner_cpu"] for x in shards],
        no_independent_UNSAT_LRAT=True,no_contest_rank_claim=True,
        verdict="NO_PROMOTION: even positive results need independent UNSAT proofs and replication",
        cautions=["R134 features derived from previously inspected R132 development data",
                  "This holdout is not a SAT Competition rank and includes multiple host CPU models",
                  "Portfolio can only choose pinned original Kissat or CaDiCaL; no new CDCL algorithm",
                  "Never select benchmark formulas based on result or speed"])
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    fields=sorted({k for row in rows for k in row})
    with (ROOT/"paired.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    with (ROOT/"probes.csv").open("w",newline="") as f:
        fields=sorted({k for row in probes for k in row})
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(probes)
    print("R135S_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":audit()
