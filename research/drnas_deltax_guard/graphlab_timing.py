#!/usr/bin/env python3
"""DELTAX GRAPH-LAB timing A/B/C: frozen GRAPH-LAB1 inputs and GUARD1 binary.

Measure end-to-end solver subprocess wall times (including startup, proof writing,
and solver work, but EXCLUDING independent SAT/DRAT checks) on the SAME 20
source-CNF graphs, serially on ONE logical CPU per runner. Each graph has 15
deterministically order-shuffled paired triplets:
  join (DELTAX off), deltax (unguarded), deltax-guard (guard enabled).

Independent original-source SAT model and original-source UNSAT DRAT checks are
kept on EVERY trial. Report robust per-graph medians, paired differences,
source-cluster bootstrap CIs, and all raw runs. No promotion or claims beyond
this retrospective synthetic graph selection.
"""
import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys

R = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(R / "research/drnas_deltax_guard"),
                str(R / "research/drnas_deltax"),
                str(R / "research")]
import graphlab_paired as G
from drnas_deltax_guard import paired as P

ARMS = ("join", "deltax", "deltax-guard")
REPS = 15
SHARDS = 4
CAP_S = 4.0
ORIGINAL_GRAPH_MANIFEST_SHA256 = "c4fd945407d52090a042c4130571baba859db972863b893792b6a28ea91d21d9"


def emit(tag, body):
    print(tag + " " + json.dumps(body, sort_keys=True), flush=True)


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def get_sources():
    sources, manifest_hash = G.manifest()
    assert manifest_hash == ORIGINAL_GRAPH_MANIFEST_SHA256, (
        "NOT_EXACT_GRAPHLAB1_SOURCE_MANIFEST", manifest_hash)
    assert len(sources) == 20 and len({s["sha256"] for s in sources}) == 20
    return sources, manifest_hash


def pinned_cpu():
    allowed = os.sched_getaffinity(0)
    os.sched_setaffinity(0, {min(allowed)})
    result = sorted(os.sched_getaffinity(0))
    assert len(result) == 1, ("MORE_THAN_ONE_LOGICAL_CPU", result)
    return result


def shuffled_arms(s, rep):
    order = list(ARMS)
    rng = random.Random(int(s["sha256"][:16], 16) ^ (rep * 0x9E3779B97F4A7C15))
    rng.shuffle(order)
    return order


def run_shard(index):
    assert 0 <= index < SHARDS
    cpu = pinned_cpu()
    sources, manifest_hash = get_sources()
    selected = [s for i, s in enumerate(sources) if i % SHARDS == index]
    folder = R / "graphlab_timing_shards" / str(index)
    folder.mkdir(parents=True, exist_ok=False)
    save(folder / "manifest.json", {
        "shard": index, "source_manifest_sha256": manifest_hash,
        "arms": list(ARMS), "reps": REPS, "cap_s": CAP_S,
        "sources": [s["sha256"] for s in selected],
        "single_logical_cpu": cpu, "solver_processes_serial": True,
        "native_binary_sha256": P.sha(P.BINARY),
        "independent_drat_checker_sha256": P.sha(P.DRAT),
        "frozen_graphlab1_from_run": 43598771169,
        "no_main_changes": True, "no_promotion": True,
        "retrospective_synthetic": True, "blind_holdout": False
    })
    count = 0
    verified = 0
    with (folder / "trials.jsonl").open("w") as out:
        for s in selected:
            for rep in range(REPS):
                for order_index, arm in enumerate(shuffled_arms(s, rep)):
                    row = P.trial(s, arm, CAP_S, folder / "raw")
                    G.check_result(s, row)
                    row.update({
                        "name": s["name"], "graph_kind": s["graph_kind"],
                        "graph_vertices": s["graph_vertices"],
                        "graph_edges": s["graph_edges"], "motifs": s["motifs"],
                        "rep": rep, "order": order_index,
                        "measurement": "solver_subprocess_wall_e2e_excluding_check",
                        "solver_wall_s": row["wall_e2e_s"],
                        "external_verification_s": row["proof_check_s"]
                    })
                    assert row["guard_invalid_source"] == 0
                    assert row["guard_clones_inconsistent"] == 0
                    out.write(json.dumps(row, sort_keys=True) + "\n")
                    out.flush()
                    count += 1
                    verified += int(row["verified"])
                    emit("GRAPHLAB_TIME_TRIAL", {
                        "graph": s["name"], "rep": rep, "arm": arm,
                        "wall_ms": round(1000 * row["wall_e2e_s"], 4),
                        "verification_ms": round(1000 * row["proof_check_s"], 4),
                        "verified": row["verified"],
                        "decisions": row["decisions"],
                        "conflicts": row["conflicts"],
                        "guard_checks": row["guard_checks"]
                    })
    assert count == len(selected) * REPS * len(ARMS)
    assert verified == count, ("UNVERIFIED_TRIAL", verified, count)
    emit("GRAPHLAB_TIME_SHARD_PASS", {
        "shard": index, "sources": len(selected),
        "trials": count, "verified": verified,
        "reps": REPS, "single_cpu": cpu
    })


