#!/usr/bin/env python3
"""Predeclared formula-level paired significance report for DRNAS MEMORY2.

One distinct source CNF is one independent comparison unit. Seeds/repetitions
are *within* that unit. These are exploratory bootstrap/permutation estimates,
not a guarantee of universality or proof of an algorithmic speedup.
"""
from __future__ import annotations
import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

ARMS=("X1_CORE","X1_M2_SHADOW","X1_M2_FROZEN","X1_M2_ONLINE")

def ci(samples):
    if not samples:return [None,None]
    a=sorted(samples)
    return [round(a[int(.025*(len(a)-1))],6),
            round(a[int(.975*(len(a)-1))],6)]

def gain(blocks):
    base=sum(v["base"] for v in blocks)
    cand=sum(v["candidate"] for v in blocks)
    return (base-cand)/base if base>0 else 0.0

def bootstrap(blocks,rng,count=3000):
    n=len(blocks);res=[]
    for _ in range(count):
        drawn=[blocks[rng.randrange(n)] for _ in range(n)]
        res.append(gain(drawn))
    return ci(res)

def family_bootstrap(blocks,rng,count=3000):
    families=defaultdict(list)
    for b in blocks:families[b["family"]].append(b)
    keys=sorted(families)
    res=[]
    for _ in range(count):
        sampled=[families[keys[rng.randrange(len(keys))]] for _ in keys]
        chosen=[b for fam in sampled for b in fam]
        res.append(gain(chosen))
    return ci(res)

def paired_signflip(blocks,rng,draws=4999):
    # One-sided paired sign randomization; assumes exchangeable null signs.
    ds=[b["base"]-b["candidate"] for b in blocks]
    obs=sum(ds)
    if not any(abs(d)>1e-15 for d in ds):return 1.0
    greater=0
    for _ in range(draws):
        simulated=sum((1 if rng.getrandbits(1) else -1)*d for d in ds)
        if simulated>=obs-1e-14:greater+=1
    return round((greater+1)/(draws+1),6)

