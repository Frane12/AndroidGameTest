#!/usr/bin/env python3
"""Exploratory v8.9 structure screen; NO fitted rule or out-of-sample claim."""
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv)>1 else Path("combined-structural-v89")
CAP=3.0
REPEATS=3
MODES=("ca_plain","orig_v76","orig_v76_plain",
       "v89_rate_no_hints","v89_rate_late_hints")
FEATURE_NAMES=("density","mean_width","binary_fraction",
               "degree_cv","max_degree_over_mean",
               "polarity_imbalance","largest_component_fraction",
               "isolated_variable_fraction")
CASES=[]
ROWS=[]
for shard in range(5):
    folder=ROOT/("shard-%d"%shard)
    manifest=json.loads((folder/"manifest.json").read_text())
    assert manifest["experiment"]=="drnas-v89-structural-pilot40-20261031-frozen-v1"
    assert manifest["cap_s"]==CAP and manifest["repeats"]==REPEATS
    assert tuple(manifest["modes"])==MODES and len(manifest["cases"])==8
    CASES += manifest["cases"]
    with (folder/"raw.csv").open(newline="") as f:
        ROWS += list(csv.DictReader(f))
assert len(CASES)==40 and len({c["sha256"] for c in CASES})==40
assert len(ROWS)==40*REPEATS*len(MODES)
assert len({(r["sha256"],r["mode"],r["repeat"]) for r in ROWS})==len(ROWS)
grouped=defaultdict(list)
for r in ROWS:
    assert r["mode"] in MODES and r["status"] in ("SAT","UNSAT","TIMEOUT","ERROR")
    grouped[(r["sha256"],r["mode"])].append(r)

def median_result(case,mode):
    block=grouped[(case["sha256"],mode)]
    assert len(block)==REPEATS and {int(r["repeat"]) for r in block}=={0,1,2}
    solved=sum(r["status"] in ("SAT","UNSAT") for r in block)
    costs=[float(r["wall_s"]) if r["status"] in ("SAT","UNSAT")
           else 2*CAP for r in block]
    return statistics.median(costs),solved

def median_or_none(xs):
    return round(statistics.median(xs),5) if xs else None

def rank(xs):
    order=sorted(range(len(xs)),key=lambda i:xs[i])
    ranks=[0.0]*len(xs)
    j=0
    while j<len(xs):
        k=j+1
        while k<len(xs) and xs[order[k]]==xs[order[j]]:k+=1
        avg=(j+k-1)/2+1
        for i in range(j,k):ranks[order[i]]=avg
        j=k
    return ranks

def pearson(xs,ys):
    mx,my=statistics.mean(xs),statistics.mean(ys)
    u=[v-mx for v in xs];v=[w-my for w in ys]
    denom=math.sqrt(sum(q*q for q in u)*sum(q*q for q in v))
    return (sum(a*b for a,b in zip(u,v))/denom) if denom else None

total={mode:0.0 for mode in MODES}
results=[]
errors=[]
for case in CASES:
    sha=case["sha256"]
    block=[r for r in ROWS if r["sha256"]==sha]
    assert len(block)==len(MODES)*REPEATS
    if any(r["status"]=="ERROR" for r in block):
        errors.append(case["cnf"]+": mode error")
    known={r["status"] for r in block if r["status"] in ("SAT","UNSAT")}
    if len(known)>1:errors.append(case["cnf"]+": contradictory SAT/UNSAT")
    if case["known_truth"].startswith("UNSAT") and "SAT" in known:
        errors.append(case["cnf"]+": SAT for unsatisfiable pigeonhole")
    med={m:median_result(case,m) for m in MODES}
    for mode in MODES:total[mode]+=med[mode][0]
    g=med["orig_v76"];p=med["orig_v76_plain"]
    comparable=(g[1]==REPEATS and p[1]==REPEATS and p[0]>=0.1)
    ratio=(p[0]/g[0]) if comparable and g[0]>0 else None
    category=("GUIDED_WIN" if ratio is not None and ratio>1.25 else
              "GUIDED_LOSS" if ratio is not None and ratio<0.8 else
              "NEUTRAL" if comparable else "INCONCLUSIVE")
    results.append(dict(case=Path(case["cnf"]).stem,
        family=case["family"],sha256=sha,category=category,
        ratio_plain_over_guided=round(ratio,6) if ratio is not None else None,
        **{m+"_par2":round(med[m][0],6) for m in MODES},
        **{m+"_solved":med[m][1] for m in MODES},
        **case["features"]))
