#!/usr/bin/env python3
"""Post-mortem only: report precisely which of 72 pre-registered cases are evaluable.
Original run must remain failed (scientifically incomplete); do not silently
retune, remove or impute any inputs. 20-second per-mode cap, PAR2=40.
No reruns or new selection. Report missing as missing.
"""
import csv,json,hashlib,statistics
from pathlib import Path
ROOT=Path("gathered")
OUT=Path("prereg72_partial_audit")
MODES=("orig_v76","hybrid_gate_with_observer","ca_plain")
def main():
    paths=sorted(ROOT.glob("prereg72-shard-*/results/summary.json"))
    assert len(paths)==12,f"Missing input artifact (got {len(paths)} of 12)"
    summaries=[json.loads(p.read_text()) for p in paths]
    assert {x["shard"] for x in summaries}==set(range(12))
    assert len({x["manifest_sha256"] for x in summaries})==1
    cases={case["id"]:case for sh in summaries for case in sh["input_cases"]}
    assert len(cases)==72
    rows=[r for x in summaries for r in x["rows"]]
    assert len(rows)==72*2*len(MODES)
    by_case={}
    for cid in cases:
        rs=[r for r in rows if r["id"]==cid]
        assert len(rs)==6
        assert {(r["mode"],r["repeat"]) for r in rs}=={
            (mode,rep) for mode in MODES for rep in (0,1)}
        by_case[cid]=rs
    OUT.mkdir(parents=True,exist_ok=True)
    statuses=[]
    evaluable=[]
    non_evaluable=[]
    for cid,rs in sorted(by_case.items()):
        fail=[r for r in rs if r["status"] in ("ERROR","INPUT_ERROR")]
        bad=[r for r in rs if r["status"] not in ("SAT","UNSAT","TIMEOUT","ERROR","INPUT_ERROR")]
        assert not bad
        if fail:
            if len(fail)!=len(rs):
                raise RuntimeError("Partially evaluable case: "+cid)
            non_evaluable.append(cid)
        else:
            evaluable.append(cid)
        statuses.append({
            "id":cid,"stratum":cases[cid]["stratum"],
            "category":"not_evaluable" if fail else "evaluable",
            "problem":fail[0]["error"] if fail else "",
            "results":{mode:[r["status"] for r in sorted(rs,key=lambda z:z["repeat"])
                              if r["mode"]==mode] for mode in MODES}
        })
    assert len(evaluable)+len(non_evaluable)==72
    mode_metrics={}
    for mode in MODES:
        rs=[r for cid in evaluable for r in by_case[cid] if r["mode"]==mode]
        assert len(rs)==2*len(evaluable)
        scores=[r["wall_s"] if r["status"] in ("SAT","UNSAT") else 40.0 for r in rs]
        mode_metrics[mode]={
            "trials":len(rs),"solved_trials":sum(r["status"] in ("SAT","UNSAT") for r in rs),
            "mean_PAR2_s":round(statistics.mean(scores),4),
            "median_PAR2_s":round(statistics.median(scores),4)
        }
    pair_counts={"both_solved":0,"both_timeout":0,"drnas_only_solved":0,
                 "plain_only_solved":0}
    for cid in evaluable:
        for rep in (0,1):
            a=next(r for r in by_case[cid] if r["mode"]=="hybrid_gate_with_observer" and r["repeat"]==rep)
            b=next(r for r in by_case[cid] if r["mode"]=="ca_plain" and r["repeat"]==rep)
            da=a["status"] in ("SAT","UNSAT")
            pb=b["status"] in ("SAT","UNSAT")
            if da and pb:pair_counts["both_solved"]+=1
            elif da:pair_counts["drnas_only_solved"]+=1
            elif pb:pair_counts["plain_only_solved"]+=1
            else:pair_counts["both_timeout"]+=1
    obj={
       "experiment":"DRNAS-SAT-2026-72-original-post-mortem",
       "original_workflow":"https://github.com/Frane12/AndroidGameTest/actions/runs/41222491055",
       "original_manifest_sha256":summaries[0]["manifest_sha256"],
       "pre_registered_instances":72,"evaluable_instances":len(evaluable),
       "not_evaluable_instances":len(non_evaluable),
       "two_paired_repeats_per_evaluable_instance":True,
       "cap_per_solver_seconds":20,"timeout_PAR2_penalty_seconds":40,
       "mode_metrics_evaluable_only":mode_metrics,"hybrid_vs_plain_pair_counts":pair_counts,
       "original_failure_intentionally_preserved":True,
       "limitations":[
           "This is an incomplete 72-case experiment, NOT a valid full 72-case result.",
           "Evaluable subset is conditional on input file size and is not random.",
           "Both outcomes and runtime strata from public competition data guided original sample selection.",
           "Some UNSAT answers match public labels but were not independently proof checked.",
           "Do not infer global performance from the file-size-censored subset.",
           "No SAT solver code/selection/manifests edited in this post-mortem."
       ],
       "cases":statuses}
    (OUT/"audit.json").write_text(json.dumps(obj,indent=2)+"\n")
    with (OUT/"case_status.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=["id","stratum","category","problem"])
        w.writeheader()
        for d in statuses:w.writerow({k:d[k] for k in w.fieldnames})
    lines=["# DRNAS SAT 2026 — 72-case post-mortem (INCOMPLETE)","",
           "**Not a complete holdout or world-record claim.**",
           f"- Pre-registered: 72. Evaluable: {len(evaluable)}. Missing: {len(non_evaluable)}.",
           "- Original GitHub run remains scientifically incomplete/failed.",
           "- Original selection is not blind nor representative of SAT Competition.",
           "- 2 paired repeats, 20-second cap, 40-second PAR-2 timeout penalty.",
           "",
           "| Solver | Valid trials | Solved | Mean PAR-2 (s) |",
           "|---|---:|---:|---:|"]
    for m,metrics in mode_metrics.items():
        lines.append(f'| {m} | {metrics["trials"]} | {metrics["solved_trials"]} | {metrics["mean_PAR2_s"]:.3f} |')
    lines+=["","## Hybrid vs plain, per paired replicate",""]
    for k,v in pair_counts.items():lines.append(f"- {k}: {v}")
    lines+=["","## Not evaluable (never silently excluded)","",
            "| Instance | Official baseline stratum | Reason |","|---|---|---|"]
    for d in statuses:
        if d["category"]=="not_evaluable":
            lines.append(f'| {d["id"]} | {d["stratum"]} | {d["problem"]} |')
    lines+=["","**Interpretation:** Complete the original roster or report it as incomplete;",
            "the evaluated-only figures are descriptive of a file-size-censored subset."]
    (OUT/"audit.md").write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
if __name__=="__main__":main()
