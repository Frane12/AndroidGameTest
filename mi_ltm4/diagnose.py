"""LTM4 training/holdout diagnostic and optional native BASE-vs-CHAIN trial.

The first version does NOT implement an online LTM4 CDCL callback. Motif
extraction is OFFLINE, and diagnostic extraction time is measured separately.
Optional native comparisons are ungated controls; they do not claim LTM4 speedup.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mi_ltm3.design import FAMILIES, cohort, opportunity_key
from mi_ltm4.trajectory import extract
from mi_ltm4.trajectory_store import TrajectoryMemory, recommend


def _paired_native(case, rep, tmp):
    from mi_ltm3.experiment import run_arm
    case["feature_key"] = opportunity_key(case["clauses"], case["n"])
    a = run_arm(case, "BASE", rep, None, tmp)
    b = run_arm(case, "MI_CHAIN", rep, None, tmp)
    if a["sha256"] != b["sha256"] or a["rep"] != b["rep"]:
        raise AssertionError("Unpaired original-CNF comparison")
    return a, b


def _summary(rows):
    if not rows:
        return {"pairs": 0, "note": "No native trials; no performance claim"}
    diffs = [a["par2_s"]-b["par2_s"] for a,b in rows]
    return {
        "pairs": len(rows),
        "BASE_solved": sum(a["solved"] for a,b in rows),
        "MI_CHAIN_solved": sum(b["solved"] for a,b in rows),
        "BASE_PAR2_s": round(sum(a["par2_s"] for a,b in rows), 6),
        "MI_CHAIN_PAR2_s": round(sum(b["par2_s"] for a,b in rows), 6),
        "CHAIN_faster": sum(d>0 for d in diffs),
        "BASE_faster": sum(d<0 for d in diffs),
        "ties": sum(d==0 for d in diffs),
        "median_chain_saving_s": round(statistics.median(diffs), 7)}


def run(*, generation, smoke=False, paired=False):
    if generation < 1:
        raise ValueError("Generation must be >= 1")
    all_cases = cohort(training_generation=generation)
    train = [x for x in all_cases if x["split"] == "train"]
    holdout = [x for x in all_cases if x["split"] == "holdout"]
    if smoke:
        train = [x for x in train if x["case"] < 2]
        holdout = [x for x in holdout if x["case"] < 34]
    held_shas = {c["sha"] for c in holdout}
    if {c["sha"] for c in train} & held_shas:
        raise AssertionError("Training / holdout not disjoint")
    out = ROOT/"mi_ltm4"
    out.mkdir(exist_ok=True)
    db = out/("training_smoke.sqlite" if smoke else "training.sqlite")
    memory = TrajectoryMemory(db)
    train_motifs = 0
    native_train = []
    native_holdout = []
    with TemporaryDirectory() as td:
        tmp = Path(td)
        for count, case in enumerate(train, 1):
            trace = extract(case["raw"])
            memory.remember(case["sha"], trace["episodes"])
            train_motifs += len(trace["episodes"])
            if paired:
                for rep in range(2):
                    a,b = _paired_native(case, rep, tmp)
                    memory.record_pair(case["sha"], rep, a,b)
                    native_train.append((a,b))
            if count%24 == 0:
                print("LTM4_TRAIN_PROGRESS",count,len(train),flush=True)
        frozen = memory.freeze(held_shas)
        memory.close()
        readonly = TrajectoryMemory(db,readonly=True)
        assert readonly.freeze(held_shas) == frozen
        recognized = 0
        matches = 0
        activated = 0
        holdout_motifs = 0
        by_family = {}
        probe_times = []
        for count, case in enumerate(holdout, 1):
            trace = extract(case["raw"])
            probe_times.append(trace["elapsed_s"])
            motifs = trace["episodes"]
            holdout_motifs += len(motifs)
            known = [ep for ep in motifs if ep["key"] in frozen["motifs"]]
            recognized += bool(known)
            matches += len(known)
            route,_ = recommend(frozen, motifs)
            activated += route == "MI_CHAIN"
            row = by_family.setdefault(case["family"],dict(
                cases=0,recognized=0,matched_motifs=0,
                observed_motifs=0,routed_chain=0))
            row["cases"]+=1
            row["recognized"]+=bool(known)
            row["matched_motifs"]+=len(known)
            row["observed_motifs"]+=len(motifs)
            row["routed_chain"]+=route=="MI_CHAIN"
            if paired:
                for rep in range(2):
                    native_holdout.append(_paired_native(case, rep, tmp))
            if count%24 == 0:
                print("LTM4_HOLDOUT_PROGRESS",count,len(holdout),flush=True)
        readonly.close()
    stats = dict(
        project="DRNAS MI-LTM4 trajectories v0.1",
        training_generation=generation, smoke=smoke, paired_native=paired,
        train_source_formulas=len(train),holdout_source_formulas=len(holdout),
        source_SHA_disjoint=True,
        training_memory_frozen_before_holdout=True,
        repeated_fixed_holdout_not_fresh_blind=True,
        training_episodes=train_motifs,
        historical_training_source_formulas=frozen["training_formulas"],
        historical_unique_motifs=len(frozen["motifs"]),
        policy_qualified_motifs=len(frozen["positive_motifs"]),
        holdout_recognized_formulas=recognized,
        holdout_matched_motif_occurrences=matches,
        holdout_observed_motif_occurrences=holdout_motifs,
        holdout_recommended_chain_formulas=activated,
        mean_offline_probe_s=round(statistics.mean(probe_times),7)
                             if probe_times else 0,
        by_family=by_family,
        native_training_reference=_summary(native_train),
        native_holdout_ungated_reference=_summary(native_holdout),
        memory_policy_sha256=frozen["sha256"],
        limitations=[
            "XOR algebraic trajectories only; no captured live native CDCL trail",
            "Repeated motifs are associations, not demonstrated causal benefits",
            "Offline structure recognition/probe NOT charged to native E2E/PAR2",
            "No online LTM4 gate; paired native BASE-vs-MI_CHAIN is ungated",
            "No learned clauses or SAT/UNSAT claims transferred across formulas",
            "Only generated six-family cohort; no SAT Competition generalization"])
    dest = ROOT/("MI_LTM4_SMOKE.json" if smoke else "MI_LTM4_FINAL.json")
    dest.write_text(json.dumps(stats,sort_keys=True,indent=2)+"\n")
    print("MI_LTM4_FINAL",json.dumps(stats,sort_keys=True),flush=True)
    return stats


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--paired", action="store_true",
                   help="real ungated BASE-vs-MI_CHAIN native E2E control")
    p.add_argument("--generation", type=int, default=1)
    args=p.parse_args()
    run(generation=args.generation, smoke=args.smoke, paired=args.paired)
