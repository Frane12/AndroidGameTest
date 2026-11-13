#!/usr/bin/env python3
"""Frozen seven-arm X5.9 / COOP5 / COOP5.1 / OMEGA4.2 vs Kissat / CaDiCaL.

Retrospective REAL36 original SAT2024 CNFs, SHA-checked, one logical CPU,
matched cases/repetitions, randomized arm order. SAT original witnesses and
UNSAT DRAT independently verified when available. OMEGA UNSAT remains
UNVERIFIED because that bridge does not emit a checkable LRAT/DRAT proof.
This is a diagnostic, NOT a blind holdout or eligible for promotion.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path("research").resolve()))
import drnas_x55_cpu_real36 as B

ARMS = (
    "X59_ON", "COOP5_FIXED_ON", "COOP51_HYBRID_ON",
    "OMEGA42_COMPONENT", "OMEGA42_CLEAN", "KISSAT", "CADICAL",
)
CAP = 8.0
REPS = 2
SHARDS = 6
BIN = {
    "X59_ON": Path("cross/x59/build/drnas-x59"),
    "COOP5_FIXED_ON": Path("cross/coop/build/drnas-coop5-fixed"),
    "COOP51_HYBRID_ON": Path("cross/coop/build/drnas-coop51-hybrid"),
    "OMEGA42_COMPONENT": Path("cross/omega/mre_omega42/bin/omega42_bridge"),
    "OMEGA42_CLEAN": Path("cross/omega/mre_omega42/bin/omega42_bridge"),
    "KISSAT": Path("cross/x59/build/kissat"),
    "CADICAL": Path("cross/x59/build/cadical"),
}
CHECKER = Path("cross/x59/build/drat-trim")
EXPORTER = Path("cross/omega/mre_omega42/bin/omega42_rows")
PINNED_RUNS = {
    "x59": 43449841902, "coop51": 43524169066,
    "omega42": 43519470159, "real36_originals": 43387395060,
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def capture(args, timeout):
    start = time.perf_counter()
    proc = subprocess.Popen([str(x) for x in args], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    killed = False
    try:
        out, err = proc.communicate(timeout=max(0.1, timeout))
    except subprocess.TimeoutExpired:
        killed = True
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
    return proc.returncode, out, err, time.perf_counter() - start, killed


def run_one(src, arm, rep, cap, raw):
    cnf = Path(src["path"]).resolve()
    proof_seconds = 0.0
    extract_seconds = 0.0
    meta = {}
    error = ""
    with tempfile.TemporaryDirectory(prefix="cross_sat_") as td:
        proof = Path(td) / "proof.drat"
        tsv = Path(td) / "source.tsv"
        tsv.write_text("")
        if arm == "OMEGA42_COMPONENT":
            rc, out, err, spent, killed = capture(
                [EXPORTER.resolve(), "export", cnf, tsv.resolve()], min(5.0, cap))
            extract_seconds = spent
            if killed:
                return result(src, arm, rep, "EXTRACT_TIMEOUT", cap, cap,
                              error="Source XOR extractor timed out")
            if rc != 0:
                return result(src, arm, rep, "EXTRACT_ERROR", cap, cap,
                              error=err[-700:])
            lines = [line.split(" ", 1)[1] for line in out.splitlines()
                     if line.startswith("XORABC3_EXPORT ")]
            if len(lines) != 1:
                raise RuntimeError("OMEGA_EXTRACTOR_MISSING_CERTIFIED_EXPORT")
            payload = json.loads(lines[0])
            if (payload.get("verified") is not True
                    or payload.get("selector") != "source_frequency_only"
                    or payload.get("rows", 999999) > 32):
                raise RuntimeError("OMEGA_UNSAFE_SOURCE_EXTRACTION " + str(payload))
            meta["source_rows"] = payload["rows"]
            if extract_seconds >= cap - .10:
                return result(src, arm, rep, "EXTRACT_TIMEOUT", cap, cap,
                              extract=extract_seconds, meta=meta)
        solver_cap = max(.05, cap - extract_seconds - .04)
        if arm == "X59_ON":
            command = [BIN[arm].resolve(), cnf, "--mode", "core", "--time",
                       str(solver_cap), "--stats", "--x59-stamp-glue",
                       "--proof", proof]
        elif arm in ("COOP5_FIXED_ON", "COOP51_HYBRID_ON"):
            command = [BIN[arm].resolve(), cnf, "--mode", "core", "--time",
                       str(solver_cap), "--stats", "--x5-no-minimize",
                       "--proof", proof, "--coop4", "on", "--coop5", "on"]
        elif arm == "KISSAT":
            command = [BIN[arm].resolve(), cnf, proof]
        elif arm == "CADICAL":
            command = [BIN[arm].resolve(), "-q", "--no-binary", cnf, proof]
        else:
            mode = "component" if arm == "OMEGA42_COMPONENT" else "clean"
            command = [BIN[arm].resolve(), mode, cnf, tsv.resolve(), str(solver_cap)]

        rc, out, err, solve_seconds, killed = capture(
            command, solver_cap + .30)
        wall = solve_seconds + extract_seconds
        if killed or wall > cap:
            return result(src, arm, rep, "TIMEOUT", wall, cap,
                          extract=extract_seconds, meta=meta)
        if rc not in (0, 10, 20, 153):
            return result(src, arm, rep, "PROCESS_ERROR", wall, cap,
                          extract=extract_seconds, meta=meta,
                          error=f"exit={rc} " + err[-800:])

        if arm.startswith("OMEGA42"):
            lines = [l for l in out.splitlines() if l.startswith("OMEGA42_RESULT ")]
            if len(lines) != 1:
                return result(src, arm, rep, "PROCESS_ERROR", wall, cap,
                              extract=extract_seconds,
                              error="OMEGA result missing: " + out[-600:])
            pairs = dict(re.findall(r"([a-z0-9_]+)=([^\s]+)", lines[0]))
            answer = pairs.get("status")
            if answer not in ("SAT", "UNSAT", "UNKNOWN"):
                raise RuntimeError("OMEGA_MALFORMED_STATUS " + repr(pairs))
            meta["source_rows_actual"] = pairs.get("source_rows")
            meta["delivered_reasons"] = pairs.get("delivered_reason_count")
        else:
            answer = {0: "UNKNOWN", 10: "SAT", 20: "UNSAT",
                      153: "UNKNOWN"}[rc]

        if answer == "SAT":
            n, clauses = B.parse_cnf(raw)
            if not B.check_sat(out, clauses, n):
                raise RuntimeError("INVALID_SAT_WITNESS arm=" + arm +
                                   " source=" + src["sha256"])
            status = "SAT_VERIFIED"
        elif answer == "UNSAT":
            if arm.startswith("OMEGA42"):
                status = "UNSAT_UNVERIFIED"
            elif proof.exists() and proof.stat().st_size:
                t0 = time.perf_counter()
                try:
                    p = subprocess.run([str(CHECKER.resolve()), str(cnf),
                                        str(proof)], capture_output=True,
                                       text=True, timeout=20)
                except subprocess.TimeoutExpired:
                    status = "UNSAT_CHECK_TIMEOUT"
                else:
                    if p.returncode != 0 or "s VERIFIED" not in p.stdout:
                        raise RuntimeError("INVALID_UNSAT_PROOF arm=" + arm +
                                           " source=" + src["sha256"] + " " +
                                           (p.stdout + p.stderr)[-350:])
                    status = "UNSAT_CERTIFIED"
                proof_seconds = time.perf_counter() - t0
            else:
                status = "UNSAT_UNVERIFIED"
        else:
            status = "UNKNOWN"

        return result(src, arm, rep, status, wall, cap,
                      proof=proof_seconds, extract=extract_seconds,
                      meta=meta, error=error)


def result(src, arm, rep, status, wall, cap, proof=0.0, extract=0.0,
           meta=None, error=""):
    verified = status in ("SAT_VERIFIED", "UNSAT_CERTIFIED") and wall <= cap
    reported = status in ("SAT_VERIFIED", "UNSAT_CERTIFIED",
                          "UNSAT_UNVERIFIED", "UNSAT_CHECK_TIMEOUT") and wall <= cap
    return {
        "id": src["id"], "family": src["family"],
        "sha256": src["sha256"], "arm": arm, "rep": rep,
        "status": status, "verified": verified, "reported": reported,
        "e2e_s": round(wall, 6),
        "par2_verified_s": round(wall if verified else 2 * cap, 6),
        "par2_reported_s": round(wall if reported else 2 * cap, 6),
        "proof_check_s": round(proof, 6),
        "source_extraction_s": round(extract, 6),
        "telemetry": meta or {}, "error": error[-900:],
    }


def binary_hashes():
    return {arm: sha(path.read_bytes()) for arm, path in BIN.items()}


def source_manifest():
    sources, source_protocol = B.official_manifest()
    assert len(sources) == 36
    assert len({s["sha256"] for s in sources}) == 36
    return sources, source_protocol


def shard_run(shard, cap, reps):
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    assert 0 <= shard < SHARDS and reps == REPS and cap == CAP
    assert all(p.is_file() for p in list(BIN.values()) + [CHECKER, EXPORTER])
    sources, protocol = source_manifest()
    target = Path("cross_results") / f"shard_{shard}"
    target.mkdir(parents=True, exist_ok=False)
    selected = [s for i, s in enumerate(sources) if i % SHARDS == shard]
    manifest = {
        "dataset": "SAT2024_REAL36_ORIGINALS_RETROSPECTIVE",
        "original_manifest_sha256": protocol["manifest_sha256"],
        "selected_source_sha256": [s["sha256"] for s in selected],
        "pinned_workflow_runs": PINNED_RUNS,
        "binary_sha256": binary_hashes(),
        "extractor_sha256": sha(EXPORTER.read_bytes()),
        "cap": cap, "reps": reps, "shard": shard, "shards": SHARDS,
        "arms": list(ARMS), "one_logical_cpu": sorted(os.sched_getaffinity(0)),
        "blind_holdout": False, "promotion": False,
        "note": "OMEGA UNSAT is not independently proof-certified",
    }
    save_json(target / "manifest.json", manifest)
    done = 0
    answers = collections.defaultdict(set)
    with (target / "trials.jsonl").open("w") as fd:
        for src in selected:
            raw = Path(src["path"]).read_bytes()
            assert sha(raw) == src["sha256"]
            for rep in range(reps):
                order = list(ARMS)
                random.Random(int(src["sha256"][:16], 16) + 10007 * rep).shuffle(order)
                for arm in order:
                    trial = run_one(src, arm, rep, cap, raw)
                    if trial["status"] in ("SAT_VERIFIED", "UNSAT_CERTIFIED"):
                        answers[(src["sha256"], rep)].add(
                            "SAT" if trial["status"] == "SAT_VERIFIED" else "UNSAT")
                    if len(answers[(src["sha256"], rep)]) > 1:
                        raise RuntimeError("CONTRADICTORY_VERIFIED_SAT_UNSAT " +
                                           src["sha256"])
                    if trial["status"] == "UNSAT_UNVERIFIED" and "SAT" in answers[(src["sha256"], rep)]:
                        raise RuntimeError("OMEGA_UNVERIFIED_UNSAT_CONTRADICTS_SAT " +
                                           src["sha256"])
                    fd.write(json.dumps(trial, sort_keys=True) + "\n")
                    fd.flush()
                    done += 1
                print("CROSS_PROGRESS", json.dumps(
                    {"shard": shard, "id": src["id"], "rep": rep,
                     "completed": done, "expected": len(selected) * reps * len(ARMS)}),
                    flush=True)
    assert done == len(selected) * reps * len(ARMS)
    print("CROSS_SHARD_PASS", json.dumps(
        {"shard": shard, "sources": len(selected), "trials": done}), flush=True)


def aggregate():
    sources, protocol = source_manifest()
    rows, manifests = [], []
    for idx in range(SHARDS):
        root = Path("cross_downloads") / f"cross-shard-{idx}" / "cross_results" / f"shard_{idx}"
        manifest = json.loads((root / "manifest.json").read_text())
        manifests.append(manifest)
        rows.extend(json.loads(s) for s in
                    (root / "trials.jsonl").read_text().splitlines())
    for m in manifests:
        assert m["pinned_workflow_runs"] == PINNED_RUNS
        assert m["original_manifest_sha256"] == protocol["manifest_sha256"]
        assert m["binary_sha256"] == manifests[0]["binary_sha256"]
        assert m["extractor_sha256"] == manifests[0]["extractor_sha256"]
        assert m["reps"] == REPS and m["cap"] == CAP
        assert m["arms"] == list(ARMS) and m["blind_holdout"] is False
        assert len(m["one_logical_cpu"]) == 1
    expected = {(s["sha256"], rep, arm) for s in sources
                for rep in range(REPS) for arm in ARMS}
    keys = [(r["sha256"], r["rep"], r["arm"]) for r in rows]
    assert len(rows) == len(expected) == 504
    assert len(set(keys)) == len(keys) and set(keys) == expected
    bysha = {s["sha256"]: s for s in sources}
    for r in rows:
        assert r["family"] == bysha[r["sha256"]]["family"]
    verified_per_src = collections.defaultdict(set)
    for r in rows:
        if r["status"] in ("SAT_VERIFIED", "UNSAT_CERTIFIED"):
            verified_per_src[r["sha256"]].add(
                "SAT" if r["status"] == "SAT_VERIFIED" else "UNSAT")
    if any(len(v) > 1 for v in verified_per_src.values()):
        raise RuntimeError("CROSS_ARM_VERIFIED_SAT_UNSAT_CONTRADICTION")
    for r in rows:
        if r["status"] == "UNSAT_UNVERIFIED" and "SAT" in verified_per_src[r["sha256"]]:
            raise RuntimeError("OMEGA_UNVERIFIED_UNSAT_CONTRADICTS_VERIFIED_SAT")
    overall = {}
    for arm in ARMS:
        rr = [r for r in rows if r["arm"] == arm]
        counts = dict(collections.Counter(r["status"] for r in rr))
        overall[arm] = {
            "attempts": len(rr),
            "verified": sum(r["verified"] for r in rr),
            "sat_verified": counts.get("SAT_VERIFIED", 0),
            "unsat_certified": counts.get("UNSAT_CERTIFIED", 0),
            "unsat_unverified": counts.get("UNSAT_UNVERIFIED", 0),
            "reported_solved": sum(r["reported"] for r in rr),
            "par2_verified_s": round(sum(r["par2_verified_s"] for r in rr), 6),
            "par2_reported_s": round(sum(r["par2_reported_s"] for r in rr), 6),
            "source_extraction_s": round(sum(r["source_extraction_s"] for r in rr), 6),
            "proof_check_s": round(sum(r["proof_check_s"] for r in rr), 6),
            "statuses": counts,
        }
    families = sorted({s["family"] for s in sources})
    by_arm_family = {}
    for arm in ARMS:
        by_arm_family[arm] = {
            f: sum(r["par2_verified_s"] for r in rows if r["arm"] == arm and r["family"] == f)
            for f in families
        }
    rng = random.Random(513242)
    bootstrap_draws = [[rng.choice(families) for _ in families] for _ in range(1200)]
    comparisons = {}
    for baseline in ("KISSAT", "CADICAL"):
        for arm in ARMS:
            if arm == baseline:
                continue
            base = sum(by_arm_family[baseline].values())
            tested = sum(by_arm_family[arm].values())
            gain = (base - tested) / base
            bs = []
            for draw in bootstrap_draws:
                b = sum(by_arm_family[baseline][f] for f in draw)
                t = sum(by_arm_family[arm][f] for f in draw)
                bs.append((b-t)/b if b else 0)
            bs.sort()
            comparisons[arm + "_vs_" + baseline] = {
                "relative_PAR2_gain": round(gain, 6),
                "family_bootstrap_95": [round(bs[30], 6), round(bs[1169], 6)],
                "independent_families": len(families),
            }
    errors = [r for r in rows if "ERROR" in r["status"]]
    report = {
        "status": "COMPLETE_WITH_SOLVER_ERRORS" if errors else "COMPLETE",
        "sources": len(sources), "families": len(families), "reps": REPS,
        "cap_s": CAP, "trials": len(rows), "arms": list(ARMS),
        "overall": overall, "comparisons": comparisons,
        "pinned_workflow_runs": PINNED_RUNS,
        "binary_sha256": manifests[0]["binary_sha256"],
        "extractor_sha256": manifests[0]["extractor_sha256"],
        "original_manifest_sha256": protocol["manifest_sha256"],
        "blind_holdout": False, "promotion": False,
        "solver_errors": len(errors),
        "caveats": [
            "Previously studied REAL36 originals; not blind, no automatic promotion.",
            "OMEGA4.2 bridge emits no independently verified UNSAT proof.",
            "PAR2 lower is better; each solver has the same 8s end-to-end solve cap.",
            "Original SAT witnesses and native DRAT proofs checked independently.",
            "Omega source row extraction time counts in Omega component's runtime.",
            "Proof checking time reported separately from solver wall runtime.",
        ],
    }
    save_json("cross_final/report.json", report)
    lines = ["## DRNAS X5.9 + COOP5 / COOP5.1 + OMEGA4.2 vs Kissat / CaDiCaL",
             "", "36 original SAT2024 REAL36 CNFs × 2 repeats × 7 arms = 504 trials.",
             "One logical CPU per solver, 8s limit, fixed SHA binaries, deterministic shuffled order.",
             "**Not blind.** UNSAT for Omega bridge cannot be independently proof-certified.",
             "", "| Solver | Verified /72 | SAT | UNSAT proof | UNSAT unverified | Verified PAR2 (s) | Reported PAR2 (s) |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for arm, v in overall.items():
        lines.append(f"| {arm} | {v['verified']}/72 | {v['sat_verified']} | "
                     f"{v['unsat_certified']} | {v['unsat_unverified']} | "
                     f"{v['par2_verified_s']:.3f} | {v['par2_reported_s']:.3f} |")
    lines += ["", "### Paired family-bootstrap 95% CIs"]
    for k,v in comparisons.items():
        lines.append(f"- {k}: {100*v['relative_PAR2_gain']:+.3f}% "
                     f"(CI {[round(100*x,3) for x in v['family_bootstrap_95']]}%; families={len(families)})")
    lines += ["", f"Solver process/source errors: {len(errors)}; promotion: disabled.",
              "Result is retrospective development evidence only."]
    summary = "\n".join(lines) + "\n"
    Path("cross_final/summary.md").write_text(summary)
    print(summary, flush=True)
    print("CROSS_FINAL", json.dumps(report, sort_keys=True, separators=(",", ":")), flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fp:
            fp.write(summary)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("shard", "aggregate"))
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--cap", type=float, default=CAP)
    p.add_argument("--reps", type=int, default=REPS)
    args = p.parse_args()
    if args.command == "shard":
        shard_run(args.shard, args.cap, args.reps)
    else:
        aggregate()


if __name__ == "__main__":
    main()
