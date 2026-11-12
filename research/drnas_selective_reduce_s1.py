#!/usr/bin/env python3
"""DRNAS Selective Reduction S1: proof-checked SAT shortcut, safe CaDiCaL fallback.

The gate uses ONLY original CNF bytes, not filenames, benchmark group labels,
ground truth, run seed, or holdout outcomes. This is a fixed pre-registered
heuristic, not learned on the test set. The shortcut validates a full SAT witness
on the original CNF before claiming SAT. Reference UNSAT without an independent
certificate receives timeout PAR2. First evaluation uses disjoint synthetic SAT
instances with shared generators, followed by an exploratory SAT2024 audit.
"""
import argparse
import hashlib
import json
import os
import pathlib
import random
import statistics
import time
import collections

import drnas_ltm12_dynamic as D

B, L = D.B, D.L
ROOT = pathlib.Path("drnas_selective_reduce_s1")
CAP = 1.5
ARMS = ("SELECTIVE_REDUCE", "CaDiCaL", "Kissat", "CryptoMiniSat", "REDUCE_KISSAT")
SEEDS = (17, 29)
PRECHECK_MAX_BYTES = 64 * 1024
PRECHECK_CLAUSES = 48

def emit(label, value):
    print(label + " " + json.dumps(value, sort_keys=True, separators=(",", ":")), flush=True)

def precheck(path):
    """Bounded screening only; never used to claim SAT or UNSAT.

    DIMACS clauses may span lines or share a line. Parse token stream until
    48 completed clauses. Return a structural *hint* for a certified attempt.
    """
    if path.stat().st_size > PRECHECK_MAX_BYTES:
        return None
    widths = set()
    width = 0
    seen = 0
    try:
        with path.open("r", encoding="ascii", errors="replace") as fd:
            header = False
            for raw in fd:
                line = raw.strip()
                if not line or line.startswith(("c", "%")):
                    continue
                if line.startswith("p "):
                    if header:
                        return None
                    parts = line.split()
                    if len(parts) != 4 or parts[1] != "cnf":
                        return None
                    header = True
                    continue
                if not header:
                    return None
                for token in line.split():
                    lit = int(token)
                    if lit == 0:
                        widths.add(width)
                        seen += 1
                        width = 0
                        if seen >= PRECHECK_CLAUSES:
                            break
                    else:
                        width += 1
                        if width > 3:
                            return None
                if seen >= PRECHECK_CLAUSES:
                    break
    except (OSError, ValueError):
        return None
    if seen < 2:
        return None
    if widths <= {1, 2} and 2 in widths:
        return "binary_candidate"
    if widths == {3}:
        return "xor3_candidate"
    return None

def checked_original(source):
    p = pathlib.Path(source["path"])
    if hashlib.sha256(p.read_bytes()).hexdigest() != source["sha256"]:
        raise RuntimeError(f"original CNF hash mismatch id={source['id']}")
    return p

def finalize(row, arm, source, seed, cap, started, **meta):
    elapsed = time.monotonic() - started
    if elapsed > cap or row.get("status") in ("INVALID_SAT", "ERROR"):
        if row.get("status") in ("INVALID_SAT", "ERROR"):
            raise RuntimeError(f"invalid solver answer {arm} id={source['id']}")
        row.update(status="UNKNOWN", verified=False, php_math_certified=False)
    row.update(id=source["id"], seed=seed, split=source["split"],
               arm=arm, cap_s=cap, e2e_s=round(elapsed, 6),
               original_cnf_sha256=source["sha256"], **meta)
    return B.with_metrics(row, cap)

def selective(source, seed, cap):
    start = time.monotonic()
    p = checked_original(source)
    before = time.monotonic()
    hint = precheck(p)
    precheck_s = time.monotonic() - before
    operator = None
    proof_s = 0.0
    if hint is not None and cap - (time.monotonic() - start) > 0.20:
        before = time.monotonic()
        # D.shortcut independently checks a complete witness against ORIGINAL CNF.
        # It returns an operator name only after witness verification.
        operator = D.shortcut(p)
        proof_s = time.monotonic() - before
    fallback = operator is None
    if operator is not None:
        row = dict(status="SAT_VERIFIED", verified=True, php_math_certified=False,
                   decisions=0, conflicts=0)
    else:
        remaining = cap - (time.monotonic() - start) - 0.12
        if remaining < 0.25:
            row = dict(status="UNKNOWN", verified=False, php_math_certified=False,
                       decisions=None, conflicts=None)
        else:
            row = B.run_solver("CaDiCaL", source, seed, remaining)
    out = finalize(row, "SELECTIVE_REDUCE", source, seed, cap, start,
                   candidate_hint=hint, operator=operator, fallback=fallback,
                   precheck_s=round(precheck_s, 7), proof_s=round(proof_s, 7))
    if source.get("known_sat") and out["status"].startswith("UNSAT"):
        raise RuntimeError("UNSAT contradicts validated planted SAT witness")
    return out

