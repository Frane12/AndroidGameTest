#!/usr/bin/env python3
"""Fail closed: assemble all 12 frozen 72-instance evaluation shards."""
from collections import defaultdict
import hashlib,json
from pathlib import Path
MODES=("orig_v76","hybrid_gate_with_observer","ca_plain")
def main():
    root=Path("gathered")
    paths=sorted(root.glob("prereg72-shard-*/results/summary.json"))
    if len(paths)!=12:
        raise RuntimeError(f"Expected 12 complete shard reports, got {len(paths)}")
    data=[json.loads(p.read_text()) for p in paths]
    assert {d["shard"] for d in data}==set(range(12))
    assert len({d["manifest_sha256"] for d in data})==1
    allrows=[r for d in data for r in d["rows"]]
    assert len(allrows)==72*3*2,len(allrows)
    ids={r["id"] for r in allrows}
    assert len(ids)==72
    for case in ids:
        runs=[r for r in allrows if r["id"]==case]
        assert len(runs)==6
        assert {(r["mode"],r["repeat"]) for r in runs}=={
            (name,repeat) for name in MODES for repeat in (0,1)}
    errors=[r for r in allrows if r["status"] in ("ERROR","INPUT_ERROR")]
    errors +=[e for d in data for e in d["errors"]]
    # Even on a corrupted/missing runner, make invalidity explicit.
    rows=["# DRNAS SAT: 72 previously unrun official 2026 CNFs","",
      "EXPLORATORY, public-outcome-informed stratification, not a random sample or blind holdout.",
      "Two paired repeats; per-mode cap 20 s; timeout counted as 40 s (PAR-2).",
      "Different shards can run on different CPU models; within shard pinning is fixed.",
      "Native SAT model checked; UNSAT must be independently certified.",
      "",
      "| Stratum | Solver mode | Solved | Total trials | Mean PAR-2 (s) |",
      "|---|---|---:|---:|---:|"]
    groups=defaultdict(list)
    for r in allrows:groups[(r["stratum"],r["mode"])].append(r)
    for (stratum,mode),rs in sorted(groups.items()):
        if any(r["status"] in ("ERROR","INPUT_ERROR") for r in rs):
            par="INVALID"
        else:
            costs=[r["wall_s"] if r["status"] in ("SAT","UNSAT") else 40.0 for r in rs]
            par=f"{sum(costs)/len(costs):.3f}"
        solved=sum(r["status"] in ("SAT","UNSAT") for r in rs)
        rows.append(f"| {stratum} | {mode} | {solved} | {len(rs)} | {par} |")
    rows+=["","## Aggregate (stratified subset only)"]
    for mode in MODES:
        rs=[r for r in allrows if r["mode"]==mode]
        if any(r["status"] in ("ERROR","INPUT_ERROR") for r in rs):
            rows.append(f"- {mode}: INVALID - missing or erroneous data")
        else:
            par=sum(r["wall_s"] if r["status"] in ("SAT","UNSAT") else 40 for r in rs)/len(rs)
            solved=sum(r["status"] in ("SAT","UNSAT") for r in rs)
            rows.append(f"- {mode}: {solved}/{len(rs)} solved, mean PAR-2 {par:.3f} s")
    rows+=["",f"Input/solver errors: {len(errors)}","",
        "No training/tuning has been performed on these selected 72 instance IDs.",
        "Source files frozen, exact GitHub workflow reports available for scrutiny."]
    Path("prereg72_full_report.md").write_text("\n".join(rows)+"\n")
    Path("prereg72_all_results.json").write_text(json.dumps(
        {"run":"72-preregistered-2026","manifest_sha256":data[0]["manifest_sha256"],
         "rows":allrows,"errors":errors,"shards":data},indent=2))
    print("\n".join(rows),flush=True)
    if errors:raise RuntimeError("Invalid or incomplete experiment; retained detailed errors")
if __name__=="__main__":main()
