#!/usr/bin/env python3
"""R136: reliability-first read-only structural feedback from frozen R135.

NO new SAT solving, threshold tuning, dynamic gate or claim of causality.
Reuse R135 paired run 42061956160 after its strict source, binary, SAT
witness and PAR-2 audit. This is *development feedback* on a seen R135 cohort;
future prospective validation MUST use new SHA-disjoint CNFs.
"""
import collections
import csv
import hashlib
import json
import pathlib
import random
import statistics
import sys

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r135_run_nonxor as benchmark
import r135_audit_nonxor as prior

ROOT = pathlib.Path("r135")
OUT = pathlib.Path("r136")
NBOOT = 3000
SEED = 13620261105
ABS_MARGIN = 0.05
REL_MARGIN = 0.02

def require(x,msg):
    if not x:
        raise RuntimeError("R136_FAIL_CLOSED "+msg)

def gain(base,alternative):
    return 100.0*(base-alternative)/base if base > 0 else 0.0

def bootstrap(by_formula):
    rng=random.Random(SEED)
    sample=list(by_formula)
    n=len(sample)
    require(n>0,"no formula identities")
    values=[]
    for _ in range(NBOOT):
        draw=[sample[rng.randrange(n)] for __ in range(n)]
        baseline=sum(x["kissat_par2"] for x in draw)
        selected=sum(x["r135_par2"] for x in draw)
        values.append(gain(baseline,selected))
    values.sort()
    return [round(values[int(0.025*(NBOOT-1))],6),
            round(values[int(0.975*(NBOOT-1))],6)]