if errors:raise RuntimeError("Solver discrepancies/errors: "+str(errors))
assert len(results)==40
# The min-of-two oracle is an idealized lower bound on cost: it knows the
# answer in advance and is NOT an implementable solver or a proof of accuracy.
oracle=sum(min(r["orig_v76_par2"],r["orig_v76_plain_par2"]) for r in results)
comparable=[r for r in results if r["ratio_plain_over_guided"] is not None]
line=["# DRNAS SAT V8.9 — structural pilot (40 unseen synthetic formulas)","",
      "Exploratory structural screening only; no general speedup/complexity theorem established.",
      "All 600 runs: 40 CNFs x 3 repeats x 5 modes, 3 s cap; PAR-2 timeouts count as 6 s.",
      "Same CaDiCaL 3.0.1 and frozen v7.6; 5 single-core runners; compare only paired cases.",
      "SAT model checked by native solver; arbitrary UNSAT proofs not independently checked.",
      "Features are invariant to variable renaming and sign inversion, and no family IDs enter them.",
      "Category only when BOTH guided and unhinted solve 3/3 and unhinted median >=0.10 s.",
      "GUIDED_WIN >1.25x; GUIDED_LOSS <0.8x; otherwise neutral/inconclusive.",
      "Feature associations in this report are hypotheses, NOT confirmed predictors.","",
      "## Aggregate PAR-2 (sum of per-case medians, lower is better)","",
      "| Mode | PAR-2 seconds |","|---|---:|"]
line += ["| %s | %.5f |"%(mode,total[mode]) for mode in MODES]
line += ["","Perfect hindsight min(V7.6 guided, V7.6 plain): %.5f s; NOT deployable."%oracle,
         "Potential oracle saving vs always-plain: %.3f%%"%
         (100*(1-oracle/total["orig_v76_plain"])),"",
         "## Per-family descriptive counts (no significance test)","",
         "| Family | Cases | Comparable | Guided wins | Guided losses | Neutral | Inconclusive |",
         "|---|---:|---:|---:|---:|---:|---:|"]
for family in ("random3","random4","color3","xor3","pigeonhole"):
    subset=[r for r in results if r["family"]==family]
    counts={label:sum(r["category"]==label for r in subset) for label in
            ("GUIDED_WIN","GUIDED_LOSS","NEUTRAL","INCONCLUSIVE")}
    line.append("| %s | %d | %d | %d | %d | %d | %d |"%(
        family,len(subset),len(subset)-counts["INCONCLUSIVE"],
        counts["GUIDED_WIN"],counts["GUIDED_LOSS"],
        counts["NEUTRAL"],counts["INCONCLUSIVE"]))
line += ["","## Cross-family-centered rank associations (exploratory)","",
         "Rank Spearman uses only comparable examples; family-centers each feature and log speed ratio before pooling.",
         "Ranking across distinct families and small sample sizes may be misleading.",
         "| Feature | Centered rank correlation with log(plain/guided) |",
         "|---|---:|"]
for feature in FEATURE_NAMES:
    xs=[];ys=[]
    for family in ("random3","random4","color3","xor3","pigeonhole"):
        subset=[r for r in comparable if r["family"]==family]
        if len(subset)<2:continue
        fx=[float(r[feature]) for r in subset]
        fy=[math.log(r["ratio_plain_over_guided"]) for r in subset]
        xbar=statistics.mean(fx);ybar=statistics.mean(fy)
        xs.extend(v-xbar for v in fx);ys.extend(v-ybar for v in fy)
    val=pearson(rank(xs),rank(ys)) if len(xs)>=8 else None
    line.append("| %s | %s |"%(feature,"%.3f"%val if val is not None else "insufficient"))
line += ["","## Every case, including timeouts and regressions","",
         "| Case | Guided V7.6 | Plain V7.6 | CaDiCaL | Ratio | Class |",
         "|---|---:|---:|---:|---:|---|"]
for r in sorted(results,key=lambda x:(x["family"],x["case"])):
    ratio=r["ratio_plain_over_guided"]
    line.append("| %s | %.4fs | %.4fs | %.4fs | %s | %s |"%(
        r["case"],r["orig_v76_par2"],r["orig_v76_plain_par2"],
        r["ca_plain_par2"],("%.2fx"%ratio if ratio is not None else "n/a"),
        r["category"]))
line += ["","## Interpretation constraints","",
         "- The pilot is inspected; do not treat fitted thresholds as out-of-sample.",
         "- Do not claim a structural class based on family-level differences or easy sub-0.1-second examples.",
         "- Any derived selector must be frozen before a separately seeded 200-instance holdout.",
         "- Stronger proof needs independent CNFs and UNSAT proof checking."]
report="\n".join(line)+"\n"
(ROOT/"summary.md").write_text(report)
(ROOT/"case_metrics.json").write_text(json.dumps(results,indent=2))
(ROOT/"totals.json").write_text(json.dumps(total,indent=2))
with (ROOT/"all_raw.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=ROWS[0].keys())
    w.writeheader()
    w.writerows(ROWS)
print(report,flush=True)
