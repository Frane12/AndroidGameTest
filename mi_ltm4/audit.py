"""Bounded proof-first LTM4 structural-graph and offline shadow screening.

These snapshots are *synthetic* and explicitly NOT obtained from the live
native CDCL trail. This benchmark establishes detection coverage and cost
only. PAR2 is deliberately not reported because no solver arm is compared.
"""
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"mi_ltm3"))
from design import cohort
from graph_shadow import graph,sample_snapshots


def main():
    train=cohort(training_generation=1001)
    diagnostics=[]
    for c in train:
        start=time.perf_counter()
        report=graph(c["clauses"])
        graph_cost=time.perf_counter()-start
        snapshots=sample_snapshots(c["clauses"],max_snapshots=12)
        count=Counter()
        for row in snapshots:
            count.update(row["measurements"])
        diagnostics.append(dict(
            sha256=c["sha"],split=c["split"],family=c["family"],
            motif_types=len(report["features"]),
            certified_source_rows=len(report["rows"]),
            edges=len(report["edges"]),
            structural_signature=report["signature"],
            graph_cost_s=round(graph_cost,8),
            snapshots=len(snapshots),
            shadow_candidate_units=count["candidate_unconfirmed_BCP"],
            shadow_candidate_conflicts=count["candidate_conflict"],
            native_trail_observed=False,
            solver_changed=False))
    byfamily={}
    for family in sorted({x["family"] for x in diagnostics}):
        rows=[x for x in diagnostics if x["family"]==family]
        byfamily[family]=dict(
            formulas=len(rows),
            formulas_with_rows=sum(x["certified_source_rows"]>0 for x in rows),
            graph_cost_s=round(sum(x["graph_cost_s"] for x in rows),6),
            source_rows=sum(x["certified_source_rows"] for x in rows),
            graph_edges=sum(x["edges"] for x in rows),
            synthetic_shadow_units=sum(x["shadow_candidate_units"] for x in rows))
    report=dict(
        mode="synthetic_offline_shadow_diagnostic_NOT_NATIVE_CDCL_TRAIL",
        original_cnfs=len(diagnostics),
        train_shas=len({x["sha256"] for x in diagnostics if x["split"]=="train"}),
        holdout_shas=len({x["sha256"] for x in diagnostics if x["split"]=="holdout"}),
        native_cdcl_trail_integrated=False,
        SAT_UNSAT_results=None,PAR2=None,
        source_shas_disjoint=True,
        by_family=byfamily,formula_diagnostics=diagnostics)
    Path("MI_LTM4_GRAPH_SHADOW.json").write_text(json.dumps(report,indent=2))
    print("MI_LTM4_GRAPH_FINAL",json.dumps({
        "mode":report["mode"],"original_cnfs":len(diagnostics),
        "by_family":byfamily,"PAR2":None,
        "live_trail":False},sort_keys=True),flush=True)


if __name__=="__main__":
    main()