def main():
    # Run the existing authoritative check first.  Never trust just a JSON
    # summary: validate eight raw shards, source SHA, pins and all pair keys.
    prior.audit()
    cases=benchmark.selected()
    frozen=ROOT/"frozen"/"manifest.json"
    manifest_sha=benchmark.sha(frozen)
    idx={}
    probes={}
    binary_pins=set()
    cpus={}
    for shard in range(benchmark.SHARDS):
        path=ROOT/f"shard-{shard}.json"
        require(path.exists(),"missing shard "+str(shard))
        record=json.loads(path.read_text())
        require(record["protocol"]==benchmark.PROTO,"protocol drift")
        require(record["source_manifest_sha256"]==manifest_sha,"source hash drift")
        binary_pins.add(json.dumps(record["binary_sha256"],sort_keys=True))
        cpus[shard]=record["runner_cpu"]
        for p in record["probes"]:
            key=p["sha256"]
            require(key not in probes,"duplicate formula probe")
            probes[key]=p
        for row in record["rows"]:
            key=(row["sha256"],row["repeat"],row["mode"])
            require(key not in idx,"duplicate paired trial")
            idx[key]=row
    require(len(binary_pins)==1,"pinned solver/selector binary SHA drift")
    require(len(cases)==56 and len(probes)==56,"unexpected R135 heldout cases")
    require(len(idx)==56*benchmark.REPS*len(benchmark.MODES),"incomplete paired trial ledger")
    by_sha={}
    records=[]
    route_counts=collections.Counter()
    regime_counts=collections.Counter()
    cost_total=0
    for case in cases:
        sha=case["sha256"]
        require(sha in probes,"missing probe")
        p=probes[sha]
        require(p["id"]==case["id"] and p["cohort"]==case["cohort"],"probe identity changed")
        require(p["route"] in ("KISSAT","CADICAL"),"bad route")
        route_counts[p["route"]]+=1
        m={}
        for mode in benchmark.MODES:
            pairs=[idx[(sha,rep,mode)] for rep in range(benchmark.REPS)]
            require(len({r["status"] for r in pairs if r["status"]!="TIMEOUT"})<=1,"incompatible repeats")
            m[mode]=sum(r["par2"] for r in pairs)
        decisions=[idx[(sha,rep,"r135")] for rep in range(benchmark.REPS)]
        require(all(d["route"]==p["route"] for d in decisions),"non-deterministic selector route")
        require(all(d["detector_reason"]==p["reason"] for d in decisions),"probe/route reason mismatch")
        require(all(abs(d["binary_fraction"]-p["binary_fraction"])<1e-8 for d in decisions),"binary signal drift")
        require(all(abs(d["horn_fraction"]-p["horn_fraction"])<1e-8 for d in decisions),"Horn signal drift")
        require(all(d["observed_clauses"]==p["observed_clauses"] for d in decisions),"probe sample drift")
        require(all(d["prefix_limited"]==p["prefix_limited"] for d in decisions),"scan completeness drift")
        cost=sum(d["detector_s"] for d in decisions)
        cost_total+=cost
        selected_mode="cadical" if p["route"]=="CADICAL" else "kissat"
        other_mode="kissat" if selected_mode=="cadical" else "cadical"
        selected=m[selected_mode]
        alternative=m[other_mode]
        margin=max(ABS_MARGIN,REL_MARGIN*min(selected,alternative))
        if selected+margin<alternative:
            label="materially_correct_ex_post"
        elif alternative+margin<selected:
            label="materially_wrong_ex_post"
        else:
            label="indistinguishable_under_margin"
        regime_counts[label]+=1
        rec=dict(sha256=sha,source_id=case["id"],cohort=case["cohort"],
            route=p["route"],detector_reason=p["reason"],
            observed_clauses=p["observed_clauses"],
            prefix_limited=p["prefix_limited"],
            binary_fraction=p["binary_fraction"],horn_fraction=p["horn_fraction"],
            probe_s=p["probe_s"],measured_r135_probe_s=round(cost,6),
            kissat_par2=round(m["kissat"],6),cadical_par2=round(m["cadical"],6),
            r118_par2=round(m["r118"],6),r135_par2=round(m["r135"],6),
            route_selected_raw_par2=round(selected,6),
            route_alternative_raw_par2=round(alternative,6),
            route_ex_post_feedback=label,
            realized_gain_vs_kissat_s=round(m["kissat"]-m["r135"],6),
            retrospective_best_of_two_s=round(min(m["kissat"],m["cadical"]),6),
            hindsight_oracle_gap_s=round(m["r135"]-min(m["kissat"],m["cadical"]),6),
            cpu_shard=next((sh for sh in range(benchmark.SHARDS)
                 if idx[(sha,0,"kissat")]["shard"]==sh),None))
        require(rec["cpu_shard"] is not None,"runner ID missing")
        records.append(rec)
        by_sha[sha]=rec
    OUT.mkdir(parents=True,exist_ok=True)
    fields=list(records[0])
    with (OUT/"formula_feedback.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)
    pairs=sorted(records,key=lambda r:r["sha256"])
    base=sum(r["kissat_par2"] for r in pairs)
    actual=sum(r["r135_par2"] for r in pairs)
    ideal=sum(r["retrospective_best_of_two_s"] for r in pairs)
    by_cohort={}
    for co in sorted({r["cohort"] for r in records}):
        subset=[r for r in records if r["cohort"]==co]
        by_cohort[co]=dict(formulas=len(subset),
            kissat_par2=round(sum(r["kissat_par2"] for r in subset),6),
            r135_par2=round(sum(r["r135_par2"] for r in subset),6),
            route_counts=dict(collections.Counter(r["route"] for r in subset)),
            feedback_counts=dict(collections.Counter(r["route_ex_post_feedback"] for r in subset)))
    report=dict(
        protocol="DRNAS-R136-READONLY-STRUCTURAL-FEEDBACK-20261105-v1",
        phase="POSTHOC_R135_DIAGNOSTIC_DEVELOPMENT_NOT_NEW_HOLDOUT",
        r135_original_run=42061956160,source_manifest_sha256=manifest_sha,
        sha_covered=56,verified_shards=8,raw_paired_trials=448,repeats=2,
        frozen_runner_cpu_models=cpus,one_pinned_binary_set_verified=True,
        sat_models_and_sat_unsat_agreement_checked_by_r135_audit=True,
        independent_unsat_proofs=False,
        route_counts=dict(route_counts),classification_counts=dict(regime_counts),
        classification_margin=dict(abs_seconds=ABS_MARGIN,relative=REL_MARGIN),
        classifier_is_retrospective_not_deployable=True,
        detector_total_s=round(cost_total,6),
        kissat_par2=round(base,6),r135_par2=round(actual,6),
        actual_gain_pct=round(gain(base,actual),6),
        formula_bootstrap_95pct_gain_pct=bootstrap(pairs),
        hindsight_oracle_par2=round(ideal,6),
        hindsight_oracle_not_implementable=True,
        hindsight_gap_s=round(actual-ideal,6),
        by_cohort=by_cohort,
        reproducible_seed=SEED,n_bootstrap=NBOOT,
        training_or_threshold_tuning_performed=False,
        next_gate="Freeze new cost-sensitive signal policy using disjoint DEVELOPMENT, then test on fresh SHA-disjoint prospective set on matched runner",
        verdict="DIAGNOSTIC_ONLY_NO_PROMOTION_NO_CAUSAL_INFERENCE"
    )
    (OUT/"feedback.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("R136_FEEDBACK_AUDIT_PASS",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
