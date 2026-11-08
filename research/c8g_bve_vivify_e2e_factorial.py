#!/usr/bin/env python3
"""C8G: end-to-end BVE x vivification factorial on three frozen C8 SAT sources.

This is a development-cohort causal follow-up, not blind validation. It uses
pinned upstream CaDiCaL 1.7.3 pristine/instrumented binaries, source-locked
original CNFs, SAT-witness replay, and real wall-time PAR2. The candidate-skip
arms only decline selected BVE attempts; they add no clauses or learned state.
C8F provides bounded first-event CDCL telemetry separately. This benchmark
checks the full solve after isolating the no-elim/vivify option interaction.
"""
from __future__ import annotations
import collections, hashlib, json, pathlib, random, sys
import c8c_pivot_causal_audit as c8c
import c7_standard_solver_bve_crosscheck as c7

PROTO = "DRNAS-C8G-3SHA-13ARM-3REP-E2E-BVE-VIVIFY-FACTORIAL-v1"
OUT = pathlib.Path("c8g_out")
REPS = 3
CAP_S = 25.0
ARMS = (
    "default", "instrumented_control",
    "noelim", "noelim_force_vivify", "noelim_novivify", "novivify",
    "skip_first_candidate", "skip_first_8_candidates",
    "skip_first_success", "skip_first_8_success", "skip_late_8_candidates",
    "skip_first_candidate_novivify", "skip_first_8_candidates_novivify",
)

def need(ok, msg):
    if not ok:
        raise RuntimeError("C8G_FAIL_CLOSED " + str(msg))

def case(i):
    c = c8c.source(i)
    need(c7.digest(c["path"]) == c["sha256"], "original CNF SHA mismatch")
    need(c.get("expected_status", "SAT") == "SAT", "C8G source must be SAT")
    p = c8c.profiles(i)
    need(p["sha256"] == c["sha256"], "first-event profile/source mismatch")
    return c, p

def configuration(arm, choices):
    need(arm in ARMS, "unregistered arm")
    opts = []
    env = {}
    binary = "plain"
    key = arm.removesuffix("_novivify")
    if arm == "instrumented_control":
        binary = "patched"
    elif arm == "noelim":
        opts = ["--no-elim"]
    elif arm == "noelim_force_vivify":
        opts = ["--no-elim", "--vivify"]
    elif arm == "noelim_novivify":
        opts = ["--no-elim", "--no-vivify"]
    elif arm == "novivify":
        opts = ["--no-vivify"]
    elif arm not in ("default",):
        binary = "patched"
        skip = choices[key]
        need(bool(skip), "empty registered candidate skip set for " + arm)
        env["DRNAS_C8C_SKIP_VARS"] = ",".join(map(str, skip))
        if arm.endswith("_novivify"):
            opts = ["--no-vivify"]
    return binary, opts, env

def bench(shard):
    c, p = case(shard)
    choices = p["skipped_candidate_order_development_only"]
    need(set(ARMS) <= set(ARMS), "arm registration failure")
    OUT.mkdir(exist_ok=True)
    rows = []
    seed = int(hashlib.sha256((PROTO + "|" + c["sha256"]).encode()).hexdigest()[:8], 16)
    for rep in range(REPS):
        order = list(ARMS)
        order_seed = seed ^ (rep * 0x9E3779B1)
        random.Random(order_seed).shuffle(order)
        for order_index, arm in enumerate(order):
            binary, opts, env = configuration(arm, choices)
            result = c8c.run_bin(c, binary, opts=opts, env_extra=env,
                                 verbose=False, cap=CAP_S)
            row = dict(protocol=PROTO, source_index=shard, gbd=c["gbd"],
                       source_sha256=c["sha256"], arm=arm, rep=rep,
                       run_order_seed=order_seed, order_index=order_index,
                       independent_seed_applied=False, cap_s=CAP_S,
                       route_header_charged=True, binary=binary, options=opts,
                       selected_skipped_candidate_variables=(
                           choices.get(arm.removesuffix("_novivify"), [])
                           if arm not in ("default", "instrumented_control",
                                          "noelim", "noelim_force_vivify",
                                          "noelim_novivify", "novivify") else []),
                       status=result["status"],
                       original_SAT_witness_verified=
                           result["original_sat_model_verified"],
                       wall_s=result["wall_s"], PAR2_s=result["PAR2_s"])
            rows.append(row)
            print("C8G_TRIAL " + json.dumps(row, sort_keys=True), flush=True)
    need(len(rows) == len(ARMS) * REPS, "incorrect trial count")
    path = OUT / ("bench-%d.json" % shard)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    print("C8G_BENCH_SHARD_PASS %d %d" % (shard, len(rows)), flush=True)

