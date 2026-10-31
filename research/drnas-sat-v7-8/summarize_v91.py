#!/usr/bin/env python3
"""Predeclared v9.1 full paired PAR2 audit. Never optimize thresholds on this holdout."""
import csv,json,os,statistics,sys,hashlib
from pathlib import Path
from collections import defaultdict,Counter
ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path("combined-v91")
VERSION="drnas-v91-30-independent-cnfs-prespecified-lbd6-prop32-v1"
MODES=("ca_plain","orig_v76","orig_v76_plain","v91_never_late","v91_always_late","v91_quality_gate")
CAUSAL=MODES[-3:]
FAMILIES=("random3","random4","color3","xor3","pigeonhole")
CAP=3.0;REPEATS=3
cases=[];raw=[]
for shard in range(5):
    folder=ROOT/("shard-"+str(shard))
    obj=json.loads((folder/"manifest.json").read_text())
    assert obj["version"]==VERSION and obj["cap_s"]==CAP and obj["repeats"]==REPEATS
    assert tuple(obj["modes"])==MODES and len(obj["cases"])==6
    cases+=obj["cases"]
    with (folder/"raw.csv").open(newline="") as fh:raw+=list(csv.DictReader(fh))
assert len(cases)==30 and len({x["sha256"] for x in cases})==30
assert len(raw)==30*len(MODES)*REPEATS

def cost(part):
    assert len(part)==REPEATS and {int(x["repeat"]) for x in part}=={0,1,2}
    solved=sum(x["status"] in ("SAT","UNSAT") for x in part)
    return statistics.median(float(x["wall_s"]) if x["status"] in ("SAT","UNSAT")
                             else 2*CAP for x in part),solved
