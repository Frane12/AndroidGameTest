#!/usr/bin/env python3
"""Predeclared 30-case v9.2 static-phase audit; compare all errors/timeouts."""
import csv,json,os,statistics,sys
from pathlib import Path
from collections import defaultdict,Counter
ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path("combined-v92")
VERSION="drnas-v92-30-fresh-early-structural-o-literals-v1"
MODES=("ca_plain","orig_v76","orig_v76_plain","v92_full_compat","v92_sparse","v92_structural")
FAMILIES=("random3","random4","color3","xor3","pigeonhole","planted3")
CAP=3.0
REPEATS=3
cases=[];raw=[]
for shard in range(5):
    f=ROOT/("shard-"+str(shard))
    m=json.loads((f/"manifest.json").read_text())
    assert m["version"]==VERSION and m["cap_s"]==CAP and m["repeats"]==REPEATS
    assert tuple(m["modes"])==MODES and len(m["cases"])==6
    cases+=m["cases"]
    with (f/"raw.csv").open(newline="") as fh:raw+=list(csv.DictReader(fh))
assert len(cases)==30 and len({x["sha256"] for x in cases})==30
assert len(raw)==30*len(MODES)*REPEATS

def score(part):
    assert len(part)==REPEATS and {int(x["repeat"]) for x in part}=={0,1,2}
    nsolved=sum(r["status"] in ("SAT","UNSAT") for r in part)
    return statistics.median(float(r["wall_s"]) if r["status"] in ("SAT","UNSAT") else 2*CAP for r in part),nsolved

