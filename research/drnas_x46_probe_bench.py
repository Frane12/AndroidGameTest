#!/usr/bin/env python3
"""X4.6: matched-state and cost-inclusive, proof-safe short-probe A/B test.

Pairs CORE/FLIP/X46-SHADOW/X46-8/X46-32/X46-128 use the same original CNF
and first K decision prefix (verified with X45 pre-state digest). The X46
controller chooses polarity from *two limited continuation clones*.
Both probe costs count toward X46 end-to-end wall time. No oracle labels,
CNF source family or post-decision final results enter the runtime selector.
An offline diagnostic compares the recommended flip with the verified
full-continuation counterfactual, but NEVER feeds this answer to X46.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import tempfile
import time

import drnas_x45_matched_branches as X45

ARMS=("CORE","FLIP","SHADOW_8","X46_8","X46_32","X46_128")
LEARNED_ARM="X46_LEARNED_8"
X47_ARM="X47_RISKGATE_8"
CHECKPOINTS=(1,2,4,8)

def emit(tag,obj):
    print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def run(binary,cnf,case,k,arm,cap,probe_ms,model_file=None,guard_file=None):
    cmd=[str(binary),str(cnf),"--mode","core","--time",str(cap),"--branch-at",str(k),"--stats"]
    if arm=="FLIP":cmd.append("--flip-branch")
    elif arm.startswith("X46_") or arm=="SHADOW_8":
        n=8 if arm in ("SHADOW_8",LEARNED_ARM,X47_ARM) else int(arm.split("_")[1])
        cmd+=["--x46-conflicts",str(n),"--x46-probe-ms",str(probe_ms)]
        if arm=="SHADOW_8":cmd.append("--x46-shadow")
        if arm in (LEARNED_ARM,X47_ARM):
            if model_file is None:raise ValueError("learned arm requires model")
            cmd+=["--x46-model",str(model_file)]
            if arm==X47_ARM:
                if guard_file is None:raise ValueError("X47 arm requires guard")
                cmd+=["--x47-guard",str(guard_file)]
    started=time.monotonic()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+1)
        wall=time.monotonic()-started
    except subprocess.TimeoutExpired:
        raise AssertionError("X46 native hard subprocess timeout; investigate")
    if p.returncode not in (0,10,20):
        raise RuntimeError(f"X46 native error {p.returncode}: {p.stderr[-1500:]}")
    lines=p.stderr.splitlines()
    a=[json.loads(l[len("X41_STATS "):]) for l in lines if l.startswith("X41_STATS ")]
    b=[json.loads(l[len("X45_COMPARE "):]) for l in lines if l.startswith("X45_COMPARE ")]
    c=[json.loads(l[len("X46_PROBE "):]) for l in lines if l.startswith("X46_PROBE ")]
    if len(a)!=1 or len(b)!=1 or len(c)!=(0 if arm in ("CORE","FLIP") else 1):
        raise AssertionError("native comparison/probe stats not present: "+p.stderr[-1400:])
    stats=a[0];pre=b[0];probe=c[0] if c else None
    status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}[p.returncode]
    oracle=case["oracle"].startswith("UNSAT")
    # All SAT witnesses independently checked on original CNF; UNSAT accepted
    # only for cases independently proved by tiny exhaustive enumeration.
    checked_at=time.monotonic()
    valid=(status=="SAT" and not oracle and X45.check_witness(case["n"],case["clauses"],p.stdout)) or (
        status=="UNSAT" and oracle)
    check_wall=time.monotonic()-checked_at
    if status=="SAT" and not valid:raise AssertionError("invalid original-CNF SAT assignment")
    if (status=="UNSAT" and not oracle) or (status=="SAT" and oracle):
        raise AssertionError("false SAT/UNSAT native outcome")
    if pre["reached"] and (pre["decision_index"]!=k or not pre["baseline_literal"]):
        raise AssertionError("invalid checkpoint metadata")
    if arm=="SHADOW_8" and pre["reached"] and pre["actual_literal"]!=pre["baseline_literal"]:
        raise AssertionError("shadow modified a real decision")
    if probe is not None:
        if probe["triggered"]:
            if arm in (LEARNED_ARM,X47_ARM) and not probe.get("learned_model",False):
                raise AssertionError("frozen X46 model failed to load into active controller")
            if arm==X47_ARM and not probe.get("x47_enabled",False):
                raise AssertionError("frozen X47 guard did not load")
            if probe["pre_state_digest"]!=pre["pre_state_digest"]:
                raise AssertionError("cloned pre-state digest differs from controller")
            if (arm=="SHADOW_8" and not probe["shadow"]) or (arm!="SHADOW_8" and probe["shadow"]):
                raise AssertionError("probe shadow mode wrong")
            if probe["probe_pair_wall_ms"]<0:
                raise AssertionError("negative probe time")
            if arm.startswith("X46_") and pre["reached"]:
                desired=(-pre["baseline_literal"] if probe["recommend_flip"] else pre["baseline_literal"])
                if pre["actual_literal"]!=desired:raise AssertionError("probe recommendation not applied")
        elif pre["reached"] and not probe["skipped"]:
            raise AssertionError("probe neither triggered nor boundedly skipped")
    e2e=wall+check_wall
    return {"arm":arm,"status":status,"verified":valid,
        "PAR2":round(e2e if valid and e2e<=cap else 2*cap,7),
        "solve_wall_s":round(wall,7),
        "check_s":round(check_wall,7),
        "reached":pre["reached"],"pre":pre,"probe":probe,
        "decisions":stats["decisions"],"conflicts":stats["conflicts"],
        "continuation_decisions":stats["decisions"]-k+1 if pre["reached"] else None,
        "continuation_conflicts":stats["conflicts"]-pre["prefix_conflicts"] if pre["reached"] else None,
        "continuation_wall_s":max(0,stats["elapsed_s"]-pre["prefix_elapsed_s"]) if pre["reached"] else None}

def aggregate(rows,arm):
    subset=[r for r in rows if r["arm"]==arm]
    if not subset:return {}
    return {"trials":len(subset),"verified":sum(r["verified"] for r in subset),
        "SAT_verified":sum(r["verified"] and r["status"]=="SAT" for r in subset),
        "UNSAT_verified":sum(r["verified"] and r["status"]=="UNSAT" for r in subset),
        "PAR2_verified_e2e_s":round(sum(r["PAR2"] for r in subset),6),
        "solver_wall_s":round(sum(r["solve_wall_s"] for r in subset),6),
        "continuation_decisions":sum(r["continuation_decisions"] for r in subset),
        "continuation_conflicts":sum(r["continuation_conflicts"] for r in subset),
        "probe_wall_s":round(sum(r.get("probe_wall_ms",0) for r in subset)/1000,6),
        "recommended_flips":sum(r.get("recommended_flip",False) for r in subset),
        "actual_flips":sum(r.get("actual_flip",False) for r in subset),
        "probe_skipped":sum(r.get("probe_skipped",False) for r in subset)}

def bootstrap(rows,arm,draws=2200):
    mapping=defaultdict(lambda:defaultdict(list))
    for x in rows:mapping[x["sha256"]][x["arm"]].append(x)
    sources=sorted(mapping)
    rng=random.Random(461911)
    gain=[]
    for _ in range(draws):
        ids=[sources[rng.randrange(len(sources))] for _ in sources]
        b=sum(x["PAR2"] for s in ids for x in mapping[s]["CORE"])
        t=sum(x["PAR2"] for s in ids for x in mapping[s][arm])
        if b:gain.append((b-t)/b)
    gain.sort()
    return {"relative_PAR2_reduction":round((sum(x["PAR2"] for x in rows if x["arm"]=="CORE") -
                sum(x["PAR2"] for x in rows if x["arm"]==arm)) /
                max(1e-12,sum(x["PAR2"] for x in rows if x["arm"]=="CORE")),6),
        "formula_cluster_95pct":[round(gain[int(.025*(draws-1))],6),
                                  round(gain[int(.975*(draws-1))],6)],
        "unique_original_sources":len(sources)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",type=Path,default=Path("build/drnas-x46"))
    p.add_argument("--out",type=Path,default=Path("x46_results"))
    p.add_argument("--per-family",type=int,default=12)
    p.add_argument("--repeats",type=int,default=3)
    p.add_argument("--cap",type=float,default=.8)
    p.add_argument("--probe-ms",type=float,default=1.5)
    p.add_argument("--index-offset",type=int,default=400000)
    p.add_argument("--model-file",type=Path,default=None)
    p.add_argument("--guard-file",type=Path,default=None)
    args=p.parse_args()
    if args.per_family<3 or args.repeats<2 or args.cap<.25 or args.index_offset<400000:
        raise ValueError("X46 input too small, reused source or invalid cap")
    args.out.mkdir(parents=True,exist_ok=False)
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binary=args.binary.resolve()
    model_file=args.model_file.resolve() if args.model_file else None
    if model_file is not None and not model_file.exists():raise ValueError("frozen model absent")
    model_sha=hashlib.sha256(model_file.read_bytes()).hexdigest() if model_file else None
    guard_file=args.guard_file.resolve() if args.guard_file else None
    if guard_file is not None and (model_file is None or not guard_file.exists()):
        raise ValueError("X47 guard requires existing frozen learned model")
    guard_sha=hashlib.sha256(guard_file.read_bytes()).hexdigest() if guard_file else None
    used_arms=ARMS+(LEARNED_ARM,) if model_file else ARMS
    if guard_file:used_arms+=(X47_ARM,)
    cases=[X45.make_case(fam,args.index_offset+i) for fam in X45.FAMILIES
           for i in range(args.per_family)]
    if len({x["sha256"] for x in cases})!=len(cases):
        raise AssertionError("duplicate original CNF source hash")
    for case in cases:
        if case["oracle"].startswith("UNSAT") and X45.exhaustive_sat(case["n"],case["clauses"]):
            raise AssertionError("constructed UNSAT has an original-CNF model")
    manifest={"sources":[{k:case[k] for k in ("family","sha256","id","n","oracle")}
                         for case in cases],
       "actual_distinct_originals":len(cases),
       "no_prior_X45_generator_indices":True,
       "source_generation_index_offset":args.index_offset,
       "repeats":args.repeats,"checkpoints":CHECKPOINTS,"arms":used_arms,
       "frozen_learned_model_sha256":model_sha,
       "frozen_x47_risk_guard_sha256":guard_sha,
       "per_probe_ms_limit":args.probe_ms,"cap_s":args.cap,
       "no_oracle_knowledge_in_runtime_controller":True,
       "SAT_independent_original_CNF_witness":True,
       "UNSAT_independently_exhaustive_small":True,
       "end_to_end_includes_probe_and_checker_cost":True,
       "probe_simulation_uses_native_solver_copy":True,
       "decision_checkpoint_prefix_hash_required":True}
    (args.out/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    rows=[];not_reached=0;probes_triggered=0;probe_skipped=0;recommended_correct=Counter()
    winning_counts=Counter()
    with tempfile.TemporaryDirectory(prefix="x46-probe-") as d:
        cnf=Path(d)/"original.cnf"
        for i,case in enumerate(cases):
            cnf.write_text(case["source"])
            for k in CHECKPOINTS:
                for rep in range(args.repeats):
                    # Rotate arm order to reduce systematic thermal/timing bias.
                    arms=list(used_arms)
                    offset=(i+k+rep)%len(arms)
                    arms=arms[offset:]+arms[:offset]
                    one={}
                    for arm in arms:
                        one[arm]=run(binary,cnf,case,k,arm,args.cap,args.probe_ms,model_file,guard_file)
                    reached={one[a]["reached"] for a in used_arms}
                    if len(reached)!=1:raise AssertionError("different checkpoint reachability")
                    if not one["CORE"]["reached"]:
                        not_reached+=1
                        continue
                    original=one["CORE"];flipped=one["FLIP"]
                    pre=original["pre"]
                    for arm,r in one.items():
                        p=r["pre"]
                        for field in ("pre_state_digest","baseline_literal",
                                      "prefix_conflicts","prefix_learnt","prefix_propagations",
                                      "decision_index"):
                            if p[field]!=pre[field]:
                                raise AssertionError(f"unmatched live prefix {field}: {case['sha256']} K={k} arm={arm}")
                        if not r["verified"]:
                            raise AssertionError("unverified matched run")
                        if r["status"]!=original["status"]:
                            raise AssertionError("different SAT/UNSAT result from same original CNF")
                    if flipped["pre"]["actual_literal"]!=-pre["baseline_literal"]:
                        raise AssertionError("X45 offline polarity was not inverted")
                    if (one["SHADOW_8"]["continuation_decisions"]!=original["continuation_decisions"] or
                        one["SHADOW_8"]["continuation_conflicts"]!=original["continuation_conflicts"]):
                        raise AssertionError("X46 shadow clone changed parent decision search")
                    if (one["SHADOW_8"]["pre"]["actual_literal"]!=pre["baseline_literal"]):
                        raise AssertionError("shadow changed selected literal")
                    diff=flipped["continuation_conflicts"]-original["continuation_conflicts"]
                    label="flip_cheaper" if diff<0 else "baseline_cheaper" if diff>0 else "equal_conflicts"
                    winning_counts[label]+=1
                    for arm in used_arms:
                        r=one[arm]
                        p=r["probe"]
                        probe_ms=p["probe_pair_wall_ms"] if p and p["triggered"] else 0
                        if p and p["triggered"]:probes_triggered+=1
                        if p and p["skipped"]:probe_skipped+=1
                        rec=(p["recommend_flip"] if p else False)
                        actual_flip=(r["pre"]["actual_literal"]==-pre["baseline_literal"])
                        if (arm.startswith("X46_") or arm==X47_ARM) and label!="equal_conflicts":
                            recommended_correct[arm+"|correct"]+=int(rec==(label=="flip_cheaper"))
                            recommended_correct[arm+"|seen"]+=1
                        row={"sha256":case["sha256"],"family":case["family"],
                             "source_id":case["id"],"checkpoint":k,"rep":rep,"arm":arm,
                             "pre_hash":pre["pre_state_digest"],
                             "status":r["status"],"verified":r["verified"],
                             "PAR2":r["PAR2"],"solve_wall_s":r["solve_wall_s"],
                             "continuation_decisions":r["continuation_decisions"],
                             "continuation_conflicts":r["continuation_conflicts"],
                             "probe_wall_ms":round(probe_ms,7),
                             "probe_triggered":bool(p and p["triggered"]),
                             "probe_skipped":bool(p and p["skipped"]),
                             "x47_enabled":bool(p and p.get("x47_enabled",False)),
                             "x47_preprobe_skipped":bool(p and p.get("x47_preprobe_skipped",False)),
                             "x47_rejected_after_probe":bool(p and p.get("x47_rejected_after_probe",False)),
                             "x47_expected_net_conflicts":p.get("x47_expected_net_conflicts") if p else None,
                             "recommended_flip":bool(rec),"actual_flip":actual_flip,
                             "learned_model":bool(p and p.get("learned_model",False)),
                             "flip_probability":p.get("predicted_flip_probability") if p else None,
                             "counterfactual_label":label,
                             "probe_base":p["original"] if p and p["triggered"] else None,
                             "probe_alt":p["opposite"] if p and p["triggered"] else None}
                        rows.append(row)
            if (i+1)%12==0:
                with (args.out/"trials.jsonl").open("w") as out:
                    for row in rows:out.write(json.dumps(row,sort_keys=True)+"\n")
                emit("X46_PROGRESS",{"done_originals":i+1,"total_originals":len(cases),
                    "matched_decision_pairs":len(rows)//len(used_arms),
                    "not_reached":not_reached,
                    "short_probes_triggered":probes_triggered})
    with (args.out/"trials.jsonl").open("w") as out:
        for row in rows:out.write(json.dumps(row,sort_keys=True)+"\n")
    if model_file and hashlib.sha256(model_file.read_bytes()).hexdigest()!=model_sha:
        raise AssertionError("holdout rewrote frozen X46 model")
    if guard_file and hashlib.sha256(guard_file.read_bytes()).hexdigest()!=guard_sha:
        raise AssertionError("holdout rewrote frozen X47 risk guard")
    totals={arm:aggregate(rows,arm) for arm in used_arms}
    tests={arm:bootstrap(rows,arm) for arm in used_arms[1:]}
    family={fam:{arm:aggregate([x for x in rows if x["family"]==fam],arm) for arm in used_arms}
             for fam in X45.FAMILIES}
    report={"protocol":"X46 costed two-clone online short-polarity probes at one matched checkpoint",
        "cohort":"new SHA-distinct original synthetics",
        "distinct_original_sources":len(cases),"source_family_count":len(X45.FAMILIES),
        "attempted_checkpoint_pairs":len(cases)*len(CHECKPOINTS)*args.repeats,
        "matched_checkpoint_pairs":len(rows)//len(used_arms),
        "checkpoint_not_reached_pairs":not_reached,
        "all_arms_matching_pre_state":True,
        "all_continuations_verified":True,
        "training":False,"probe_policy_fixed_pre_holdout":True,
        "frozen_learned_cost_model":model_sha,
        "frozen_x47_risk_guard":guard_sha,
        "default_branch_unchanged":True,
        "full_counterfactual_labels":dict(winning_counts),
        "probe_vs_full_continuation":{arm:{
            "correct":recommended_correct[arm+"|correct"],
            "evaluable":recommended_correct[arm+"|seen"],
            "accuracy":round(recommended_correct[arm+"|correct"]/
                      recommended_correct[arm+"|seen"],5)
                      if recommended_correct[arm+"|seen"] else None}
            for arm in (("X46_8","X46_32","X46_128",LEARNED_ARM,X47_ARM) if guard_file
                else ("X46_8","X46_32","X46_128",LEARNED_ARM) if model_file
                else ("X46_8","X46_32","X46_128"))},
        "by_arm":totals,"comparisons_vs_CORE":tests,
        "by_family":family,"all_probe_triggered_arm_runs":probes_triggered,
        "probe_skips":probe_skipped,
        "caveats":[
          "Short probe cost includes cloning and selected bounded C++ continuation; end-to-end PAR2 includes independent SAT witness checks.",
          "Main solver never imports learned clauses or proofs from clones.",
          "The optional learned arm loads a frozen predictor from a separate verified training cohort; fixed arms are heuristics.",
          "UNSAT only independently checked for <=18 vars by exhaustive enumeration.",
          "Original CNFs, not repeated probes, are independent statistical units.",
          "This is synthetic, not blind official SAT Competition performance."
        ]}
    (args.out/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    emit("X46_FINAL",report)

if __name__=="__main__":main()
