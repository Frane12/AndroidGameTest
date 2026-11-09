#!/usr/bin/env python3
"""Independent DMD8 recovery audit over IM-MUT-ABLE 42715717640 artifact outputs.

The original run's four paired shards SUCCEEDED (126 source-paired E2E rows),
but its reporting code raised KeyError due to a wrong DMD7 manifest key.
This audits EXISTING artifacts without rerunning solvers, fixing code in frozen
measurement jobs, or attributing artificial bounded UP events to real CDCL.

Source SAT witness was checked in the solver at measurement time and the
boolean is audited here. Raw models are not independently replayed anew.
Original UNSAT outputs are backend-only without independent LRAT.
"""
from __future__ import annotations
import collections,hashlib,json,pathlib,tempfile
import dmd8_bounded_bench as old

ROOT=pathlib.Path("mre_dmd8")
ARMS=old.ARMS
CAP=old.CAP
REPS=old.REPS
SHARDS=old.SHARDS
SOURCE_RUN=42715717640

def need(ok,msg):
    if not ok:raise RuntimeError("DMD8_RECOVERY_FAIL_CLOSED "+str(msg))

def main():
    # This checks original DMD8 source and binary hashes, source roster,
    # immutable original EQUIV7 SHA, and the frozen DMD7 screen manifest.
    m,predecessor,bysha=old.check()
    need(m["expected_trials"]==126 and predecessor["selected"]==m["selected_sha"],
         "unexpected original experiment coverage")
    # Independent DMD7 proof replay from the original exact SHA once per source.
    proof=[]
    for entry in predecessor["selected_cases"]:
        case=bysha[entry["sha256"]]
        with tempfile.TemporaryDirectory(prefix="dmd8-replay-") as td:
            n,cs,clauses,raw=old.prior.derive(case,pathlib.Path(td))
        need(old.prior.digest(raw["certificates"])==entry["candidate_signature"] and
             len(clauses)==entry["proof_verified"] and
             old.prior.d5.d1.sha(case["path"])==entry["sha256"],
             "original parent proof replay or source SHA failed")
        proof.append(dict(filename=entry["filename"],proved=len(clauses),sha256=entry["sha256"]))
    rows=[]
    for shard in range(SHARDS):
        p=ROOT/f"shard-{shard}.json"
        need(p.is_file(),"missing shard artifact "+str(shard))
        items=json.loads(p.read_text())
        expected=len(predecessor["selected_cases"][shard::SHARDS])*REPS*len(ARMS)
        need(len(items)==expected,"shard count mismatch "+str(shard))
        rows.extend(items)
    expected={(sha,rep,arm) for sha in predecessor["selected"]
              for rep in range(REPS) for arm in ARMS}
    index={(r["original_sha256"],r["rep"],r["arm"]):r for r in rows}
    need(len(rows)==len(index)==len(expected)==126 and set(index)==expected,
         "duplicated or missing paired original-SHA E2E trial")
    for x in rows:
        need(x["protocol"]==old.PROTO and x["cap_s"]==CAP and
             x["one_logical_cpu"] and x["source_SHA_verified"] and
             x["status"] in ("SAT","UNSAT","TIMEOUT"),
             "trial protocol and immutable original source mismatch")
        need(x["status"]!="SAT" or x["SAT_original_verified"],
             "SAT result without original witness verification")
        need(x["UNSAT_independent_LRAT"]==False,
             "unexpected independently claimed UNSAT proof")
        need(x["selected_lemmas"] in range(5) and
             x["selected_lemmas"]<=
              (4 if x["arm"]=="dmd8_top4" else 1 if
                 x["arm"] in ("dmd8_top1","dmd7_top1") else 0),
             "unregistered source-proof lemma selection")
        if x["arm"] not in ("cadical_clean","kissat_original"):
            source_entry=next(e for e in predecessor["selected_cases"]
                              if e["sha256"]==x["original_sha256"])
            need(x["original_proof_replayed"] and
                 x["proof_sha256"]==source_entry["candidate_signature"],
                 "source original two-parent proof not replayed")
        need(abs(x["PAR2_s"] -
              (16 if x["status"]=="TIMEOUT" else x["e2e_s"]))<1e-5,
             "PAR2 formula or E2E mismatch")
        if x["arm"].startswith("dmd8_"):
            probe=x["probe"]
            if x["arm"] in old.GATED:
                need(probe["protocol"]=="DMD8-SYNC-UP-TWO-ROUND-v1"
                     and probe["probe_rounds"]==2 and
                     probe["per_candidate_max_probes"]==2 and
                     probe["max_candidates"]==16 and
                     len(probe["selected_indices"])<=4 and
                     all(z["score"]>0 for z in probe["features"]
                         if z["index"] in probe["selected_indices"]),
                     "improper UP probe claimed")
                expected_added=0 if x["arm"]=="dmd8_probe_shadow" else (
                      min(1,len(probe["selected_indices"]))
                      if x["arm"]=="dmd8_top1" else
                      min(4,len(probe["selected_indices"])))
                need(x["selected_lemmas"]==expected_added,
                     "probe selection inconsistent with added lemmas")
    scores={}
    for arm in ARMS:
        a=[r for r in rows if r["arm"]==arm]
        scores[arm]=dict(trials=len(a),
          SAT_verified=sum(x["status"]=="SAT" for x in a),
          UNSAT_backend_only=sum(x["status"]=="UNSAT" for x in a),
          solved=sum(x["status"]!="TIMEOUT" for x in a),
          PAR2_s=round(sum(x["PAR2_s"] for x in a),6),
          CPU_s=round(sum(x["child_CPU_s"] for x in a),6),
          appended_lemmas=sum(x["selected_lemmas"] for x in a),
          activated_trials=sum(x["selected_lemmas"]>0 for x in a),
          positive_probe_trials=sum(x["probe_positive_candidates"]>0 for x in a),
          probe_abstentions=sum(x["probe"].get("abstained",False) for x in a),
          total_probe_s=round(sum(x["probe_wall_s"] for x in a),6),
          conflicts_censored=sum(x["cdcl_stats"].get("conflicts",0) for x in a),
          decisions_censored=sum(x["cdcl_stats"].get("decisions",0) for x in a))
    ref=scores["cadical_clean"]["PAR2_s"]
    for v in scores.values():
        v["speedup_x_vs_clean"]=round(ref/v["PAR2_s"],6)
    paired={}
    for arm in ARMS:
        if arm in ("cadical_clean","kissat_original"):continue
        pair=[(index[(sha,rep,arm)],
               index[(sha,rep,"cadical_clean")],
               index[(sha,rep,"dmd8_probe_shadow")])
              for sha in predecessor["selected"] for rep in range(REPS)]
        paired[arm]=dict(
            pairs=len(pair),
            net_PAR2_gain_vs_clean_s=round(sum(b["PAR2_s"]-x["PAR2_s"]
                                           for x,b,shadow in pair),6),
            net_PAR2_gain_vs_probe_shadow_s=round(sum(shadow["PAR2_s"]-x["PAR2_s"]
                                             for x,b,shadow in pair),6),
            wins_vs_clean=sum(x["PAR2_s"]<b["PAR2_s"]-.02
                              for x,b,shadow in pair),
            losses_vs_clean=sum(x["PAR2_s"]>b["PAR2_s"]+.02
                                for x,b,shadow in pair),
            successful_with_new_lemmas=sum(x["selected_lemmas"]>0 and
                x["status"]!="TIMEOUT" for x,b,shadow in pair))
    regressions=[]
    for sha in predecessor["selected"]:
        for rep in range(REPS):
            base=index[(sha,rep,"cadical_clean")]
            for arm in ("dmd8_top1","dmd8_top4"):
                actual=index[(sha,rep,arm)]
                if base["status"]!="TIMEOUT" and actual["status"]=="TIMEOUT":
                    regressions.append(dict(filename=actual["filename"],
                       rep=rep,arm=arm,baseline_status=base["status"],
                       baseline_E2E_s=base["e2e_s"],added_lemmas=actual["selected_lemmas"],
                       probe_top_score=actual["probe_top_score"]))
    mismatches=[]
    for sha in predecessor["selected"]:
        for rep in range(REPS):
            xs=[index[(sha,rep,a)] for a in old.GATED]
            valid=[x["probe"]["features"] for x in xs
                   if not x["probe"].get("abstained")]
            if any(v!=valid[0] for v in valid[1:]):
                mismatches.append(dict(source=sha,rep=rep))
    result=dict(protocol=old.PROTO,
       source_run=SOURCE_RUN,screened_orig_SHA=24,
       selected_orig_SHA=9,matched_trials=len(rows),
       all_four_shards_finished=True,immutable_source_proof_replay=True,
       original_source_SAT_witness_verified_during_solver=True,
       original_SAT_model_not_replayed_from_artifact=True,
       UNSAT_independent_LRAT=False,one_logical_cpu=True,
       second_audit_recovers_reporter_KeyError_not_solver_failure=True,
       probe_is_synthetic_source_counterfactual_not_real_CDCL=True,
       globally_unseen=False,no_promotion=True,
       scores=scores,paired=paired,case_regressions=regressions,
       deterministic_probe_feature_mismatches=mismatches,
       original_local_proof_sources=proof)
    (ROOT/"recovered_report.json").write_text(
         json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("DMD8_RECOVERED_FINAL",json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":main()
