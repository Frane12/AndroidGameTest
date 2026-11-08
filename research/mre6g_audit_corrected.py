#!/usr/bin/env python3
"""Audit EXACT previously finished MRE6g 60 real SAT2026 solves.

The original MRE6g audit inherited MRE6f's '48' count despite adding a
fifth arm. Reuses its unchanged source/seed/SAT checks, fixes only
expected 6×2×5=60 attempts. No solve rerun or source selection.
"""
from mre6g_medium_benchmark import *
def audit():
    frozen.verify(INPUT)
    manifest=json.loads((INPUT/"manifest.json").read_text())
    records=[]
    for i in range(SHARDS):
        file=ROOT/("shard-%d.json"%i)
        need(file.exists(),"missing shard")
        records+=json.loads(file.read_text())
    need(len(records)==6*REPS*len(MODES)==60,"expected 60 paired results")
    permitted={c["sha256"]:c for c in manifest["cases"]}
    pairing=collections.defaultdict(dict)
    for r in records:
        c=permitted.get(r["original_sha256"])
        need(c and c["name"]==r["source"] and c["cohort"]==r["source_cohort"],
             "source pairing drift")
        need(r["protocol"]==PROTO and r["same_pinned_CMS_source_sha"]==CMS_SOURCE_SHA
             and r["otf_gauss"] is False and r["full_cost_includes_proof_and_reconstruction"],
             "configuration drift")
        if r["status"]=="SAT":
            need(r["source_original_SAT_witness_verified"] and r["expected"]=="SAT",
                 "missing verified original SAT model")
        if r["status"]=="UNSAT":
            need(c["expected"]=="UNSAT" and r["official_UNSAT_status_crosschecked"],
                 "UNSAT not crosschecked")
        pair=(r["original_sha256"],r["rep"])
        need(r["mode"] not in pairing[pair],"duplicate pair")
        pairing[pair][r["mode"]]=r
    need(len(pairing)==12,"missing source-rep pair")
    for z in pairing.values():
        need(set(z)==set(MODES),"five-arm pair incomplete")
        need(len({a["seed"] for a in z.values()})==1,
             "different native solver seeds")
    bycohort={}
    for cohort in ("REUSED_known_solved_diagnostic","NEW_official_reference_medium"):
        bycohort[cohort]={}
        for mode in MODES:
            rows=[r for r in records if r["mode"]==mode and r["source_cohort"]==cohort]
            bycohort[cohort][mode]=dict(
                n=len(rows),
                solved=sum(r["status"] in ("SAT","UNSAT") for r in rows),
                timeouts=sum(r["status"]=="TIMEOUT" for r in rows),
                par2_s=round(sum(r["par2_s"] for r in rows),6),
                full_wall_s=round(sum(r["full_wall_s"] for r in rows),6),
                prep_s=round(sum(r["gate"]["preprocessing_wall_s"] for r in rows),6),
                cpu_solve_samples=sum(r["native_solve_cpu_s"] is not None for r in rows),
                solver_cpu_s=round(sum(r["native_solve_cpu_s"] or 0 for r in rows),6),
                certified_merges=sum(r["gate"]["eliminated_variables"] for r in rows))
    allmodes={}
    for mode in MODES:
        rows=[r for r in records if r["mode"]==mode]
        allmodes[mode]=dict(
            solved=sum(r["status"] in ("SAT","UNSAT") for r in rows),
            attempts=len(rows),
            par2_s=round(sum(r["par2_s"] for r in rows),6),
            prep_s=round(sum(r["gate"]["preprocessing_wall_s"] for r in rows),6),
            equality_active_sources=len({r["source"] for r in rows if r["certified_quotient_applied"]}),
            timeouts=sum(r["status"]=="TIMEOUT" for r in rows))
    per_source=[]
    for c in manifest["cases"]:
        found=[r for r in records if r["original_sha256"]==c["sha256"]]
        per_source.append(dict(source=c["name"],cohort=c["cohort"],
            status=c["expected"],external_reference_s=c["published_reference_s"],
            per_mode={m:dict(
                solved=sum(r["status"]!="TIMEOUT" for r in found if r["mode"]==m),
                par2_s=round(sum(r["par2_s"] for r in found if r["mode"]==m),6),
                gates=[r["gate"]["gate"] for r in found if r["mode"]==m],
                eliminated_variables=[r["gate"]["eliminated_variables"]
                                    for r in found if r["mode"]==m])
                for m in MODES}))
    report=dict(protocol=PROTO,sources=6,
       repeats=2,attempts=60,cap_s=CAP,
       anchors_reused=2,externally_selected_new_sources=4,
       comparison_design="same MRE7 pre-frozen 6 original SHA paired across all 5 arms and seeds",
       official_source_disjoint_new_not_exhaustively_verified=True,
       cohort_is_not_new_blind_test=True,
       entire_35s_wall_charged=True,
       all_SAT_models_checked_on_original=True,
       UNSAT_independent_LRAT=False,
       no_unsolved_CDCL_counter_claims=True,
       by_cohort=bycohort,modes=allmodes,per_source=per_source,
       no_policy_promoted_without_new_source_validation=True)
    ROOT.mkdir(parents=True,exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("MRE6G_FINAL",json.dumps(report,sort_keys=True),flush=True)


if __name__=="__main__":
    audit()
