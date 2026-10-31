#!/usr/bin/env python3
"""v9.0 audit: true first-UIP LBD vs hints benefit. All 30 CNFs included."""
import csv,json,math,os,statistics,sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path("combined-v90")
VERSION="drnas-v90-true-lbd-30-fresh-20261031-v1"
MODES=("ca_plain","orig_v76","orig_v76_plain","v90_quality_guided","v90_quality_no_hints")
FAMILIES=("random3","random4","color3","xor3","pigeonhole")
CAP=3.0; REPEATS=3
cases=[];rows=[]
for shard in range(5):
    folder=ROOT/("shard-"+str(shard))
    obj=json.loads((folder/"manifest.json").read_text())
    assert obj["version"]==VERSION and obj["cap_s"]==CAP and obj["repeats"]==REPEATS
    assert tuple(obj["modes"])==MODES and len(obj["cases"])==6
    cases+=obj["cases"]
    with (folder/"raw.csv").open(newline="") as fh:rows+=list(csv.DictReader(fh))
assert len(cases)==30 and len({x["sha256"] for x in cases})==30
assert len(rows)==30*REPEATS*len(MODES)

def score(part):
    assert len(part)==REPEATS and {int(x["repeat"]) for x in part}=={0,1,2}
    solved=sum(x["status"] in ("SAT","UNSAT") for x in part)
    cost=statistics.median(float(x["wall_s"]) if x["status"] in ("SAT","UNSAT")
                           else 6.0 for x in part)
    return cost,solved

def med_int(part,key):
    vals=[int(r[key]) for r in part if r["status"] in ("SAT","UNSAT") and r.get(key,"") not in ("",None)]
    return statistics.median(vals) if vals else None

def rank(values):
    sorted_idx=sorted(range(len(values)),key=lambda i:values[i])
    out=[0.]*len(values)
    i=0
    while i<len(values):
        j=i+1
        while j<len(values) and values[sorted_idx[j]]==values[sorted_idx[i]]:j+=1
        for k in range(i,j):out[sorted_idx[k]]=(i+j-1)/2+1
        i=j
    return out

def spearman(pairs):
    if len(pairs)<5:return None
    xs=rank([v[0] for v in pairs]);ys=rank([v[1] for v in pairs])
    mx=statistics.mean(xs);my=statistics.mean(ys)
    xx=sum((x-mx)**2 for x in xs);yy=sum((y-my)**2 for y in ys)
    if xx*yy==0:return None
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/(xx*yy)**.5

