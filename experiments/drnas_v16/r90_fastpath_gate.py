#!/usr/bin/env python3
"""R90 predeclared early clean-solve gate vs unconditionally cooperative R88.

Development replay on the exact R88 2026-shard-2 original CNF cohort.
Never represent these already-observed samples as an unseen holdout.
The entire gate/preprocessing/solve path shares one 12 s wall-clock cap.
Every timeout contributes exactly 2*CAP to PAR-2 (no prep double penalty).
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, random, statistics, subprocess, tempfile, time
from pathlib import Path
import r88_cooperative as r88

CAP = 12.0
FAST_CAP = 0.040
REPS = 2
MODES = ("clean", "cooperative", "guarded")
PROTO = "DRNAS-R90-QUICK-SOLVE-GATE-40MS-DEV-20261104-v1"

def require(test, msg):
    if not test:
        raise RuntimeError("R90_FAIL_CLOSED " + str(msg))

def trial(mode, source, exe):
    start = time.monotonic()
    fast_exit = False
    prep_s = 0.0
    cause = 0
    lemmas = 0
    if mode == "clean":
        r = r88.solve(exe, source, source, CAP)
    else:
        if mode == "guarded":
            # Independent clean solve, not reuse of the separately measured baseline.
            # Includes process launch and UNSAT proof search within the time budget.
            early = r88.solve(exe, source, source, FAST_CAP)
            if early["answer"] != "TIMEOUT":
                fast_exit = True
                r = early
        if not fast_exit:
            prep_start = time.monotonic()
            n, clauses = r88.read_cnf(source)
            r88.fingerprint(n, clauses)  # Include original R88 feature extraction.
            extras, tele = r88.cooperative_learn(clauses)
            lemmas = len(extras)
            cause = tele["causal_cross_group_lemmas"]
            with tempfile.TemporaryDirectory() as d:
                amended = Path(d) / "augmented.cnf"
                r88.write_augmented(n, clauses, extras, amended)
                prep_s = time.monotonic() - prep_start
                remaining = CAP - (time.monotonic() - start)
                if remaining > 0:
                    r = r88.solve(exe, amended, source, remaining)
                else:
                    r = {"answer": "TIMEOUT", "witness_verified": False}
    elapsed = time.monotonic() - start
    answer = r["answer"] if elapsed <= CAP else "TIMEOUT"
    return dict(answer=answer,
                total_s=round(min(CAP, elapsed), 6),
                par2_s=round(2 * CAP if answer == "TIMEOUT" else elapsed, 6),
                prep_s=round(prep_s, 6),
                fast_exit=fast_exit,
                lemmas=lemmas,
                causal_cross_group_lemmas=cause,
                witness_verified=bool(r.get("witness_verified", False)) if answer == "SAT" else False)

def measure(args):
    srcdir = Path(args.sources).resolve()
    compiled = Path(args.compiled).resolve()
    manifest = json.loads((srcdir / "manifest.json").read_text())
    require(manifest["protocol"] == "DRNAS-R88-BULK-OFFICIAL-CNF-20261104-v1",
            "source protocol mismatch")
    require(int(manifest["year"]) == 2026 if "year" in manifest else
            all(int(c["year"]) == 2026 for c in manifest["cases"]), "not 2026 sources")
    exe = compiled / "clean"
    require(exe.is_file(), "pinned clean binary absent")
    require(subprocess.run(["sha256sum", "-c", "r87-binaries.sha256"],
            cwd=compiled, capture_output=True).returncode == 0, "pinned binary digest failed")
    os.chmod(exe, 0o755)
    if hasattr(os, "sched_getaffinity") and hasattr(os, "sched_setaffinity"):
        available = os.sched_getaffinity(0)
        os.sched_setaffinity(0, {min(available)})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in manifest["cases"]:
        source = srcdir / case["filename"]
        require(r88.sha(source) == case["sha256"], "original source SHA changed")
        for rep in range(REPS):
            modes = list(MODES)
            seed = hashlib.sha256((case["sha256"] + str(rep) + PROTO).encode()).hexdigest()
            random.Random(int(seed, 16)).shuffle(modes)
            for mode in modes:
                data = trial(mode, source, exe)
                expected = case.get("official_status", "UNKNOWN")
                if data["answer"] != "TIMEOUT" and expected in ("SAT", "UNSAT"):
                    require(data["answer"] == expected, "official answer mismatch")
                row = dict(source_id=case["gbd"], source_sha256=case["sha256"],
                           rep=rep, mode=mode, official_status=expected,
                           code_sha=os.environ.get("GITHUB_SHA", "local"),
                           baseline_run=41776279539, **data)
                rows.append(row)
                print("R90_TRIAL", json.dumps(row, sort_keys=True), flush=True)
        (out / "rows.json").write_text(json.dumps(rows, indent=2) + "\n")
    require(len(rows) == len(manifest["cases"]) * REPS * len(MODES),
            "paired attempt count mismatch")
    grouped = {m: [r for r in rows if r["mode"] == m] for m in MODES}
    summary = {}
    for mode, group in grouped.items():
        summary[mode] = dict(trials=len(group), solved=sum(
            r["answer"] in ("SAT", "UNSAT") for r in group),
            timeout=sum(r["answer"] == "TIMEOUT" for r in group),
            par2_s=round(sum(r["par2_s"] for r in group), 6),
            median_par2_s=round(statistics.median(r["par2_s"] for r in group), 6),
            quick_exits=sum(r["fast_exit"] for r in group),
            cumulative_preparation_s=round(sum(r["prep_s"] for r in group), 6))
    clean = summary["clean"]["par2_s"]
    for mode, values in summary.items():
        values["relative_clean_speedup_x"] = round(clean / values["par2_s"], 6) if values["par2_s"] else None
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (out / "paired.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    report = [
        "# DRNAS R90 quick-solve guard — development replay only",
        "",
        "Predeclared: clean 40 ms pilot, then sound R88 cooperation only if unsolved.",
        "Every mode is separately run; all preflight, feature, proof and solver costs",
        "are included inside one 12 s limit. Timed-out trials contribute PAR-2 = 24 s.",
        "Samples are **previously observed** R88 originals, NOT a new holdout.",
        "",
        "| Method | Solved / trials | PAR-2 (s) | Median PAR-2 (s) | vs clean | Fast exits | Prep sum (s) |",
        "|---|---:|---:|---:|---:|---:|---:|"
    ]
    for m in MODES:
        x = summary[m]
        report.append("| {} | {} / {} | {:.3f} | {:.3f} | {:.3f}x | {} | {:.3f} |".format(
            m, x["solved"], x["trials"], x["par2_s"], x["median_par2_s"],
            x["relative_clean_speedup_x"], x["quick_exits"], x["cumulative_preparation_s"]))
    report += ["", "Per-CNF paired values:", "",
        "| Source | Rep | Clean (s) | Cooperative (s) | Guarded (s) |",
        "|---|---:|---:|---:|---:|"]
    for case in manifest["cases"]:
        for rep in range(REPS):
            t = {r["mode"]: r for r in rows if r["source_id"] == case["gbd"] and r["rep"] == rep}
            report.append("| {} | {} | {:.4f} | {:.4f} | {:.4f} |".format(
                case["gbd"], rep, t["clean"]["par2_s"],
                t["cooperative"]["par2_s"], t["guarded"]["par2_s"]))
    report += ["", "No speedup claim until a separate SHA-disjoint blind cohort replicates it.",
               "R88 archived timings use a different timeout accounting (prep+2CAP);",
               "this study consistently applies 2CAP on timeouts and counts all",
               "actual costs within the same 12-second wall budget.", ""]
    (out / "R90_REPORT.md").write_text("\n".join(report))
    print("R90_PAIRED_AUDIT_PASS", json.dumps(summary, sort_keys=True), flush=True)

def selftest():
    require(0 < FAST_CAP < CAP, "invalid probe cap")
    r88.selftest()
    require(r88.bcp_conflict([(1,), (-1, 2), (-2,)], ()), "unsat sanity")
    print("R90_FASTPATH_SELFTEST_PASS")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    p = ap.add_subparsers(dest="cmd", required=True)
    p.add_parser("selftest")
    m = p.add_parser("measure")
    m.add_argument("--sources", required=True)
    m.add_argument("--compiled", required=True)
    m.add_argument("--out", required=True)
    args = ap.parse_args()
    selftest() if args.cmd == "selftest" else measure(args)
