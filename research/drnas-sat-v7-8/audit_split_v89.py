#!/usr/bin/env python3
"""Train-only rule fitting, then blind 100-CNF test audit for DRNAS v8.9.

Training selects from a bounded, deterministic set of single-feature threshold
rules. The test script NEVER alters that choice. All speedups use PAR-2 and all
cases, including timeouts.
"""
import csv
import hashlib
import json
import math
import random
import statistics
import sys
from collections import Counter,defaultdict
from pathlib import Path
from split_v89 import VERSION,FAMILIES,FEATURES,BASE_MODES,CAP,REPEATS,decision

STAGE=sys.argv[1] if len(sys.argv)>1 else "train"
ROOT=Path(sys.argv[2]) if len(sys.argv)>2 else Path("combined-v89-"+STAGE)
assert STAGE in ("train","test")
MODES=BASE_MODES+(("trained_selector",) if STAGE=="test" else ())

cases=[];rows=[]
for shard in range(5):
    folder=ROOT/("shard-%d"%shard)
    m=json.loads((folder/"manifest.json").read_text())
    assert m["version"]==VERSION and m["stage"]==STAGE and m["shard"]==shard
    assert m["cap_s"]==CAP and m["repeats"]==REPEATS
    assert tuple(m["modes"])==MODES and len(m["cases"])==20
    cases+=m["cases"]
    with (folder/"raw.csv").open(newline="") as f:
        rows+=list(csv.DictReader(f))
assert len(cases)==100 and len({c["sha256"] for c in cases})==100
assert len(rows)==100*REPEATS*len(MODES)
assert len({(r["sha256"],r["mode"],r["repeat"]) for r in rows})==len(rows)
assert all(sum(c["family"]==f for c in cases)==20 for f in FAMILIES)
assert {c["sha256"] for c in cases}=={r["sha256"] for r in rows}
groups=defaultdict(list)
for r in rows:
    assert r["mode"] in MODES
    assert r["status"] in ("SAT","UNSAT","TIMEOUT","ERROR")
    assert r["split"]==STAGE
    groups[(r["sha256"],r["mode"])].append(r)

def med(case,mode):
    rr=groups[(case["sha256"],mode)]
    assert len(rr)==REPEATS and {int(r["repeat"]) for r in rr}==set(range(REPEATS))
    if any(r["status"]=="ERROR" for r in rr):
        raise RuntimeError("solver error: "+case["sha256"])
    return statistics.median(
        float(r["wall_s"]) if r["status"] in ("SAT","UNSAT") else 2*CAP
        for r in rr)

case_rows=[]; totals={m:0.0 for m in MODES}
for case in cases:
    statuses={r["status"] for r in rows if r["sha256"]==case["sha256"]
              and r["status"] in ("SAT","UNSAT")}
    if len(statuses)>1:
        raise RuntimeError("contradictory SAT/UNSAT for "+case["sha256"])
    if case["known_truth"].startswith("UNSAT") and "SAT" in statuses:
        raise RuntimeError("pigeonhole contradicted "+case["sha256"])
    cost={m:med(case,m) for m in MODES}
    for mode in MODES:totals[mode]+=cost[mode]
    case_rows.append(dict(name=Path(case["cnf"]).stem,family=case["family"],
                          sha256=case["sha256"],features=case["features"],
                          cost=cost))

def candidate_score(policy,feature=None,threshold=None,direction=None):
    model=dict(policy=policy,feature=feature,threshold=threshold,direction=direction)
    select=[decision(model,r["features"]) for r in case_rows]
    value=sum(r["cost"][choice] for r,choice in zip(case_rows,select))
    selected=[r for r,choice in zip(case_rows,select) if choice=="orig_v76"]
    by_family={}
    for fam in FAMILIES:
        frows=[r for r in case_rows if r["family"]==fam]
        fchoices=[choice for r,choice in zip(case_rows,select) if r["family"]==fam]
        by_family[fam]=sum(r["cost"][choice] for r,choice in zip(frows,fchoices))
    return dict(policy=policy,feature=feature,threshold=threshold,
                direction=direction,total=value,
                guided=len(selected),
                guided_families=len({r["family"] for r in selected}),
                family=by_family)

def fit():
    # Conservative rule search: never reuse test labels, require measurable
    # gain in at least two families; family metadata never enters decision().
    plain=candidate_score("always_plain")
    guided=candidate_score("always_guided")
    candidates=[plain,guided]
    for feature in FEATURES:
        values=sorted({float(r["features"][feature]) for r in case_rows})
        if len(values)<4:continue
        quantiles=sorted({values[round((len(values)-1)*q)]
                          for q in (0.10,0.25,0.40,0.50,0.60,0.75,0.90)})
        for threshold in quantiles:
            for direction in ("le","gt"):
                p=candidate_score("threshold",feature,threshold,direction)
                # An all/none policy is not a structural selector.
                if 10<=p["guided"]<=90 and p["guided_families"]>=2:
                    candidates.append(p)
    baseline=min(plain["total"],guided["total"])
    best=min(candidates,key=lambda c:(c["total"],c["policy"]!="always_plain"))
    # Do not learn a fragile gate from noise or a single easy family.
    benefit_families=sum(
        best["family"][f] <= plain["family"][f]-0.02
        for f in FAMILIES)
    if best["policy"]=="threshold" and (
        best["total"]>0.97*baseline or benefit_families<2):
        best=plain if plain["total"]<=guided["total"] else guided
    elif best["policy"]=="always_guided" and guided["total"]>0.97*plain["total"]:
        best=plain
    model={
        "version":VERSION,"source_split":"train",
        "policy":best["policy"],"feature":best["feature"],
        "threshold":best["threshold"],"direction":best["direction"],
        "train_par2":best["total"],"train_plain_par2":plain["total"],
        "train_guided_par2":guided["total"],
        "train_family_count":len(FAMILIES),
        "train_case_count":len(case_rows),
        "note":"Train-selected exploratory rule, not an independently verified gain",
    }
    (ROOT/"model.json").write_text(json.dumps(model,indent=2,sort_keys=True))
    (ROOT/"train_hashes.json").write_text(json.dumps(
        sorted(r["sha256"] for r in case_rows),indent=2))
    return model,sorted(candidates,key=lambda c:c["total"])[:10]

