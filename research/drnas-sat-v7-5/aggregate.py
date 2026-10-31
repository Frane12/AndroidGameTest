#!/usr/bin/env python3
"""Aggregate ALL independent V7.5 GitHub Actions holdout shards, excluding pilot.
Reject duplicate formula IDs; require exact six methods and paired repeats.
No case may be selected by measured performance or deleted after timeout.
"""
import argparse
import csv
import json
import hashlib
from pathlib import Path
from benchmark import FIELDS, METHODS, report

def main(root,out,repeats,cutoff):
    root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    sources=sorted(root.glob("drnas-v75-shard*-results/v75_results/raw.csv"))
    if len(sources)!=8:
        raise RuntimeError(f"Expected all 8 holdout shards, got {len(sources)}: {sources}")
    rows=[]
    names={}
    for path in sources:
        items=list(csv.DictReader(path.open(newline="",encoding="utf8")))
        if not items:raise RuntimeError("Empty shard "+str(path))
        for r in items:
            k=r["case"]
            if k in names and names[k]!=str(path):
                raise RuntimeError("Same CNF in more than one shard: "+k)
            names[k]=str(path)
            row={}
            for f in FIELDS:
                v=r.get(f,"")
                if f in ("repeat","hints","limit_conflicts","stage1_status","resumed","variables","clauses"):
                    v=int(v) if v else None
                elif f in ("elapsed_s","native_s","hint_us","stage1_us","stage2_us","cutoff_s"):
                    v=float(v) if v else None
                row[f]=v
            rows.append(row)
    result=report(rows,repeats,cutoff)
    result["aggregated_holdout_shards"]=len(sources)
    result["measurement_rows"]=len(rows)
    # No such assertion on PAR2: timeout cases are part of the full sample.
    if len(rows)!=result["cases"]*len(METHODS)*repeats:
        raise RuntimeError("Unexpected number of measurements")
    with (out/"all_raw.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        w.writeheader();w.writerows(rows)
    (out/"summary.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    lines=[
        "# DRNAS SAT V7.5 — prospective real SATLIB holdout",
        "",
        f"Completed **{result['cases']} independent authentic formulas**, 8 disjoint GitHub shards, "
        f"{repeats} repetitions per method. Every timeout retained in PAR-2.",
        "",
        "| Method | PAR-2 sum of per-instance medians (s) | Speed ratio vs plain | Solved attempts | Faster cases |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in METHODS:
        d=result["modes"][name]
        lines.append(
           f"| {name} | {d['par2_sum_case_medians_s']:.4f} | "
           f"{d['speedup_plain_over_mode']:.4f}x | "
           f"{d['solved_runs']}/{d['total_runs']} | {d['faster_cases']} |")
    lines += ["", "## Statistical uncertainty"]
    for mode,ci in result["bootstrap_95pct_ratio"].items():
        lines.append(f"- {mode}: bootstrap 95% speed-ratio interval {ci[0]:.3f}–{ci[1]:.3f}")
    lines += ["", "## Protocol",
              "- CaDiCaL v3.0.1 original, no solver source modifications.",
              "- First solve conflict budget 256 or 1024, after UNKNOWN unphase and solve again with same solver.",
              "- Control split_plain256 verifies the cost of merely stopping and resuming.",
              "- Identical selected variable set with random polarity is the negative control.",
              "- Real SATLIB SHA256 authenticated, preselected without timing information.",
              "- Differences below noise or confidence intervals including unity are inconclusive.",
              "- SAT model checked for every solved SAT instance; UNSAT compared with original corpus labels."]
    (out/"research_report.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    print("\n".join(lines),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--repeats",type=int,default=2)
    p.add_argument("--cutoff",type=float,default=12.)
    a=p.parse_args();main(a.root,a.out,a.repeats,a.cutoff)