def audit():
    paths = sorted(OUT.glob("bench-*.json"))
    rows = []
    for path in paths:
        rows.extend(json.loads(path.read_text()))
    need(len(rows) == 3 * len(ARMS) * REPS,
         "expected complete three-source factorial")
    need(len({r["source_sha256"] for r in rows}) == 3, "source set mismatch")
    need(all(r["original_SAT_witness_verified"] for r in rows
             if r["status"] == "SAT"), "unverified SAT witness")
    need(not any(r["status"] == "UNSAT" for r in rows),
         "UNSAT contradicts frozen SAT source")
    need(all(r["route_header_charged"] for r in rows),
         "E2E accounting must include wrapper/header")
    by_arm = collections.defaultdict(list)
    by_source_arm = collections.defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)
        by_source_arm[(r["gbd"], r["arm"])].append(r)
    scores = {}
    for arm in ARMS:
        xs = by_arm[arm]
        need(len(xs) == 9, "arm missing repetitions: " + arm)
        scores[arm] = dict(PAR2_s=round(sum(x["PAR2_s"] for x in xs), 6),
                           actual_wall_s=round(sum(x["wall_s"] for x in xs), 6),
                           solved=sum(x["status"] == "SAT" for x in xs),
                           timeouts=sum(x["status"] != "SAT" for x in xs),
                           trials=len(xs))
    reference = scores["default"]["PAR2_s"]
    for value in scores.values():
        value["speedup_vs_default_x"] = round(
            reference / value["PAR2_s"], 6) if value["PAR2_s"] else None
    per_source = []
    for gbd in sorted({r["gbd"] for r in rows}):
        arms = {}
        for arm in ARMS:
            xs = by_source_arm[(gbd, arm)]
            arms[arm] = dict(PAR2_s=round(sum(x["PAR2_s"] for x in xs), 6),
                             actual_wall_s=round(sum(x["wall_s"] for x in xs), 6),
                             solved=sum(x["status"] == "SAT" for x in xs),
                             timeouts=sum(x["status"] != "SAT" for x in xs))
        per_source.append(dict(gbd=gbd, arms=arms))
    report = dict(protocol=PROTO, cohort="three previously studied C8 development SAT originals; no blind claim",
                  source_count=3, cap_s=CAP_S, repeats=REPS, attempts=len(rows),
                  arms=list(ARMS), real_E2E_PAR2_including_route_header=True,
                  original_SAT_models_checked=True, independent_solver_seeds=False,
                  independent_UNSAT_LRAT=False,
                  bounded_CDCL_telemetry_source="C8F separate bounded diagnostic; not PAR2",
                  no_auto_promotion=True, scores=scores, per_source=per_source)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("C8G_FINAL " + json.dumps(dict(attempts=len(rows), scores=scores),
                                   sort_keys=True), flush=True)
    for row in per_source:
        print("C8G_CASE " + json.dumps(row, sort_keys=True), flush=True)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("bench", "audit"))
    parser.add_argument("--shard", type=int)
    args = parser.parse_args()
    if args.command == "bench":
        need(args.shard in (0, 1, 2), "invalid source shard")
        bench(args.shard)
    else:
        audit()

if __name__ == "__main__":
    main()