def baseline(arm, source, seed, cap):
    start = time.monotonic()
    if arm == "REDUCE_KISSAT":
        # Keep original implementation as a reproducible reference on synthetic cases.
        oldcap = D.CAP
        try:
            D.CAP = cap
            row = D.trial(arm, source, seed)
        finally:
            D.CAP = oldcap
        row.update(operator=row.get("operator"), fallback=row.get("operator") is None)
        return row
    row = B.run_solver(arm, source, seed, max(0.25, cap - 0.12))
    out = finalize(row, arm, source, seed, cap, start,
                   candidate_hint=None, operator=None, fallback=False,
                   precheck_s=0.0, proof_s=0.0)
    if source.get("known_sat") and out["status"].startswith("UNSAT"):
        raise RuntimeError("UNSAT contradicts validated planted SAT witness")
    return out

def trial(arm, source, seed, cap):
    return selective(source, seed, cap) if arm == "SELECTIVE_REDUCE" else baseline(arm, source, seed, cap)

def summary(rows, cap, arms):
    totals = B.metrics(rows, cap, arms)
    best = min(("CaDiCaL", "Kissat", "CryptoMiniSat"), key=lambda name: totals[name]["PAR2_verified_s"])
    paired = {(r["id"], r["seed"], r["arm"]): r for r in rows}
    regrets = {}
    for arm in arms:
        if arm == best:
            continue
        deltas = []
        regressions = improvements = 0
        for row in rows:
            if row["arm"] != arm:
                continue
            ref = paired[(row["id"], row["seed"], best)]
            deltas.append(row["PAR2_verified_s"] - ref["PAR2_verified_s"])
            regressions += row["PAR2_verified_s"] > ref["PAR2_verified_s"] * 1.1 + .002
            improvements += row["PAR2_verified_s"] + .002 < ref["PAR2_verified_s"] * .9
        regrets[arm] = dict(
            mean_regret_s=round(statistics.mean(deltas), 7),
            regressions_over_10pct=regressions,
            improved_over_10pct=improvements)
    s = [r for r in rows if r["arm"] == "SELECTIVE_REDUCE"]
    return dict(best_reference=best, totals=totals, regressions_vs_best=regrets,
                selective_details=dict(
                    trials=len(s), shortcut_verified=sum(r["operator"] is not None and r["verified"] for r in s),
                    fallbacks=sum(r["fallback"] for r in s),
                    binary_hints=sum(r["candidate_hint"] == "binary_candidate" for r in s),
                    xor3_hints=sum(r["candidate_hint"] == "xor3_candidate" for r in s),
                    precheck_total_s=round(sum(r["precheck_s"] for r in s), 6),
                    proof_attempt_total_s=round(sum(r["proof_s"] for r in s), 6),
                    median_precheck_ms=round(1000 * statistics.median(r["precheck_s"] for r in s), 5),
                    max_precheck_ms=round(1000 * max(r["precheck_s"] for r in s), 5)),
                selective_vs_best_x=round(
                    totals[best]["PAR2_verified_s"] /
                    max(totals["SELECTIVE_REDUCE"]["PAR2_verified_s"], 1e-9), 6),
                selective_relative_PAR2_reduction_pct=round(
                    100 * (1 - totals["SELECTIVE_REDUCE"]["PAR2_verified_s"] /
                           max(totals[best]["PAR2_verified_s"], 1e-9)), 3))