families=defaultdict(lambda:dict(count=0,comparable=0,wins=0,losses=0,timeouts=0,ratios=[]))
totals={m:0. for m in MODES}
data=[];errors=[]
lines=[
"# DRNAS SAT v9.0 — true LBD and propagation/backjump exploratory correlation",
"",
"30 newly seeded synthetic CNFs, 5 single-core runners, 5 methods, 3 repeats, 450 paired runs.",
"Each mode uses the SAME explicitly instrumented CaDiCaL 3.0.1 build; original DRNAS v7.6 C++ wrapper is unchanged.",
"Pre-minimization 1st-UIP LBD, search propagations, cumulative backjump-depth are instrumented internally.",
"v9.0 modes reproduce the v7.6 256-conflict durable rule; instrumentation does NOT choose a new solver policy.",
"SAT models internally checked, UNSAT external certificates not checked; timeout = 6s PAR2.",
"Ratios only if both modes solved 3/3 and unphased baseline median >=0.05 s.",
"Correlation is EXPLORATORY, not a predictive test or evidence of a universal acceleration.",
"",
"| Formula | CaDiCaL | Frozen guided | Frozen no hints | v9 guided | v9 no hints | Hint gain (v9 no hints/guided) | Real LBD<=2 % (no-hint) | Propagations/conflict | Avg backjump depth |",
"|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
for case in cases:
    name=Path(case["cnf"]).stem
    part=[r for r in rows if r["case"]==name]
    assert len(part)==5*REPEATS and {r["sha256"] for r in part}=={case["sha256"]}
    answer={r["status"] for r in part if r["status"] in ("SAT","UNSAT")}
    if len(answer)>1: errors.append(name+": contradictory answers")
    if case["known_truth"].startswith("UNSAT") and "SAT" in answer: errors.append(name+": wrong known-UNSAT")
    if any(r["status"]=="ERROR" for r in part):errors.append(name+": unexpected solver error")
    vals={m:score([r for r in part if r["mode"]==m]) for m in MODES}
    fam=families[case["family"]];fam["count"]+=1
    if any(x[1]!=REPEATS for x in vals.values()):fam["timeouts"]+=1
    for m in MODES:totals[m]+=vals[m][0]
    no=[r for r in part if r["mode"]=="v90_quality_no_hints"]
    le=med_int(no,"v90_learned_256")
    lbd2=med_int(no,"v90_lbd2_256")
    props=med_int(no,"v90_props_256")
    conflicts=med_int(no,"v90_conflicts_256")
    jumps=med_int(no,"v90_jumps_256")
    depth=med_int(no,"v90_jumpdepth_256")
    frac=lbd2/le if le and lbd2 is not None else None
    propconf=props/conflicts if conflicts and props is not None else None
    jumpdepth=depth/jumps if jumps and depth is not None else None
    unhint,guided=vals["v90_quality_no_hints"],vals["v90_quality_guided"]
    measurable=(unhint[1]==REPEATS and guided[1]==REPEATS and unhint[0]>=0.05)
    gain=unhint[0]/guided[0] if measurable else None
    if gain is not None:
        fam["comparable"]+=1;fam["ratios"].append(gain)
        fam["wins"]+=gain>1.25;fam["losses"]+=gain<0.8
    fmt=lambda mode:"%.4fs (%d/3)"%vals[mode]
    lines.append("| "+name+" | "+" | ".join(fmt(m) for m in MODES)+" | "+
        ("%.2fx"%gain if gain is not None else "n/a")+" | "+
        ("%.1f%%"%(frac*100) if frac is not None else "n/a")+" | "+
        ("%.2f"%propconf if propconf is not None else "n/a")+" | "+
        ("%.2f"%jumpdepth if jumpdepth is not None else "n/a")+" |")
    data.append({"case":name,"family":case["family"],"gain":gain,
                 "lbd2_frac":frac,"prop_per_conflict":propconf,"mean_backjump":jumpdepth,
                 "lbd2":lbd2,"lbd_le4":med_int(no,"v90_lbd4_256"),
                 "lbd_sum":med_int(no,"v90_lbd_sum_256"),"learnt":le,
                 "propagations":props,"conflicts":conflicts,"jumps":jumps,
                 "backjump_depth_sum":depth,"mode_par2":{m:vals[m][0] for m in MODES}})
lines+=["","## Full per-family paired summary",
"| Family | Cases | Measurable hint comparisons | Median hint gain | >1.25x | <0.8x | Any mode timed out |",
"|---|---:|---:|---:|---:|---:|---:|"]
for fam in FAMILIES:
    d=families[fam]
    lines.append("| %s | %d | %d | %s | %d | %d | %d |"%(
        fam,d["count"],d["comparable"],
        ("%.3fx"%statistics.median(d["ratios"]) if d["ratios"] else "n/a"),
        d["wins"],d["losses"],d["timeouts"]))
lines+=["","## PAR2 sum of all 30 formula medians (lower is better)",
"| Mode | Total |","|---|---:|"]
for m in MODES:lines.append("| %s | %.5f s |"%(m,totals[m]))
lines+=["","## Out-of-model exploratory rank correlation (not cross-validated)",""]
for feature in ("lbd2_frac","prop_per_conflict","mean_backjump"):
    pairs=[(x[feature],math.log(x["gain"])) for x in data
           if x["gain"] is not None and x[feature] is not None and x["gain"]>0]
    corr=spearman(pairs)
    lines.append("- %s vs log(hint speedup): n=%d, Spearman=%s"%(
        feature,len(pairs),"%.3f"%corr if corr is not None else "insufficient variation/data"))
lines+=["","Errors/contradictions: "+(str(errors) if errors else "none detected"),
        "LBD here is a *true internal first-UIP* glue computed by CaDiCaL, pre-minimization.",
        "A low LBD count alone does not establish clause usefulness; propagation and backjump counters are also descriptive.",
        "Instrumented performance numbers must not be treated as official unmodified CaDiCaL competition performance."]
report="\n".join(lines)+"\n"
(ROOT/"summary.md").write_text(report)
(ROOT/"case_telemetry.json").write_text(json.dumps(data,indent=2))
(ROOT/"par2_totals.json").write_text(json.dumps(totals,indent=2))
with (ROOT/"all_raw.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
with open(os.environ.get("GITHUB_STEP_SUMMARY",str(ROOT/"gh_summary.md")),"a") as f:f.write(report)
print(report,flush=True)
if errors:raise RuntimeError("Unexpected wrong answer or solver errors, inspect raw logs")
