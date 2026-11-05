#!/usr/bin/env python3
"""R26: causal restart-interval ablation on SHA-pinned R24 regression/control CNFs.

The four input identities are frozen from the R24 fresh manifest, before this
experiment's timings. No classifier is trained or evaluated as a blind holdout.
All arms share the same R24-instrumented Kissat binary and generated CNF bytes.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import time

UPSTREAM = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"
LIMIT = 2.0
REPEATS = 3
N = 220
M = round(4.23 * N)
CASES = {
    "r24_random3_test_00.cnf": (2426311300, "3ed04d48d2df5daee89bb186c7c77785b9424b6ea6ac41bb07c9afd0e40d8066"),
    "r24_random3_test_01.cnf": (2426311301, "bb6b60f3ffc55720e2f25582cbf65c390286a99001724b0e7dbe9af64005a3f4"),
    "r24_random3_test_02.cnf": (2426311302, "6a1f0542b0b5fba6a997fcb29801905dc99baa1b7c8ff737cd84670489e16341"),
    "r24_random3_test_05.cnf": (2426311305, "969e9ac420c270e0901b1eb2ab417ed170c5f0cafe4c6fc7ddc9cea191ed8f90"),
}
ARMS = {
    "monitor": "r5_monitor",
    "switch_2048_25": "r11_2048_25",
    "switch_2048_50": "r11_2048_50",
    "switch_4096_50": "r11_4096_50",
}

def freeze(out):
    inputs = out / "cnf"
    inputs.mkdir(parents=True, exist_ok=True)
    frozen = []
    clauses_by_name = {}
    for name, (seed, sha) in CASES.items():
        rng = random.Random(seed)
        clauses = []
        for _ in range(M):
            vs = rng.sample(range(1, N + 1), 3)
            clauses.append([v if rng.getrandbits(1) else -v for v in vs])
        raw = (f"p cnf {N} {M}\n" +
               "".join(" ".join(map(str, cl)) + " 0\n" for cl in clauses)).encode()
        observed = hashlib.sha256(raw).hexdigest()
        if observed != sha:
            raise RuntimeError(f"ORIGINAL_SHA_MISMATCH {name}: {observed} != {sha}")
        (inputs / name).write_bytes(raw)
        frozen.append({"file": name, "seed": seed, "sha256": sha, "vars": N, "clauses": M})
        clauses_by_name[name] = clauses
    manifest = {
        "source_kissat": UPSTREAM, "base": "R24 patch with only permitted late-50 mode added",
        "limit_s": LIMIT, "repeats": REPEATS,
        "inputs": frozen, "arms": ARMS,
        "method": "paired, order-shuffled modes; SHA-frozen original CNFs; same binary and CPU",
        "warnings": ["R24 fresh formulas were already examined: diagnostic not blind",
                     "2 s timeout means unsolved, not UNSAT",
                     "UNSAT is solver-reported, no independent proof certificate",
                     "The change at 2048 tests native restartint; no external solver restart"],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("R26_FROZEN", len(CASES), hashlib.sha256((out / "manifest.json").read_bytes()).hexdigest(), flush=True)
    return clauses_by_name

def extend_mode(kissat_root):
    p = kissat_root / "src" / "search.c"
    original = "(r11_at==4096 && r11_interval==25)"
    changed = "(r11_at==4096 && (r11_interval==25 || r11_interval==50))"
    data = p.read_text()
    if data.count(original) != 1:
        raise RuntimeError("R26_R11_LATE50_ANCHOR_MISMATCH")
    p.write_text(data.replace(original, changed, 1))
    print("R26_PATCH_OK one additional allowed restart mode; no policy or telemetry edits", flush=True)

def kv_trace(line):
    out = {}
    for k, v in re.findall(r"([A-Za-z_]+)=([0-9]+(?:\.[0-9]+)?)", line):
        try:
            out[k] = float(v) if "." in v else int(v)
        except ValueError:
            pass
    return out

def attempt(binary, path, clauses, name, arm, rep, out):
    env = os.environ.copy()
    env.update({
        "DRNAS_V177_MODE": ARMS[arm],
        "DRNAS_R13_N": str(N),
        "DRNAS_R12_DEGREE_CV": "0.28",
        "DRNAS_R16_GINI": "0.16",
        "DRNAS_R16_POLARITY": "0.22",
    })
    start = time.monotonic()
    try:
        proc = subprocess.run([str(binary), str(path)], capture_output=True,
                              text=True, errors="replace", env=env, timeout=LIMIT)
        elapsed = time.monotonic() - start
        text = proc.stdout + "\n" + proc.stderr
        if proc.returncode not in (10, 20):
            raise RuntimeError(f"BAD_SOLVER_EXIT {name}/{arm}/{rep} {proc.returncode}: {text[-200:]}")
        status = "SAT" if proc.returncode == 10 else "UNSAT"
        if status == "SAT":
            vals = [int(v) for line in proc.stdout.splitlines() if line.startswith("v ")
                    for v in line.split()[1:] if v != "0"]
            assignment = {abs(v): v > 0 for v in vals}
            if not vals or not all(any(abs(l) in assignment and assignment[abs(l)] == (l > 0)
                                       for l in cl) for cl in clauses):
                raise RuntimeError(f"SAT_WITNESS_INVALID {name}/{arm}/{rep}")
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start
        text = (exc.stdout or b"")
        if isinstance(text, bytes):
            text = text.decode(errors="replace")
        status = "TIMEOUT"
    trace_lines = [line for line in text.splitlines() if line.startswith(
        ("c R6_TRACE", "c R24_TRACE", "c DRNAS_V177_SWITCH", "c R5_EARLY"))]
    (out / "logs").mkdir(exist_ok=True)
    (out / "logs" / f"{name}.{arm}.{rep}.log").write_text("\n".join(trace_lines) + "\n")
    r6 = [kv_trace(s) for s in trace_lines if s.startswith("c R6_TRACE")]
    switch = [s for s in trace_lines if "DRNAS_V177_SWITCH" in s]
    return dict(formula=name, repeat=rep, arm=arm, status=status,
                seconds=round(elapsed, 6),
                par2=round(4.0 if status == "TIMEOUT" else elapsed, 6),
                switch_seen=bool(switch), snapshots=r6,
                pre_switch=[x for x in r6 if x.get("conflict", 999999) < 2048])

def summarize(rows, out):
    final = {}
    for name in CASES:
        sample = [r for r in rows if r["formula"] == name]
        by_arm = {}
        for arm in ARMS:
            trials = [r for r in sample if r["arm"] == arm]
            if len(trials) != REPEATS:
                raise RuntimeError("INCOMPLETE_TRIALS " + name + " " + arm)
            by_arm[arm] = {
                "median_par2_s": round(statistics.median(x["par2"] for x in trials), 6),
                "median_wall_s": round(statistics.median(x["seconds"] for x in trials), 6),
                "solved": sum(x["status"] != "TIMEOUT" for x in trials),
                "statuses": [x["status"] for x in trials],
                "switches": sum(x["switch_seen"] for x in trials),
                "last_snapshots": [x["snapshots"][-1] if x["snapshots"] else None for x in trials],
            }
        original = by_arm["monitor"]["median_par2_s"]
        for arm in ARMS:
            by_arm[arm]["relative_par2_vs_monitor"] = round(
                by_arm[arm]["median_par2_s"] / max(original, 1e-9), 5)
        # Pre-intervention checkpoints should match when the only active policy difference
        # is restartint at 2048/4096. Preserve mismatch instead of hiding it.
        expected = [x["pre_switch"] for x in sample if x["arm"] == "monitor"]
        other = {a: [x["pre_switch"] for x in sample if x["arm"] == a]
                 for a in ARMS if a != "monitor"}
        comparison = {}
        for arm, seq in other.items():
            # Trial order is randomized, sort by repeat before comparing.
            d0 = {x["repeat"]: x["pre_switch"] for x in sample if x["arm"] == "monitor"}
            d1 = {x["repeat"]: x["pre_switch"] for x in sample if x["arm"] == arm}
            comparison[arm] = all(d0[k] == d1[k] for k in range(REPEATS))
        final[name] = {"arms": by_arm, "pre_2048_equal": comparison}
        print("R26_RESULT", name, json.dumps(final[name], sort_keys=True), flush=True)
    (out / "summary.json").write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
    with (out / "trials.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["formula", "repeat", "arm", "status", "seconds", "par2", "switch_seen"])
        for x in rows:
            w.writerow([x[k] for k in ("formula", "repeat", "arm", "status", "seconds", "par2", "switch_seen")])
    md = ["# DRNAS R26 — targeted restart interval causal ablation",
          "R24 fresh CNFs were previously examined; this is **diagnostic**, not a new blind holdout.",
          "Same native instrumented Kissat, SHA-pinned inputs, randomized execution order, three repeats, 2 s cap.",
          "", "| Formula | monitor | 2048→25 | 2048→50 | 4096→50 |",
          "|---|---:|---:|---:|---:|"]
    for name, val in final.items():
        ss = [val["arms"][x]["median_par2_s"] for x in ARMS]
        md.append(f"| {name} | " + " | ".join(f"{x:.4f}" for x in ss) + " |")
    md.extend(["", "Times are medians of PAR-2 seconds; TIMEOUT is scored 4 s.",
               "See summary.json for switch markers and pre-2048 checkpoint equality.",
               "Intervention timing and solver mechanism require further independent holdout confirmation."])
    (out / "report.md").write_text("\n".join(md) + "\n")
    print("R26_AUDIT_PASS", len(rows), "trials", len(final), "formulas", flush=True)

def run(binary, out):
    if hasattr(os, "sched_getaffinity"):
        cpus = os.sched_getaffinity(0)
        os.sched_setaffinity(0, {min(cpus)})
    out.mkdir(parents=True, exist_ok=True)
    clauses = freeze(out)
    binary = binary.resolve()
    results = []
    for name in CASES:
        path = (out / "cnf" / name).resolve()
        for rep in range(REPEATS):
            modes = list(ARMS)
            random.Random(26031103 + CASES[name][0] + rep).shuffle(modes)
            for arm in modes:
                row = attempt(binary, path, clauses[name], name, arm, rep, out)
                results.append(row)
                (out / "partial.json").write_text(json.dumps(results, indent=2) + "\n")
                print("R26_TRIAL", name, rep, arm, row["status"], row["seconds"],
                      "switch", int(row["switch_seen"]), flush=True)
    for name in CASES:
        statuses = {r["status"] for r in results if r["formula"] == name} - {"TIMEOUT"}
        if len(statuses) > 1:
            raise RuntimeError("INCONSISTENT_SAT_UNSAT " + name)
    summarize(results, out)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="action", required=True)
    x = sub.add_parser("patch")
    x.add_argument("--kissat-root", type=Path, required=True)
    x = sub.add_parser("run")
    x.add_argument("--binary", type=Path, required=True)
    x.add_argument("--outdir", type=Path, required=True)
    a = p.parse_args()
    if a.action == "patch":
        extend_mode(a.kissat_root)
    else:
        run(a.binary, a.outdir)
