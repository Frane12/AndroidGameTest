"""LTM5 graph-motion audit on existing 384 frozen/train source CNFs.

Produces offline replay only, with deliberately synthetic assignments.
Does not claim native CDCL trail integration or SAT speedup.
"""
import json
import sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"mi_ltm3"))
from design import cohort
from dynamic_graph import GraphTrajectory


def main():
    cases=cohort(training_generation=1001)
    totals=Counter()
    by_family={}
    motions=Counter()
    examples=[]
    for case in cases:
        trajectory=GraphTrajectory(case["clauses"])
        if trajectory.sources:
            variables=trajectory.sources[0]["variables"]
            trajectory.decide(variables[0],True)
            if len(variables)>1:
                trajectory.propagate(variables[1],False)
            trajectory.backtrack(0)
        transitions=trajectory.transition_histogram()
        motions.update(transitions)
        family=by_family.setdefault(case["family"],Counter())
        family["formulas"]+=1
        family["with_certified_rows"]+=bool(trajectory.sources)
        family["certified_rows"]+=len(trajectory.sources)
        family["events"]+=len(trajectory.events)
        totals["formulas"]+=1
        totals["events"]+=len(trajectory.events)
        if len(examples)<15 and trajectory.sources:
            examples.append(dict(sha=case["sha"],family=case["family"],
                                 structure=trajectory.initial_signature,
                                 motion=trajectory.trajectory_key(),
                                 events=trajectory.events))
    report=dict(
        mode="LTM5_OFFLINE_SYNTHETIC_TRANSITION_REPLAY",
        native_cdcl_trail=False,
        solver_modified=False,
        SAT_UNSAT=None,
        PAR2=None,
        totals=dict(totals),
        by_family={k:dict(v) for k,v in by_family.items()},
        transition_types=dict(motions),
        examples=examples,
        warning="No native trail or BCP closure. Synthetic state trajectories cannot train intervention usefulness.")
    (ROOT/"MI_LTM5_MOTION.json").write_text(json.dumps(report,indent=2))
    print("MI_LTM5_FINAL",json.dumps({
        "totals":report["totals"],
        "by_family":report["by_family"],
        "transition_types":len(motions),
        "live_CDCL":False,
        "PAR2":None},sort_keys=True),flush=True)


if __name__=="__main__":
    main()
