#!/usr/bin/env python3
"""V13.3 exploratory calibration using exactly the pinned prior 2026 mini results.
No new solve timings, no prospective validation and no official rank claims.
"""
import argparse
import collections
import json
import statistics
from pathlib import Path

MODES=("DRNAS_LBD","DRNAS_Legacy","DRNAS_Soft","DRNAS_NoLate","CaDiCaL301","Kissat404")
CAP=30.0
REPS=2

def check(ok,msg):
    if not ok: raise RuntimeError(msg)

def analyze(data):
    check(data["total_attempts"]==216,"Unexpected run size")
    m=data["source"]
    check(len(m["cases"])==18,"Wrong frozen 2026 sample")
    cases={x["id"]:x for x in m["cases"]}
    check(len(cases)==18 and len({x["sha256"] for x in cases.values()})==18,"Duplicate inputs")
    rows=data["all_rows"]
    check(len(rows)==18*len(MODES)*REPS,"Incomplete measurements")
    groups=collections.defaultdict(dict)
    for r in rows:
        ident=r["cnf_id"];mode=r["mode"];rep=r["repetition"]
        check(ident in cases and mode in MODES and rep in (0,1),"Unknown measurement")
        check(r["cnf_sha256"]==cases[ident]["sha256"],"SHA drift")
        check(r["status"] in ("SAT","UNSAT","TIMEOUT"),"Invalid solver answer")
        check(r["status"]=="TIMEOUT" or r["status"]==cases[ident]["official_label"],"Label mismatch")
        check((mode,rep) not in groups[ident],"Duplicate measurement")
        groups[ident][(mode,rep)]=r

    output=[]; wins=collections.Counter();solved_totals=collections.Counter()
    cost_totals=collections.Counter(); potential_gain=0.0
    for ident,c in cases.items():
        g=groups[ident]
        check(len(g)==len(MODES)*REPS,"Incomplete case")
        costs={};solved={}
        for mode in MODES:
            tt=[g[(mode,i)] for i in range(REPS)]
            solved[mode]=sum(x["status"]!="TIMEOUT" for x in tt)
            costs[mode]=statistics.mean([2*CAP if x["status"]=="TIMEOUT" else x["seconds"] for x in tt])
            solved_totals[mode]+=solved[mode];cost_totals[mode]+=costs[mode]
        best=min(MODES,key=lambda z:(costs[z],-solved[z]))
        order=sorted(MODES,key=lambda z:(costs[z],-solved[z]))
        worst=max(costs.values())
        advantage=worst-costs[best]
        # A case is informative if two strategies differ materially.
        informative=(advantage>=2.0 and advantage>=0.15*worst)
        if informative: wins[best]+=1
        potential_gain+=costs["Kissat404"]-costs[best]
        output.append({
            "id":ident,"sha256":c["sha256"],"cohort":c.get("cohort"),
            "label":c["official_label"],"features":c["features"],
            "best_in_sample":best,"runner_up_in_sample":order[1],
            "informative":informative,"max_par2_gap_s":round(advantage,5),
            "solved_attempts":solved,
            "PAR2_by_solver_s":{z:round(costs[z],6) for z in MODES}
        })
    aggregate={z:{"solved":solved_totals[z],"attempts":36,
                   "PAR2_s":round(cost_totals[z]/18,5)} for z in MODES}
    oavg=sum(min(q["PAR2_by_solver_s"].values()) for q in output)/18
    report={"scope":"Exploratory prior-observed 2026 mini 18 CNFs, not blind. 30s wall cap, 3GiB.",
       "formulas":18,"attempts":216,"informative_count":sum(x["informative"] for x in output),
       "in_sample_informative_best":dict(wins),
       "aggregate":aggregate,"oracle_in_sample_PAR2_s":round(oavg,5),
       "oracle_is_not_a_real_router":True,
       "cases":output,
       "next_test":"Prelock class/router; use SHA-disjoint 2024/2025/2026 or independent benchmark CNFs; include easy-medium-hard; >=2 reps; account for prefix runtime; compare frozen fixed solvers."
       }
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True);p.add_argument("--out",required=True);p.add_argument("--md",required=True)
    a=p.parse_args()
    result=analyze(json.loads(Path(a.source).read_text()))
    Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    lines=["# DRNAS V13.3 — calibration of solver discrimination","",
      "**Exploratory analysis ONLY — the 18 CNFs were seen before. No new solve or record.**","",
      f"Cases: {result['formulas']}; matched trials: {result['attempts']}; informative: {result['informative_count']}/{result['formulas']}.",
      "Informativeness: >=2 s and >=15% difference between slowest and fastest PAR2 within a case.",
      "This classification uses measured outcomes and cannot be used for a prospective router.","",
      "| Solver | Solved attempts | Mean PAR2 (s) |","|---|---:|---:|"]
    for mode,d in sorted(result["aggregate"].items(),key=lambda q:q[1]["PAR2_s"]):
        lines.append(f"| {mode} | {d['solved']}/{d['attempts']} | {d['PAR2_s']:.5f} |")
    lines+=["",f"In-sample oracle lower bound: {result['oracle_in_sample_PAR2_s']:.5f} s (not achievable without prediction).",
           "","## Where solvers differ","",
           "| Formula SHA prefix | Cohort | Best measured | PAR2 spread s |","|---|---|---|---:|"]
    for c in sorted(result["cases"],key=lambda r:-r["max_par2_gap_s"]):
        if c["informative"]:
            lines.append(f"| {c['sha256'][:10]} | {c['cohort']} | {c['best_in_sample']} | {c['max_par2_gap_s']:.3f} |")
    lines+=["","## Next test","",
      "Fix and freeze strategy before a genuinely independent holdout; select solvable easy/medium/hard CNFs, not only hard timeouts.",
      "Include two repeats per solver and count feature-extraction / prefix runtime in the adaptive policy cost.",
      "This calibration uses previously observed inputs; it is not a real blind improvement and not an official SAT Competition result."]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V133_CALIBRATION_PASS",result["formulas"],result["informative_count"],flush=True)
if __name__=="__main__": main()