def compute(rows,primary="X1_M2_FROZEN",target=0.05,seed=20261113):
    if primary not in ARMS or primary=="X1_CORE":raise ValueError("bad primary arm")
    seen={};families={};ids={}
    for row in rows:
        key=(row["sha256"],row["rep"],row["arm"])
        if key in seen:raise ValueError("duplicate paired trial "+str(key))
        if row["arm"] not in ARMS:raise ValueError("unexpected arm "+str(row["arm"]))
        if not (math.isfinite(float(row["PAR2"])) and row["PAR2"]>=0):
            raise ValueError("invalid PAR2 value")
        seen[key]=row
        family=row["family"]
        source=row["sha256"]
        if source in families and families[source]!=family:
            raise ValueError("source family changed")
        families[source]=family
        ids.setdefault(source,set()).add(row["rep"])
    by_arm={arm:{"rows":0,"verified":0,"PAR2_verified_e2e_s":0.0,
                 "SAT_verified":0,"UNSAT_verified":0} for arm in ARMS}
    for row in rows:
        d=by_arm[row["arm"]];d["rows"]+=1
        d["verified"]+=int(row["verified"])
        d["PAR2_verified_e2e_s"]+=float(row["PAR2"])
        d["SAT_verified"]+=int(row["verified"] and row["status"]=="SAT")
        d["UNSAT_verified"]+=int(row["verified"] and row["status"]=="UNSAT")
    for arm in ARMS:by_arm[arm]["PAR2_verified_e2e_s"]=round(by_arm[arm]["PAR2_verified_e2e_s"],6)
    if not ids:raise ValueError("empty holdout")
    expected_reps=set(next(iter(ids.values())))
    if not expected_reps:raise ValueError("no repetitions")
    blocks={arm:[] for arm in ARMS if arm!="X1_CORE"}
    for sha,reps in sorted(ids.items()):
        if reps!=expected_reps:raise ValueError("unbalanced seeds for source "+sha)
        family=families[sha]
        base=[seen[(sha,r,"X1_CORE")] for r in sorted(reps)]
        if not all(x["verified"] for x in base):
            pass # Unverified answers are already counted at PAR2=2*cap.
        for arm in blocks:
            others=[seen[(sha,r,arm)] for r in sorted(reps)]
            for x,y in zip(base,others):
                if x["verified"] and y["verified"] and x["status"]!=y["status"]:
                    raise ValueError("certified SAT/UNSAT disagreement")
            blocks[arm].append({"sha256":sha,"family":family,
                "base":statistics.mean(x["PAR2"] for x in base),
                "candidate":statistics.mean(x["PAR2"] for x in others)})
    n=len(ids)
    results={}
    for i,(arm,paired) in enumerate(blocks.items()):
        rng=random.Random(seed+101*i)
        observed=gain(paired)
        individual_ci=bootstrap(paired,rng)
        across_family_ci=family_bootstrap(paired,rng)
        one_sided_p=paired_signflip(paired,rng)
        diffs=[b["base"]-b["candidate"] for b in paired]
        sd=statistics.stdev(diffs) if n>1 else 0.0
        base_mean=statistics.mean(b["base"] for b in paired)
        needed=math.ceil((1.959964+0.841621)**2*(sd/(target*base_mean))**2) if base_mean>0 else None
        family_sums=defaultdict(list)
        for b in paired:family_sums[b["family"]].append(b)
        family_effects={k:{"sources":len(v),"relative_PAR2_reduction":round(gain(v),6)}
                       for k,v in sorted(family_sums.items())}
        extra_solved=by_arm[arm]["verified"]-by_arm["X1_CORE"]["verified"]
        # Formal claim requires both independent formula and structural-family
        # uncertainty to clear the PREDEFINED +5% target.
        defendable=(n>=200 and len(family_sums)>=6 and extra_solved>=0
                    and individual_ci[0]>target and across_family_ci[0]>target)
        results[arm]={
            "relative_PAR2_reduction":round(observed,6),
            "formula_cluster_bootstrap_95pct":individual_ci,
            "family_cluster_bootstrap_95pct":across_family_ci,
            "paired_one_sided_signflip_p_exploratory":one_sided_p,
            "relative_effect_target":target,
            "observed_pair_difference_sd_s":round(sd,9),
            "approx_n_for_80pct_power_at_target_effect":needed,
            "family_effects":family_effects,
            "verified_solved_delta":extra_solved,
            "passes_predefined_5pct_criterion":defendable,
        }
    return {
        "stat_method":"paired formula-level mean PAR2, bootstrap formula/family, exploratory signflip",
        "primary_comparison":f"{primary} vs X1_CORE",
        "primary_passed":results[primary]["passes_predefined_5pct_criterion"],
        "confidence_level":0.95,
        "bootstrap_samples":3000,
        "one_sided_signflip_draws":4999,
        "n_distinct_test_formulas":n,
        "n_distinct_families":len(set(families.values())),
        "n_repeats_per_formula":len(expected_reps),
        "N_trials_is_not_N_independent_samples":True,
        "limits":"Synthetic families are a fixed non-random assortment; bootstrap relies on exchangeability within that pool and does not establish general performance on SAT Competition CNFs. Repeated runs do not increase distinct N. Tiny process timings may be noisy.",
        "arms":by_arm,
        "comparisons":results,
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--trials",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--primary",choices=ARMS[1:],default="X1_M2_FROZEN")
    args=parser.parse_args()
    rows=[json.loads(x) for x in args.trials.read_text().splitlines() if x.strip()]
    report=compute(rows,args.primary)
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("X1_M2_SIGNIFICANCE "+json.dumps(report,sort_keys=True,separators=(",",":")),flush=True)
if __name__=="__main__":main()