lines=[
"# DRNAS v9.1 — genuine causal late-phase LBD gate, held-out 30 CNFs",
"",
"30 precommitted new-seed formulas, 6 methods, 3 paired repetitions = 540 solver runs.",
"All modes share instrumented CaDiCaL 3.0.1, same per-case runner, CPU affinity, seeds.",
"All three v9.1 modes: IDENTICAL first 256 unhinted conflicts; same v7.6 learned-delta extend rule and 768 additional budget.",
"Only change is whether hints are switched on AFTER first 256 conflicts.",
"Frozen quality gate (derived before this run from exploratory v9.0):",
"  >=20 learned first-UIP clauses, >=6% TRUE LBD<=2, >=32 search propagations/conflict.",
"Each timeout is PAR2=6s, never silently discarded. Pigeonhole CNFs may be structurally isomorphic despite new hashes.",
"SAT witnesses checked by C++ solver. No external UNSAT proof checking. Not a world record.",
"",
"| Case | CaDiCaL | v7.6 guided | v7.6 no hints | v9.1 never | v9.1 always | v9.1 selector | Ca/selector | Never/selector | Gate applied (out of 3) |",
"|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
totals={m:0. for m in MODES}
family=defaultdict(lambda:{"cases":0,"measurable":0,"wins_vs_never":0,"losses_vs_never":0,"wins_vs_ca":0,"losses_vs_ca":0,"any_timeout":0,"gate_repetitions":0,"gate_total_known":0,"ratios":[]})
errors=[];diagnostics=[];n_gate=0;n_gate_known=0
for case in cases:
    name=Path(case["cnf"]).stem
    rs=[r for r in raw if r["case"]==name]
    assert len(rs)==REPEATS*len(MODES) and {r["sha256"] for r in rs}=={case["sha256"]}
    results={m:cost([r for r in rs if r["mode"]==m]) for m in MODES}
    for m in MODES:totals[m]+=results[m][0]
    ans={r["status"] for r in rs if r["status"] in ("SAT","UNSAT")}
    if len(ans)>1: errors.append(name+" contradictory answers")
    if any(r["status"]=="ERROR" for r in rs): errors.append(name+" solver error")
    if case["known_truth"].startswith("UNSAT") and "SAT" in ans:
        errors.append(name+" wrong known UNSAT")
    # The early probe MUST be identical in each matched arm for every
    # completed run. Only downstream hints can differ.
    all_gates=[]
    for repeat in range(REPEATS):
        early=[r for r in rs if int(r["repeat"])==repeat and r["mode"] in CAUSAL]
        assert len(early)==3
        if any(r["status"] in ("TIMEOUT","ERROR") for r in early):continue
        for key in ("v90_learned_256","v90_lbd2_256","v90_lbd_sum_256",
                    "v90_props_256","v90_conflicts_256","v90_jumpdepth_256",
                    "learned_delta","threshold","active_256","hints"):
            if len({r.get(key) for r in early})!=1:
                errors.append(name+" early divergent "+key+" rep "+str(repeat))
        selector=next(r for r in early if r["mode"]=="v91_quality_gate")
        all_gates.append(int(selector["v91_phase_applied"]))
        n_gate+=int(selector["v91_phase_applied"]);n_gate_known+=1
        if selector.get("v91_quality_signal","") not in ("0","1"):
            errors.append(name+" missing gate signal")
        if int(selector["v91_phase_applied"]) and selector["extended"]!="1":
            errors.append(name+" applied hints without durable extension")
        # sanity unconditional & never arms act as advertised when extending
        always=next(r for r in early if r["mode"]=="v91_always_late")
        never=next(r for r in early if r["mode"]=="v91_never_late")
        if never["v91_phase_applied"]!="0":
            errors.append(name+" never arm used hints")
        if always["extended"]=="1" and always["v91_phase_applied"]!="1":
            errors.append(name+" always arm failed to phase")
    fs=family[case["family"]];fs["cases"]+=1
    fs["gate_repetitions"]+=sum(all_gates)
    fs["gate_total_known"]+=len(all_gates)
    if any(n!=REPEATS for _,n in results.values()):fs["any_timeout"]+=1
    base=results["ca_plain"];never=results["v91_never_late"];select=results["v91_quality_gate"]
    measurable=all(n==REPEATS for _,n in (base,never,select)) and min(base[0],never[0])>=0.05
    rca=base[0]/select[0] if measurable else None
    rnever=never[0]/select[0] if measurable else None
    if measurable:
        fs["measurable"]+=1;fs["ratios"].append(rnever)
        fs["wins_vs_never"]+=rnever>1.25;fs["losses_vs_never"]+=rnever<0.8
        fs["wins_vs_ca"]+=rca>1.25;fs["losses_vs_ca"]+=rca<0.8
    fmt=lambda m:"%.4fs (%d/3)"%results[m]
    lines.append("| "+name+" | "+" | ".join(fmt(m) for m in MODES)+
        " | "+("%.2fx"%rca if rca is not None else "n/a")+
        " | "+("%.2fx"%rnever if rnever is not None else "n/a")+
        " | %d/%d |"%(sum(all_gates),len(all_gates)))
    diagnostics.append({"case":name,"family":case["family"],"sha256":case["sha256"],
       "PAR2":{m:results[m][0] for m in MODES},"solved":{m:results[m][1] for m in MODES},
       "ratio_ca":rca,"ratio_never":rnever,"selector_applied_repeats":all_gates,
       "learned_256":[r.get("v90_learned_256") for r in rs if r["mode"]=="v91_quality_gate"],
       "lbd2_256":[r.get("v90_lbd2_256") for r in rs if r["mode"]=="v91_quality_gate"],
       "propagations_256":[r.get("v90_props_256") for r in rs if r["mode"]=="v91_quality_gate"]})
lines+=["","## Full family results","",
"| Family | Cases | Measurable | Median never/selector | selector wins >1.25x | selector losses <0.8x | Cases any timeout | Phase applied/known repetitions |",
"|---|---:|---:|---:|---:|---:|---:|---:|"]
for fam in FAMILIES:
    d=family[fam]
    lines.append("| %s | %d | %d | %s | %d | %d | %d | %d/%d |"%(
        fam,d["cases"],d["measurable"],
        "%.3fx"%statistics.median(d["ratios"]) if d["ratios"] else "n/a",
        d["wins_vs_never"],d["losses_vs_never"],d["any_timeout"],
        d["gate_repetitions"],d["gate_total_known"]))
lines+=["","## Full 30-case PAR2 sums, including timeouts","",
"| Mode | PAR2 seconds |","|---|---:|"]
for mode in MODES:lines.append("| %s | %.5f |"%(mode,totals[mode]))
lines+=["","Early probe equality audit: "+("FAIL "+str(errors) if errors else "PASS, all fully observed v9.1 paired first-stage counters match"),
       "Actual late phase applications: %d/%d observed paired repetitions"%(n_gate,n_gate_known),
       "No significant speedups or world records claimed from one synthetic holdout.",
       "Any simple rule inferred from this test would require a NEW independent holdout for validation."]
report="\n".join(lines)+"\n"
(ROOT/"summary.md").write_text(report)
(ROOT/"totals.json").write_text(json.dumps(totals,indent=2))
(ROOT/"diagnostics.json").write_text(json.dumps(diagnostics,indent=2))
(ROOT/"family.json").write_text(json.dumps({k:v for k,v in family.items()},indent=2))
with (ROOT/"all_raw.csv").open("w",newline="") as fh:
    writer=csv.DictWriter(fh,fieldnames=raw[0].keys());writer.writeheader();writer.writerows(raw)
with open(os.environ.get("GITHUB_STEP_SUMMARY",str(ROOT/"actions_summary.md")),"a") as fh:fh.write(report)
print(report,flush=True)
if errors:raise RuntimeError("Contradictions or causal early stage mismatch")