def synthetic(root, seed):
    sources = D.collect(root, seed)
    rows = []
    (root / "manifest_extra.json").write_text(json.dumps(dict(
        benchmark="synthetic planted SAT", selection="all 32 held-out sources",
        run_seed=seed, precheck_bytes=PRECHECK_MAX_BYTES,
        precheck_clause_window=PRECHECK_CLAUSES, frozen_gate=True,
        no_outcome_based_routing=True, used_prior_generator_family=True,
        globally_blind=False), indent=2) + "\n")
    with (root / "holdout.jsonl").open("w") as fd:
        for source in sources:
            if source["split"] != "holdout":
                continue
            source["known_sat"] = True
            for rep, random_seed in enumerate(SEEDS):
                rotated = list(ARMS)
                shift = (source["id"] + rep) % len(rotated)
                for arm in rotated[shift:] + rotated[:shift]:
                    row = trial(arm, source, random_seed, CAP)
                    row.update(rep=rep, group=source["group"],
                               variant=source["variant"], tier=source["tier"],
                               shard=(source["id"] - 68) // 8)
                    rows.append(row)
                    fd.write(json.dumps(row, sort_keys=True) + "\n")
                    fd.flush()
    B.check_contradictions(rows)
    result = summary(rows, CAP, ARMS)
    result.update(corpus="synthetic planted SAT", source_count=32, holdout_reps=2,
                  total_rows=len(rows), one_logical_cpu=True,
                  caveat="Shared generators and prior observed group results; exploratory, not globally blind.")
    result["groups"] = {group: summary([r for r in rows if r["group"] == group], CAP, ARMS)
                        for group in D.VARIANTS}
    result["shards"] = {str(i): summary([r for r in rows if r["shard"] == i], CAP, ARMS)
                        for i in range(4)}
    (root / "report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    emit("SELECTIVE_REDUCE_SYNTH_FINAL", result)
    return result

def official(root):
    """Original official CNF check. 12 compact cases chosen WITHOUT outcome labels.

    This archive has been used in earlier DRNAS experiments; explicitly reused
    exploratory evaluation. No novel blind performance claim.
    """
    B.ROOT = root
    sources = B.collect()
    chosen = sorted(sources, key=lambda s: (s["compressed_bytes"], s["sha256"]))[:12]
    cap = 6.0
    arms = ("SELECTIVE_REDUCE", "CaDiCaL", "Kissat", "CryptoMiniSat")
    rows = []
    (root / "official_probe_selection.json").write_text(json.dumps(dict(
        archive=B.ARCHIVE, selected_ids=[s["id"] for s in chosen],
        selection="12 smallest compressed original CNFs from fixed official100 selection",
        evaluation_type="exploratory reused SAT2024 archive, not blind",
        cap_s=cap, one_cpu=True, run_seed=17), indent=2) + "\n")
    with (root / "official_holdout.jsonl").open("w") as fd:
        for source in chosen:
            for arm in arms:
                row = trial(arm, source, 17, cap)
                rows.append(row)
                fd.write(json.dumps(row, sort_keys=True) + "\n")
                fd.flush()
                emit("SELECTIVE_REDUCE_OFFICIAL_TRIAL",
                     dict(arm=arm, id=source["id"], status=row["status"],
                          PAR2_verified_s=row["PAR2_verified_s"],
                          operator=row.get("operator"),
                          overhead_s=row.get("precheck_s", 0) + row.get("proof_s", 0)))
    B.check_contradictions(rows)
    result = summary(rows, cap, arms)
    result.update(corpus="SAT Competition 2024 original CNF, selected 12",
                  source_count=len(chosen), one_logical_cpu=True, repetitions=1,
                  independently_verified_UNSAT="only independently checked math PHP",
                  globally_blind=False)
    (root / "report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    emit("SELECTIVE_REDUCE_OFFICIAL_FINAL", result)
    return result

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "proof.cnf"
        p.write_text("p cnf 3 3\n1 2 0\n-1 2 0\n-2 0\n")
        assert precheck(p) == "binary_candidate"
        p.write_text("p cnf 3 1\n1 2 3 0\n")
        assert precheck(p) is None
        p.write_text("p cnf 3 4\n1 2 3 0\n1 -2 -3 0\n-1 2 -3 0\n-1 -2 3 0\n")
        assert precheck(p) == "xor3_candidate"
        assert D.shortcut(p) == "gf2_elimination"
        p.write_text("p cnf 3 3\n1 0\n-1 0\n2 0\n")
        assert D.shortcut(p) is None
        p.write_text("p cnf 3 4\n1 2 0\n3 0\n1 -2 3 0\n2 0\n")
        assert precheck(p) is None
    emit("SELECTIVE_REDUCE_SELFTEST_PASS", dict(
        binary_probe=True, xor_probe=True,
        verified_mathematical_witness=True, contradiction_safe=True))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--seed", type=int, default=82021112)
    parser.add_argument("--skip-official", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    L.setup_source()
    ROOT.mkdir(exist_ok=False)
    results = {"synthetic": synthetic(ROOT / "synthetic", args.seed)}
    if not args.skip_official:
        results["official"] = official(ROOT / "official")
    (ROOT / "combined.json").write_text(json.dumps(dict(
        policy="S1 fixed source-only gate, 64 KiB and 48 sample clauses",
        one_cpu=True, globally_blind=False,
        results={k: dict(best_reference=v["best_reference"],
                         reduction_pct=v["selective_relative_PAR2_reduction_pct"],
                         shortcut_verified=v["selective_details"]["shortcut_verified"],
                         PAR2=v["totals"]) for k,v in results.items()}),
        indent=2, sort_keys=True) + "\n")
    emit("SELECTIVE_REDUCE_DONE", dict(
        checks=list(results), verified_par2_goal_met_exploratory={
            k: v["selective_relative_PAR2_reduction_pct"] >= 30 for k, v in results.items()}))

if __name__ == "__main__":
    main()