def bootstrap_ci(a,b):
    """Paired resampling of formula-level PAR2 costs, not repeated runs."""
    rnd=random.Random(810399)
    arr=[(r["cost"][a],r["cost"][b]) for r in case_rows]
    values=[]
    for _ in range(2000):
        subs=[arr[rnd.randrange(len(arr))] for _ in range(len(arr))]
        numer=sum(x for x,y in subs);denom=sum(y for x,y in subs)
        values.append((numer/denom-1.0)*100 if denom else 0)
    values.sort()
    return (round(values[50],3),round(values[1949],3))

lines=[
    "# DRNAS SAT V8.9 — "+STAGE.upper()+" 100 formulas, 20 per family",
    "",
    "Exactly 100 unique CNFs, 3 repeats per mode; all timeouts included at PAR-2=6s.",
    "Pinned-core GitHub runners; percentages descriptive, not world-record claims.",
    "SAT models checked by solver; arbitrary UNSAT proofs not independently checked.",
    "The 100-CNF holdout never feeds rule selection.","",
]
if STAGE=="train":
    model,best=fit()
    lines += [
        "## Frozen rule trained on TRAIN ONLY","",
        "Policy: "+str(model["policy"]),
        "Feature: "+str(model["feature"]),
        "Threshold: "+str(model["threshold"]),
        "Direction: "+str(model["direction"]),
        "Top candidate rules (exploratory):",
        "","| Rule | Feature | Cutoff | Direction | Sum PAR-2 |",
        "|---|---|---:|---|---:|",
    ]
    for p in best:
        lines.append("| %s | %s | %s | %s | %.5fs |"%(
            p["policy"],p["feature"],p["threshold"],p["direction"],p["total"]))
else:
    model=json.loads(Path("trained-model/model.json").read_text())
    assert model["version"]==VERSION and model["source_split"]=="train"
    train_hashes=set(json.loads(Path("trained-model/train_hashes.json").read_text()))
    assert len(train_hashes)==100
    assert not(train_hashes & {r["sha256"] for r in case_rows}), "DATA LEAKAGE!"
    digest=hashlib.sha256(json.dumps(model,sort_keys=True).encode()).hexdigest()
    for shard in range(5):
        m=json.loads((ROOT/("shard-%d"%shard)/"manifest.json").read_text())
        assert m.get("model_sha256")==digest, "mixed model across test shards!"
    # Ensure actual test execution followed the frozen feature rule.
    for r in rows:
        if r["mode"]!="trained_selector":continue
        case=next(c for c in cases if c["sha256"]==r["sha256"])
        assert r["underlying_mode"]==decision(model,case["features"])
    ci=bootstrap_ci("ca_plain","trained_selector")
    ci_plain=bootstrap_ci("orig_v76_plain","trained_selector")
    lines += ["## Frozen model evaluated exactly once on unseen TEST",
              "", "Model: "+json.dumps(model,sort_keys=True),
              "Paired bootstrap 95% interval, CaDiCaL/switch ratio minus one (percent): %s"%str(ci),
              "Paired bootstrap 95% interval, V7.6 plain/switch minus one (percent): %s"%str(ci_plain),
              "Training hashes/test hashes overlap: 0.",
              "Selector feature computation wall-time is included in the selected-mode costs.",""]
lines += ["## Aggregate PAR-2: lower is better","",
          "| Mode | Sum of formula medians (s) |",
          "|---|---:|"]
for m in MODES:lines.append("| %s | %.5f |"%(m,totals[m]))
lines += ["","## Family accounting","",
          "| Family | Cases | CaDiCaL | V7.6 guided | V7.6 plain | "+
          ("Trained selector |" if STAGE=="test" else ""),
          "|---|---:|---:|---:|---:|"+("---:|" if STAGE=="test" else "")]
for fam in FAMILIES:
    subset=[r for r in case_rows if r["family"]==fam]
    fcost={m:sum(r["cost"][m] for r in subset) for m in MODES}
    lines.append("| %s | %d | %.4f | %.4f | %.4f | %s"%(
        fam,len(subset),fcost["ca_plain"],fcost["orig_v76"],
        fcost["orig_v76_plain"],
        ("%.4f |"%fcost["trained_selector"]) if STAGE=="test" else ""))
lines += ["","## Every formula (includes failures and regressions)","",
          "| Case | CaDiCaL | Guided | Plain |"+
          (" Selector |" if STAGE=="test" else ""),
          "|---|---:|---:|---:|"+("---:|" if STAGE=="test" else "")]
for r in sorted(case_rows,key=lambda x:(x["family"],x["name"])):
    lines.append("| %s | %.4f | %.4f | %.4f | %s"%(
        r["name"],r["cost"]["ca_plain"],r["cost"]["orig_v76"],
        r["cost"]["orig_v76_plain"],
        ("%.4f |"%r["cost"]["trained_selector"]) if STAGE=="test" else ""))
(ROOT/"summary.md").write_text("\n".join(lines)+"\n")
(ROOT/"totals.json").write_text(json.dumps(totals,indent=2))
with (ROOT/"all_raw.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
print("\n".join(lines),flush=True)