def bootstrap_ratio_ci(graphs, reference, comparison, draws=5000):
    """Source-cluster bootstrap of geometric mean median wall-time ratios."""
    logs = [
        math.log(g["median_wall_ms"][reference] / g["median_wall_ms"][comparison])
        for g in graphs
    ]
    observed = math.exp(statistics.mean(logs))
    rng = random.Random(611141227)
    sims = []
    n = len(logs)
    for _ in range(draws):
        sims.append(math.exp(sum(logs[rng.randrange(n)] for _ in range(n)) / n))
    sims.sort()
    return {
        "geomean_speedup_ref_over_comparison": observed,
        "ci95_source_cluster": [sims[int(draws * .025)],
                                sims[int(draws * .975)]],
        "bootstrap_draws": draws,
        "speedup_gt_1_ci95": sims[int(draws * .025)] > 1.0
    }


def aggregate():
    sources, manifest_hash = get_sources()
    manifests, trials = [], []
    for index in range(SHARDS):
        folder = R / "graphlab_timing_downloads" / (
            "graphlab-time-shard-" + str(index)) / "graphlab_timing_shards" / str(index)
        m = json.loads((folder / "manifest.json").read_text())
        manifests.append(m)
        trials += [json.loads(line) for line in
                   (folder / "trials.jsonl").read_text().splitlines()]
    for m in manifests:
        assert m["source_manifest_sha256"] == manifest_hash
        assert m["arms"] == list(ARMS) and m["reps"] == REPS
        assert m["cap_s"] == CAP_S and len(m["single_logical_cpu"]) == 1
        assert m["solver_processes_serial"] and not m["blind_holdout"]
        assert m["retrospective_synthetic"] and m["no_promotion"]
        assert m["native_binary_sha256"] == manifests[0]["native_binary_sha256"]
        assert m["independent_drat_checker_sha256"] == manifests[0]["independent_drat_checker_sha256"]
    keys = {(s["sha256"], rep, arm) for s in sources
            for rep in range(REPS) for arm in ARMS}
    got = [(r["sha256"], r["rep"], r["arm"]) for r in trials]
    assert len(got) == len(keys) == 20 * REPS * len(ARMS)
    assert len(set(got)) == len(got) and set(got) == keys
    bykey = {(r["sha256"], r["rep"], r["arm"]): r for r in trials}
    assert all(r["verified"] for r in trials), "UNVERIFIED_OR_TIMEOUT"
    assert all(r["guard_invalid_source"] == r["guard_clones_inconsistent"] == 0
               for r in trials), "UNSOUND_GUARD"
    verified_verdicts = collections.defaultdict(set)
    for r in trials:
        verified_verdicts[r["sha256"]].add(r["status"])
    assert all(len(v) == 1 for v in verified_verdicts.values()), "CONTRADICTORY_CERTIFICATES"
    per_graph = []
    for s in sources:
        per_arm = {arm: [bykey[(s["sha256"], rep, arm)] for rep in range(REPS)]
                   for arm in ARMS}
        median_wall = {
            arm: 1000 * statistics.median(r["solver_wall_s"] for r in per_arm[arm])
            for arm in ARMS
        }
        mean_wall = {
            arm: 1000 * statistics.mean(r["solver_wall_s"] for r in per_arm[arm])
            for arm in ARMS
        }
        median_paired_diff = {
            "guard_minus_join_ms": 1000 * statistics.median(
                per_arm["deltax-guard"][rep]["solver_wall_s"] -
                per_arm["join"][rep]["solver_wall_s"] for rep in range(REPS)),
            "guard_minus_deltax_ms": 1000 * statistics.median(
                per_arm["deltax-guard"][rep]["solver_wall_s"] -
                per_arm["deltax"][rep]["solver_wall_s"] for rep in range(REPS))
        }
        per_graph.append({
            "name": s["name"], "kind": s["graph_kind"],
            "vertices": s["graph_vertices"], "sha256": s["sha256"],
            "median_wall_ms": median_wall,
            "mean_wall_ms": mean_wall,
            "median_paired_difference": median_paired_diff,
            "speedup_join_over_guard": median_wall["join"] / median_wall["deltax-guard"],
            "speedup_deltax_over_guard": median_wall["deltax"] / median_wall["deltax-guard"],
            "sum_guard_checks": sum(r["guard_checks"] for r in per_arm["deltax-guard"]),
            "sum_guard_accepted": sum(r["guard_accepted"] for r in per_arm["deltax-guard"]),
            "sum_guard_rejected": sum(r["guard_rejected"] for r in per_arm["deltax-guard"]),
            "decisions": {a: per_arm[a][0]["decisions"] for a in ARMS},
            "conflicts": {a: per_arm[a][0]["conflicts"] for a in ARMS},
            "verdict": per_arm["join"][0]["status"]
        })
    totals = {}
    for arm in ARMS:
        rr = [r for r in trials if r["arm"] == arm]
        totals[arm] = {
            "trials": len(rr), "verified": sum(r["verified"] for r in rr),
            "sum_wall_s": sum(r["solver_wall_s"] for r in rr),
            "median_trial_wall_ms": 1000 * statistics.median(r["solver_wall_s"] for r in rr),
            "sum_independent_verification_s": sum(r["external_verification_s"] for r in rr),
            "sum_par2_verified_s": sum(r["par2_verified_s"] for r in rr),
            "sum_decisions": sum(r["decisions"] for r in rr),
            "sum_conflicts": sum(r["conflicts"] for r in rr)
        }
    report = {
        "status": "COMPLETE", "graphs": len(sources), "trials": len(trials),
        "reps_per_graph_arm": REPS, "arms": list(ARMS),
        "all_source_cnf_sat_and_drat_proofs_verified": True,
        "one_logical_cpu_per_runner": True,
        "solver_processes_serial": True,
        "source_manifest_sha256": manifest_hash,
        "native_binary_sha256": manifests[0]["native_binary_sha256"],
        "retrospective_synthetic": True, "blind_holdout": False,
        "no_promotion": True, "on_off_same_binary": True,
        "solver_wall_excludes_independent_verifier": True,
        "solver_wall_includes_process_startup_and_proof_emission": True,
        "totals": totals,
        "join_vs_guard": bootstrap_ratio_ci(per_graph, "join", "deltax-guard"),
        "deltax_vs_guard": bootstrap_ratio_ci(per_graph, "deltax", "deltax-guard"),
        "graphs_guard_faster_than_join": sum(
            g["speedup_join_over_guard"] > 1 for g in per_graph),
        "graphs_guard_faster_than_deltax": sum(
            g["speedup_deltax_over_guard"] > 1 for g in per_graph),
        "per_graph": per_graph
    }
    save(R / "graphlab_timing_final" / "report.json", report)
    save(R / "graphlab_timing_final" / "trials.json", trials)
    emit("GRAPHLAB_TIME_FINAL", {k: v for k, v in report.items() if k != "per_graph"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("shard", "aggregate"))
    parser.add_argument("--shard", type=int, default=0)
    options = parser.parse_args()
    if options.stage == "shard":
        run_shard(options.shard)
    else:
        aggregate()
