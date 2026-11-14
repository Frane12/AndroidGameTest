#!/usr/bin/env python3
"""Retrospective single-core MATH-GUARD1 on previously solved REAL SAT2024 CNFs.

Cohort selection is based ONLY on older, proof/model-verified DELTA4 trials
having an independently recorded nonlinear-structure signal. The selected
sources are SHA-frozen; no TIMEOUT is rebranded as a solved source.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import signal
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
CAP = 10.0
REPS = 2
MAX_SOURCES = 12
OUT = ROOT / "mathguard1_real"
OLD = ROOT / "frozen/delta4_shards"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name, obj):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")


def emit(tag, obj):
    print(tag + " " + json.dumps(obj, sort_keys=True), flush=True)


def choose():
    manifest = json.loads((ROOT / "delta4_sources/manifest.json").read_text())
    sources = manifest["sources"]
    assert len(sources) == 60 and len({s["sha256"] for s in sources}) == 60
    seen = sorted(OLD.rglob("trials.jsonl"))
    if len(seen) != 12:
        raise RuntimeError(f"EXPECTED_ALL_12_FROZEN_DELTA4_SHARDS got={len(seen)}")
    old_rows = []
    for path in seen:
        old_rows.extend(json.loads(row) for row in path.read_text().splitlines())
    assert len(old_rows) == 840, ("INCOMPLETE_FROZEN_REFERENCE", len(old_rows))
    bysha = collections.defaultdict(list)
    for r in old_rows:
        bysha[r["sha256"]].append(r)
    chosen = []
    for s in sources:
        rows = bysha[s["sha256"]]
        assert len(rows) == 14, ("BAD_REFERENCE_PAIR_COUNT", s["id"], len(rows))
        # Nonlinear flags are structural telemetry, NOT proof of novel mathematics.
        nonlinear = max(
            max(int(r.get("stats", {}).get("DELTA2_JOIN", {}).get("nonlinear_tuple_events", 0)),
                int(r.get("stats", {}).get("DELTA2_JOIN", {}).get("d4_nonaffine_pairs", 0)))
            for r in rows)
        certified = [r for r in rows
                     if r.get("verified") and r.get("status") in
                     ("SAT_VERIFIED", "UNSAT_CERTIFIED") and
                     float(r.get("wall_e2e_s", CAP*5)) <= CAP]
        if not nonlinear or not certified:
            continue
        verdicts = {r["status"] for r in certified}
        assert len(verdicts) == 1, ("CONFLICTING_OLD_CERTIFICATES", s["sha256"])
        selected = dict(s)
        selected["old_verdict"] = next(iter(verdicts))
        selected["old_best_s"] = min(float(r["wall_e2e_s"]) for r in certified)
        selected["nonlinear_telemetry"] = nonlinear
        chosen.append(selected)
    chosen.sort(key=lambda r: (r["sha256"], r["id"]))
    return chosen[:MAX_SOURCES], len(chosen)


def check_sat(original, output):
    n = 0
    model = {}
    for line in output.splitlines():
        if line.startswith("v "):
            for entry in line.split()[1:]:
                lit = int(entry)
                if lit:
                    model[abs(lit)] = lit > 0
    with open(original, encoding="utf8", errors="replace") as inp:
        pending = []
        for line in inp:
            if line.startswith("c") or not line.strip() or line.startswith("%"):
                continue
            if line.startswith("p"):
                head = line.split()
                n = int(head[2])
                continue
            for tok in line.split():
                if tok in ("c", "%"):
                    break
                v = int(tok)
                if v == 0:
                    if not any(model.get(abs(l)) == (l > 0) for l in pending):
                        return False
                    pending = []
                else:
                    pending.append(v)
    return n > 0 and len(model) == n and not pending


def telemetry(stderr):
    found = [json.loads(line.split(" ", 1)[1])
             for line in stderr.splitlines() if line.startswith("MATH_GUARD_STATS ")]
    return found[0] if len(found) == 1 else {}


def trial(source, arm, rep):
    path = (ROOT / source["path"]).resolve()
    assert path.is_file() and sha(path) == source["sha256"]
    folder = OUT / "raw"
    folder.mkdir(exist_ok=True, parents=True)
    stem = f"{source['id']}-{rep}-{arm}"
    proof = folder / (stem + ".drat")
    usage = folder / (stem + ".usage")
    # Both measurements use the IDENTICAL binary: guard is a runtime toggle.
    executable = ROOT / "build/drnas-mathguard1"
    cmd = [str(executable), str(path), "--mode", "core",
           "--time", str(CAP-0.10), "--x5-no-minimize",
           "--stats", "--proof", str(proof)]
    if arm == "MATH_GUARD":
        cmd.extend(["--math-guard", "--math-guard-budget-ms", "4.0"])

    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (4*1024**3, 4*1024**3))
        resource.setrlimit(resource.RLIMIT_FSIZE, (128*1024**2, 128*1024**2))

    start = time.perf_counter()
    proc = subprocess.Popen(
        ["/usr/bin/time", "-f", "%U %S %M", "-o", str(usage), *cmd],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True, preexec_fn=limits)
    killed = False
    try:
        stdout, stderr = proc.communicate(timeout=CAP+0.10)
    except subprocess.TimeoutExpired:
        killed = True
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
    wall = time.perf_counter()-start
    (folder / (stem + ".stdout")).write_text(stdout)
    (folder / (stem + ".stderr")).write_text(stderr)
    status = "TIMEOUT" if killed else "UNKNOWN"
    check_s = 0
    if not killed and proc.returncode == 10:
        t = time.perf_counter()
        assert check_sat(path, stdout), ("INVALID_SAT_MODEL", stem)
        check_s = time.perf_counter() - t
        status = "SAT_VERIFIED"
    elif not killed and proc.returncode == 20:
        assert proof.exists() and proof.stat().st_size, ("MISSING_UNSAT_PROOF", stem)
        t = time.perf_counter()
        try:
            verified = subprocess.run(
                [str(ROOT / "build/drat-trim"), str(path), str(proof)],
                capture_output=True, text=True, timeout=30)
            if verified.returncode >= 0 and "s VERIFIED" in verified.stdout:
                status = "UNSAT_CERTIFIED"
            else:
                raise RuntimeError(("INVALID_UNSAT_PROOF", stem, verified.stdout[-1200:]))
        except subprocess.TimeoutExpired:
            status = "UNSAT_CHECK_TIMEOUT"
        check_s = time.perf_counter() - t
    elif not killed and proc.returncode not in (0, 153):
        raise RuntimeError(("SOLVER_ERROR", stem, proc.returncode, stderr[-900:]))
    cpu = None
    rss = None
    if usage.exists():
        fields = usage.read_text().split()
        if len(fields) == 3:
            cpu, rss = float(fields[0]) + float(fields[1]), int(fields[2])
    proof.unlink(missing_ok=True)
    stat = telemetry(stderr) if arm == "MATH_GUARD" else {}
    if arm == "MATH_GUARD":
        assert stat.get("enabled"), ("MISSING_MATH_GUARD_STATS", stem)
    accepted = status in ("SAT_VERIFIED", "UNSAT_CERTIFIED") and wall <= CAP
    row = {
        "sha256": source["sha256"], "family": source["family"],
        "id": source["id"], "rep": rep, "arm": arm,
        "status": status, "verified": accepted,
        "wall_e2e_s": wall, "cpu_s": cpu, "maxrss_kib": rss,
        "proof_check_s": check_s, "PAR2_verified_s": wall if accepted else 2*CAP,
        "math_guard": stat, "old_verdict": source["old_verdict"],
        "nonlinear_telemetry": source["nonlinear_telemetry"],
    }
    emit("MATH_GUARD_REAL_TRIAL", row)
    return row


def main():
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    selected, eligible = choose()
    write("cohort.json", {
        "criteria": "prior certificate within 10s plus DELTA4 nonlinear/nonaffine structural telemetry",
        "historical_run": 43589616448, "retrospective": True,
        "holdout": False, "promotion": False, "eligible": eligible,
        "selected": selected, "one_logical_cpu": True, "max_sources": MAX_SOURCES})
    rows = []
    for s in selected:
        for rep in range(REPS):
            arms = ["GUARD_OFF", "MATH_GUARD"]
            random.Random(int(s["sha256"][:16], 16)+rep*61).shuffle(arms)
            for arm in arms:
                rows.append(trial(s, arm, rep))
    write("trials.json", rows)
    by = {(r["sha256"], r["rep"], r["arm"]): r for r in rows}
    paired = []
    for s in selected:
        for rep in range(REPS):
            x = by[s["sha256"], rep, "GUARD_OFF"]
            y = by[s["sha256"], rep, "MATH_GUARD"]
            if x["verified"] and y["verified"]:
                assert x["status"] == y["status"], ("CONTRADICTORY_VERIFIED_VERDICT", s["sha256"])
                paired.append(x["wall_e2e_s"]/y["wall_e2e_s"])
    summary = {
        "eligible_prior_solved_with_structural_signal": eligible,
        "selected_sources": len(selected), "paired_trials": len(rows),
        "both_verified_pairs": len(paired),
        "median_speedup_when_both_verified": statistics.median(paired) if paired else None,
        "verified": {arm: sum(r["verified"] for r in rows if r["arm"] == arm)
                     for arm in ("GUARD_OFF", "MATH_GUARD")},
        "PAR2_verified_s": {arm: sum(r["PAR2_verified_s"] for r in rows if r["arm"] == arm)
                            for arm in ("GUARD_OFF", "MATH_GUARD")},
        "math_guard_lemmas": sum(r["math_guard"].get("lemmas", 0)
                                 for r in rows if r["arm"] == "MATH_GUARD"),
        "single_cpu": True, "retrospective": True,
        "holdout": False, "promotion": False,
        "speed_claim": bool(paired),
    }
    write("report.json", summary)
    emit("MATH_GUARD_REAL_FINAL", summary)


if __name__ == "__main__":
    main()
