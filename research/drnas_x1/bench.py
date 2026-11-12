#!/usr/bin/env python3
"""Paired X1 benchmark. Reference executables are competitors, never X1 backends.

Solver timing includes parsing, preprocessing, proof generation and model output.
Independent checking is timed separately AND included in the e2e PAR2 metric.
Only independently certified answers receive verified PAR2 credit.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import check

HERE = Path(__file__).resolve().parent
ARMS = ("X1_CORE", "X1_AUTO", "Kissat", "CaDiCaL")


def emit(tag, obj):
    print(tag + " " + json.dumps(obj, sort_keys=True, separators=(",", ":")), flush=True)


def limits():
    resource.setrlimit(resource.RLIMIT_AS, (2*1024**3, 2*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8*1024**2, 8*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def command(arm, binary, path, proof, cap, seed):
    if arm.startswith("X1_"):
        mode = {"X1_CORE": "core", "X1_AUTO": "auto", "X1_FACTOR": "factor"}[arm]
        return [str(binary), "--mode", mode, "--seconds", str(max(.01, cap-.03)),
                "--seed", str(seed), "--proof", str(proof), str(path)]
    if arm == "Kissat":
        return ["kissat", "-q", f"--seed={seed}", "--no-binary", str(path), str(proof)]
    if arm == "CaDiCaL":
        return ["cadical", "-q", f"--seed={seed}", "--no-binary", str(path), str(proof)]
    raise ValueError(arm)


def independent(source, output, proof, drat, allowance=3.0):
    started = time.monotonic()
    text = output.read_text(errors="replace")
    if "s UNSATISFIABLE" in text and drat and proof.exists():
        with proof.open("rb") as f:
            factor = f.read(32).startswith(b"c X1_FACTOR_V1")
        if not factor:
            try:
                p = subprocess.run([drat, str(source), str(proof)], capture_output=True, text=True,
                                   timeout=allowance, preexec_fn=limits)
                okay = p.returncode == 0 and "s VERIFIED" in p.stdout.splitlines()
                return {"verified": okay, "kind": "DRAT_TRIM", "check_s": time.monotonic()-started}
            except subprocess.TimeoutExpired:
                return {"verified": False, "kind": "CHECK_TIMEOUT", "check_s": time.monotonic()-started}
    try:
        p = subprocess.run([sys.executable, "-S", str(HERE/"check.py"), str(source), str(output),
                            "--proof", str(proof), "--seconds", str(max(.01, allowance-.05))],
                           capture_output=True, text=True, timeout=allowance, preexec_fn=limits)
        result = json.loads(p.stdout)
        result["check_s"] = time.monotonic()-started
        return result
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return {"verified": False, "kind": "CHECK_TIMEOUT_OR_ERROR", "check_s": time.monotonic()-started}


def run_trial(arm, binary, source, cap, seed, drat):
    with tempfile.TemporaryDirectory(prefix="x1-trial-") as td:
        root = Path(td)
        proof, output, error = root/"proof", root/"stdout", root/"stderr"
        args = command(arm, binary, source, proof, cap, seed)
        start = time.monotonic()
        timeout = False
        with output.open("w") as out, error.open("w") as err:
            try:
                p = subprocess.run(args, stdout=out, stderr=err, timeout=cap, preexec_fn=limits)
                code = p.returncode
            except subprocess.TimeoutExpired:
                timeout, code = True, -9
        solve_s = time.monotonic()-start
        text = output.read_text(errors="replace")
        status = "TIMEOUT" if timeout else "UNKNOWN"
        if not timeout and code == 10 and "s SATISFIABLE" in text.splitlines():
            status = "SAT"
        elif not timeout and code == 20 and "s UNSATISFIABLE" in text.splitlines():
            status = "UNSAT"
        elif not timeout and code not in (0, 10, 20):
            status = "RESOURCE_LIMIT" if code == -25 or (proof.exists() and proof.stat().st_size >= 8*1024**2) else "ERROR"
        certified = {"verified": False, "kind": "NOT_SOLVED", "check_s": 0.0}
        if status in ("SAT", "UNSAT"):
            certified = independent(source, output, proof, drat)
        e2e = solve_s + certified["check_s"]
        verified = bool(certified["verified"])
        stats = {}
        for line in text.splitlines():
            if line.startswith("c X1_STATS "):
                stats = json.loads(line[len("c X1_STATS "):])
        if arm.startswith("X1_") and stats and stats.get("external_solver_calls") != 0:
            raise RuntimeError("native provenance audit failed")
        row = {"arm": arm, "status": status, "returncode": code, "cap_s": cap,
               "seed": seed, "verified": verified, "verified_within_cap": verified and e2e <= cap,
               "solve_s": round(solve_s, 6), "check_s": round(certified["check_s"], 6),
               "e2e_s": round(e2e, 6), "verification": certified["kind"],
               "PAR2_verified_solver_s": round(solve_s if verified and solve_s <= cap else 2*cap, 6),
               "PAR2_verified_e2e_s": round(e2e if verified and e2e <= cap else 2*cap, 6),
               "PAR2_reported_s": round(solve_s if status in ("SAT", "UNSAT") and solve_s <= cap else 2*cap, 6),
               "proof_bytes": proof.stat().st_size if proof.exists() else 0, "stats": stats}
        if status == "ERROR":
            row["error_excerpt"] = error.read_text(errors="replace")[-1000:] + text[-1000:]
        return row


def aggregate(rows):
    output = {}
    for arm in sorted({r["arm"] for r in rows}):
        part = [r for r in rows if r["arm"] == arm]
        output[arm] = {"trials": len(part), "solved_verified": sum(r["verified"] for r in part),
                       "solved_verified_e2e_cap": sum(r["verified_within_cap"] for r in part),
                       "SAT_verified": sum(r["verified"] and r["status"] == "SAT" for r in part),
                       "UNSAT_verified": sum(r["verified"] and r["status"] == "UNSAT" for r in part),
                       "errors": sum(r["status"] == "ERROR" for r in part),
                       **{key: round(sum(r[key] for r in part), 6) for key in
                          ("solve_s", "check_s", "e2e_s", "PAR2_verified_solver_s", "PAR2_verified_e2e_s", "PAR2_reported_s")}}
    return output


def parity_pair(length, unsat):
    # Two parity chains over the SAME free inputs. Different final parities conflict.
    clauses = [[length+1], [2*length+2]]
    for i in range(length):
        b = i+1
        for offset in (length+1, 2*length+2):
            vs = (offset+i, b, offset+i+1)
            for a in range(8):
                if a.bit_count() % 2:
                    clauses.append([-v if (a>>j)&1 else v for j, v in enumerate(vs)])
    clauses.extend([[2*length+1], [-(3*length+2) if unsat else 3*length+2]])
    return 3*length+2, clauses


def write_cnf(path, n, clauses):
    path.write_text(f"p cnf {n} {len(clauses)}\n" + "".join(" ".join(map(str, c))+" 0\n" for c in clauses))


def synthetic(root):
    result = []
    for size in (6, 12, 24, 48, 96):
        for unsat in (False, True):
            n, clauses = parity_pair(size, unsat)
            path = root/f"parity-pair-{size}-{unsat}.cnf"
            write_cnf(path, n, clauses)
            result.append({"id": len(result), "path": str(path), "nvars": n, "cap_s": 3.0,
                           "family": "diagnostic_parity_pair", "expected": "UNSAT" if unsat else "SAT"})
    return result


def official(root):
    # Source acquisition only. No B.run_solver, B.command or legacy solver binary.
    sys.path.insert(0, str(HERE.parent))
    import drnas_ltm11_real2 as archive
    archive.ROOT = root/"archive"
    sources = archive.collect()
    for item in sources:
        item["nvars"] = archive.nvars(item["path"])
        item["family"] = item["normalized_name_family"]
    sources.sort(key=lambda s: (s["nvars"], s["bytes"], s["sha256"]))
    for i, item in enumerate(sources):
        item["cap_s"] = 3.0 if i < 50 else 5.0
    return sources


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, default=Path("build/drnas-x1"))
    ap.add_argument("--suite", choices=("official100", "synthetic", "smoke"), default="synthetic")
    ap.add_argument("--native-only", action="store_true")
    ap.add_argument("--out", type=Path, default=Path("x1_results"))
    args = ap.parse_args()
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    args.out.mkdir(parents=True, exist_ok=False)
    binary = args.binary.resolve()
    arms = ("X1_CORE", "X1_AUTO", "X1_FACTOR") if args.native_only else ARMS
    drat = shutil.which("drat-trim")
    if not args.native_only:
        for exe in ("kissat", "cadical", "drat-trim"):
            if not shutil.which(exe):
                raise RuntimeError(f"missing benchmark dependency: {exe}")
    sources = official(args.out) if args.suite == "official100" else synthetic(args.out)
    if args.suite == "smoke":
        sources = sources[:2]
    manifest = []
    for s in sources:
        p = Path(s["path"])
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if s.get("sha256", digest) != digest:
            raise RuntimeError("original source hash mismatch")
        s["sha256"] = digest
        manifest.append(dict(s))
    if len({s["sha256"] for s in sources}) != len(sources):
        raise RuntimeError("duplicate sources")
    (args.out/"manifest.json").write_text(json.dumps({"suite": args.suite, "sources": manifest,
        "arms": arms, "repeats": 1, "globally_blind": False, "trained_on_outcomes": False,
        "selection_uses_solver_results": False, "one_logical_cpu": True,
        "proof_generation": "ON for every arm; 8 MiB per-file limit",
        "primary_metric": "PAR2_verified_e2e_s; independent checking included",
        "secondary_metric": "PAR2_verified_solver_s; certification outside solver timing"}, indent=2)+"\n")
    rows = []
    with (args.out/"trials.jsonl").open("w") as log:
        for i, s in enumerate(sources):
            offset = i % len(arms)
            for arm in arms[offset:]+arms[:offset]:
                if hashlib.sha256(Path(s["path"]).read_bytes()).hexdigest() != s["sha256"]:
                    raise RuntimeError("original source changed")
                row = run_trial(arm, binary, Path(s["path"]), s["cap_s"], 17, drat)
                row.update(id=s["id"], family=s["family"], source_sha256=s["sha256"], nvars=s["nvars"])
                rows.append(row)
                log.write(json.dumps(row, sort_keys=True)+"\n"); log.flush()
                emit("X1_TRIAL", row)
                if row["status"] == "ERROR":
                    raise RuntimeError(f"solver/configuration error: {row}")
                if s.get("expected") and row["status"] in ("SAT", "UNSAT") and row["status"] != s["expected"]:
                    raise RuntimeError("contradiction with constructed ground truth")
                if args.suite == "smoke" and not row["verified"]:
                    raise RuntimeError("solver/independent-check smoke failed")
            verified = {r["status"] for r in rows if r["id"] == s["id"] and r["verified"]}
            if len(verified) > 1:
                raise RuntimeError("verified SAT/UNSAT contradiction")
            emit("X1_PROGRESS", {"completed": i+1, "total": len(sources), "totals": aggregate(rows)})
    totals = aggregate(rows)
    comparisons = {}
    paired = {(r["id"], r["arm"]): r for r in rows}
    for arm in arms:
        base = totals["X1_CORE"]["PAR2_verified_e2e_s"]
        score = totals[arm]["PAR2_verified_e2e_s"]
        comparisons[arm] = {"speedup_vs_X1_CORE_x": base/max(score, 1e-12),
            "regressions_over_10pct_vs_CORE": sum(r["PAR2_verified_e2e_s"] >
                1.1*paired[(r["id"], "X1_CORE")]["PAR2_verified_e2e_s"]+.002 for r in rows if r["arm"] == arm)}
    report = {"suite": args.suite, "source_count": len(sources), "trials": len(rows), "totals": totals,
              "comparisons": comparisons, "groups": {str(cap): aggregate([r for r in rows if r["cap_s"] == cap])
                  for cap in sorted({r["cap_s"] for r in rows})}, "globally_blind": False,
              "reference_solvers_are_external_competitors_only": True}
    (args.out/"report.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    lines = ["## DRNAS X1 — "+args.suite, "", "Native X1 has no external solver backend. Proof-on, one CPU, one repeat.", "",
             "| Arm | Certified | Total solve s | PAR2 solver s | PAR2 e2e s |", "|---|---:|---:|---:|---:|"]
    for arm, r in totals.items():
        lines.append(f"| {arm} | {r['solved_verified']}/{r['trials']} | {r['solve_s']:.4f} | {r['PAR2_verified_solver_s']:.4f} | {r['PAR2_verified_e2e_s']:.4f} |")
    text = "\n".join(lines)+"\n"
    (args.out/"summary.md").write_text(text)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(text)
    emit("X1_FINAL", report)


if __name__ == "__main__":
    main()
