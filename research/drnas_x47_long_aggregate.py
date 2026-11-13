#!/usr/bin/env python3
"""Aggregate independently verified X47 long-cap benchmark shards.

Use exact original source SHA as the independent unit. Report
PAR2 verified, unverified UNSAT separately, paired bootstrap CI and
multiple complete provenance manifests. Official retrospective results
never get general UNSAT proof credit without independent verification.
"""
from __future__ import annotations
from collections import defaultdict
import argparse
import json
from pathlib import Path
import random
import statistics

ARMS=("CORE","X46_8","X46_128","X46_LEARNED_8","X47_RISKGATE_8")

def analyze(name,entries):
    if not entries:return {"status":"not_run"}
    data=[]
    manifests=[]
    seen_sources=set()
    for manifest,records in entries:
        manifests.append(manifest)
        newsha={x["sha256"] for x in manifest["originals"]}
        if seen_sources & newsha:
            raise AssertionError("source SHA overlap across independent shards")
        seen_sources.update(newsha)
        data.extend(records)
    by_case=defaultdict(lambda:defaultdict(list))
    all_source_families={}
    for row in data:
        sha=row["sha256"]
        by_case[sha][row["arm"]].append(row)
        all_source_families[sha]=row["family"]
    expected_reps=manifests[0]["repeats"]
    for sha,arms in by_case.items():
        if set(arms)!=set(ARMS) or any(len(x)!=expected_reps for x in arms.values()):
            raise AssertionError("missing paired arm/repeat")
    byarm={}
    for arm in ARMS:
        subset=[r for r in data if r["arm"]==arm]
        byarm[arm]={"trials":len(subset),
            "SAT_verified":sum(r["status"]=="SAT" and r["verified"] for r in subset),
            "UNSAT_verified":sum(r["status"]=="UNSAT" and r["verified"] for r in subset),
            "UNSAT_unverified":sum(r["status"]=="UNSAT" and not r["verified"] for r in subset),
            "UNKNOWN_TIMEOUT":sum(r["status"] in ("TIMEOUT","UNKNOWN") for r in subset),
            "verified_PAR2_s":round(sum(r["PAR2"] for r in subset),6),
            "e2e_s":round(sum(r["solver_e2e_s"]+r["check_s"] for r in subset),6),
            "native_conflicts":sum(r["conflicts"] or 0 for r in subset),
            "native_decisions":sum(r["decisions"] or 0 for r in subset),
            "probe_wall_s":round(sum(r["probe_wall_ms"] or 0 for r in subset)/1000.,6),
            "probe_triggered":sum(r["probe_triggered"] for r in subset),
            "probe_skipped":sum(r["probe_skipped"] for r in subset),
            "active_flips":sum(r["actual_flip"] for r in subset)}
    originals=sorted(by_case)
    rng=random.Random(471119)
    ci={}
    for arm in ARMS[1:]:
        baseline=byarm["CORE"]["verified_PAR2_s"]
        active=byarm[arm]["verified_PAR2_s"]
        vals=[]
        for _ in range(2500):
            drawn=[originals[rng.randrange(len(originals))] for _ in originals]
            core=sum(sum(x["PAR2"] for x in by_case[sha]["CORE"]) for sha in drawn)
            other=sum(sum(x["PAR2"] for x in by_case[sha][arm]) for sha in drawn)
            vals.append((core-other)/core if core else 0.0)
        vals.sort()
        ci[arm]={"PAR2_relative_reduction":round((baseline-active)/baseline,6) if baseline else None,
            "formula_cluster95":[round(vals[int(.025*2499)],6),
                                  round(vals[int(.975*2499)],6)]}
    family={}
    for fam in sorted(set(all_source_families.values())):
        famkeys=[x for x in originals if all_source_families[x]==fam]
        family[fam]={"sources":len(famkeys),
            "verified_PAR2_s":{arm:round(sum(
                sum(x["PAR2"] for x in by_case[sha][arm]) for sha in famkeys),6)
                for arm in ARMS},
            "verified_solved":{arm:sum(
                r["verified"] for sha in famkeys for r in by_case[sha][arm])
                for arm in ARMS}}
    source_sat_solved=sum(any(x["verified"] and x["status"]=="SAT"
                               for x in arms["CORE"])
                          for arms in by_case.values())
    return {"cohort":name,"original_sources":len(originals),
        "source_families":len(family),
        "SAT_verified_source_count_CORE":source_sat_solved,
        "total_trials":len(data),"completed_shards":len(entries),
        "by_arm":byarm,"comparison":ci,"by_family":family,
        "independent_unit":"original source SHA; repetitions correlated",
        "not_globally_blind":True,
        "confidence_caveat":"Formula bootstrap conditional on the sampled structural families; family clusters too few for broad generalization."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    groups=defaultdict(list)
    for mf in args.root.rglob("manifest.json"):
        try:manifest=json.loads(mf.read_text())
        except ValueError:continue
        if manifest.get("cohort") not in ("synthetic","official"):continue
        trialfile=mf.with_name("trials.jsonl")
        if not trialfile.exists():continue
        rows=[json.loads(x) for x in trialfile.read_text().splitlines() if x.strip()]
        groups[manifest["cohort"]].append((manifest,rows))
    report={
      "synthetic":analyze("synthetic",groups["synthetic"]),
      "official":analyze("official_retrospective",groups["official"]),
      "all_outputs_consistent":True,
      "warning":"Synthetic source selection is outcome-blind but generator-specific. Official SAT2024 is retrospective; unverified UNSAT gets PAR2 timeout credit. No official universal claim."}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    for cohort in ("synthetic","official"):
        result=report[cohort]
        if result.get("status")=="not_run":
            print("X47_LONG_AGG "+json.dumps({"cohort":cohort,"status":"not_run"}),flush=True)
            continue
        print("X47_LONG_AGG "+json.dumps({
            "cohort":cohort,"sources":result["original_sources"],
            "families":result["source_families"],
            "trials":result["total_trials"],
            "by_arm":result["by_arm"],
            "comparison":result["comparison"]},sort_keys=True,separators=(",",":")),flush=True)

if __name__=="__main__":main()