lines=[
"# DRNAS SAT v9.2 — pre-first-conflict low-level structural phase selection",
"",
"Frozen hypothesis: one O(total CNF literal occurrences) scan checks clause width",
"and variable polarity imbalance. No family labels, file hashes, or outcome",
"data enter the selector. Precommitted algorithm; no tuning after holdout.",
"30 new CNFs including an unseen planted-SAT family, 6 modes, 3 repetitions",
"=540 independent subprocesses, 5 Ubuntu 24.04 runner shards, one core each.",
"3-second wall limit, timeout contributes 6 seconds PAR2. All timeouts and",
"regressions counted; SAT models validated by C++; UNSAT proof not external.",
"Baseline v7.6 is frozen by Git object hash; v9.2 keeps exactly its 256/768",
"checkpoint continuation schedule. Exact matched v92_full_compat audit below.",
"Head-to-head improvements on synthetic generators do NOT establish generality.",
"",
"| Case | CaDiCaL | v7.6 guided | v7.6 no hints | v9.2 full | v9.2 strong hints | v9.2 structural | Ca/structural | v7.6/structural | structural selection |",
"|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
totals={m:0.0 for m in MODES}
family=defaultdict(lambda:dict(count=0,comparable=0,ratios_ca=[],ratios_guided=[],
                                wins_ca=0,losses_ca=0,wins_guided=0,losses_guided=0,
                                any_timeout=0,selection=Counter()))
errors=[];details=[]
for case in cases:
    name=Path(case["cnf"]).stem
    r=[x for x in raw if x["case"]==name]
    assert len(r)==18 and {x["sha256"] for x in r}=={case["sha256"]}
    truth={x["status"] for x in r if x["status"] in ("SAT","UNSAT")}
    if len(truth)>1:errors.append(name+" contradictory SAT and UNSAT")
    if case["known_truth"]=="SAT-by-construction" and "UNSAT" in truth:
        errors.append(name+" contradicts planted SAT witness")
    if case["known_truth"].startswith("UNSAT") and "SAT" in truth:
        errors.append(name+" contradicts known UNSAT")
    if any(x["status"]=="ERROR" for x in r):
        errors.append(name+" solver ERROR")
    modes={m:score([x for x in r if x["mode"]==m]) for m in MODES}
    for m in MODES:totals[m]+=modes[m][0]
    g=family[case["family"]];g["count"]+=1
    if any(v[1]!=REPEATS for v in modes.values()):g["any_timeout"]+=1
    structural=[x for x in r if x["mode"]=="v92_structural"]
    selections=Counter(x.get("v92_choice","") for x in structural)
    g["selection"].update(selections)
    ca=modes["ca_plain"];guided=modes["orig_v76"];sel=modes["v92_structural"]
    comparable=all(v[1]==REPEATS for v in (ca,guided,sel)) and min(ca[0],guided[0])>=.05
    rca=ca[0]/sel[0] if comparable else None
    rguided=guided[0]/sel[0] if comparable else None
    if comparable:
        g["comparable"]+=1;g["ratios_ca"].append(rca);g["ratios_guided"].append(rguided)
        g["wins_ca"]+=rca>1.25;g["losses_ca"]+=rca<.8
        g["wins_guided"]+=rguided>1.25;g["losses_guided"]+=rguided<.8
    fmt=lambda m:"%.4fs (%d/3)"%modes[m]
    choices=", ".join("%s:%d"%(k,v) for k,v in sorted(selections.items()))
    lines.append("| "+name+" | "+" | ".join(fmt(m) for m in MODES)+
                 " | "+("%.2fx"%rca if rca is not None else "n/a")+
                 " | "+("%.2fx"%rguided if rguided is not None else "n/a")+
                 " | "+choices+" |")
    details.append({"case":name,"family":case["family"],"sha256":case["sha256"],
         "PAR2":{m:modes[m][0] for m in MODES},
         "solved":{m:modes[m][1] for m in MODES},
         "speedup_ca":rca,"speedup_guided":rguided,
         "choice_repeats":dict(selections),
         "structure":{k:[x.get(k,"") for x in structural] for k in
           ("v92_broad","v92_strong","v92_clause2","v92_clause3",
            "v92_clause4","v92_maxwidth","v92_static_us")},
         "hint_count":[x.get("hints") for x in structural]})
    # Full compatibility must retain exactly same hints/schedule on solved runs.
    for rep in range(REPEATS):
        pair=[x for x in r if int(x["repeat"])==rep and
              x["mode"] in ("orig_v76","v92_full_compat")]
        assert len(pair)==2
        if any(x["status"] not in ("SAT","UNSAT") for x in pair):continue
        # Frozen v7.6 leaves learned_delta/threshold/active_256
        # unrecorded on terminal stage1 SAT/UNSAT; v9.2 diagnostics do not.
        # Compare those counters only when the original reached its gate.
        frozen=next(x for x in pair if x["mode"]=="orig_v76")
        check=["hints","extended","second_budget"]
        if frozen.get("threshold","") not in ("","0"):
            check+=["learned_delta","threshold","active_256"]
        for field in check:
            if len({x.get(field,"") for x in pair})!=1:
                errors.append(name+" v7.6/full-compat "+field+" mismatch")
lines+=["","## Per-family selection and sensitivity","",
"| Family | CNFs | Comparable | Median Ca/structural | wins >1.25x | losses <0.8x | Median guided/structural | wins | losses | Cases with any timeout |",
"|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
for fam in FAMILIES:
    d=family[fam]
    def fmt(vals):return "%.3fx"%statistics.median(vals) if vals else "n/a"
    lines.append("| %s | %d | %d | %s | %d | %d | %s | %d | %d | %d |"%(
        fam,d["count"],d["comparable"],fmt(d["ratios_ca"]),d["wins_ca"],
        d["losses_ca"],fmt(d["ratios_guided"]),d["wins_guided"],
        d["losses_guided"],d["any_timeout"]))
    lines.append("- "+fam+" selector choices: "+", ".join("%s=%d"%(k,v)
                        for k,v in sorted(d["selection"].items())))
lines+=["","## Complete 30-case PAR2 aggregate","",
"| Mode | Sum of per-case PAR2 median (s) |","|---|---:|"]
for m in MODES:lines.append("| %s | %.5f |"%(m,totals[m]))
lines+=["","Frozen v7.6 matched control audit: "+("FAIL" if errors else "PASS for all fully solved matching pairs"),
        "Errors and contradictions: "+(str(errors) if errors else "none detected"),
        "Phase hints are NOT SAT solutions and do not alter soundness of the solver.",
        "This prospective test remains synthetic and too small for world record, P vs NP, or universal advantage claims."]
report="\n".join(lines)+"\n"
(ROOT/"summary.md").write_text(report)
(ROOT/"case_diagnostics.json").write_text(json.dumps(details,indent=2))
(ROOT/"totals.json").write_text(json.dumps(totals,indent=2))
(ROOT/"family.json").write_text(json.dumps({k:v for k,v in family.items()},indent=2,
                               default=lambda x:dict(x)))
with (ROOT/"all_raw.csv").open("w",newline="") as fh:
    writer=csv.DictWriter(fh,fieldnames=raw[0].keys());writer.writeheader();writer.writerows(raw)
with open(os.environ.get("GITHUB_STEP_SUMMARY",str(ROOT/"actions_summary.md")),"a") as fh:fh.write(report)
print(report,flush=True)
if errors:raise RuntimeError("v9.2 solver error, contradiction, or compatibility mismatch")
