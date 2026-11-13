#!/usr/bin/env python3
"""Oracle, exact-trajectory and CPU-sampling checks for the observational clone."""
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "build/drnas-x5"
PROFILE = ROOT / "build/drnas-x5-profile"
CHECKER = ROOT / "build/drat-trim"
FROZEN_SHA = "9768340a8bed3bac3e43f0fb29780c4d5165c50283f90eae141733a7b76106fc"
PHASES = {"other", "parse", "bcp", "bcp_empty", "analyze", "minimize", "reduce", "proof", "select"}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def pigeonhole(pigeons, holes):
    var = lambda p, h: p * holes + h + 1
    clauses = [[var(p, h) for h in range(holes)] for p in range(pigeons)]
    clauses += [[-var(a, h), -var(b, h)] for h in range(holes)
                for a in range(pigeons) for b in range(a + 1, pigeons)]
    return pigeons * holes, clauses


def brute(n, clauses):
    return any(all(any(values[abs(lit) - 1] == (lit > 0) for lit in clause) for clause in clauses)
               for values in itertools.product((False, True), repeat=n))


def model_ok(text, clauses):
    values = {}
    for line in text.splitlines():
        if line.startswith("v "):
            for word in line[2:].split():
                lit = int(word)
                if lit:
                    require(abs(lit) not in values or values[abs(lit)] == (lit > 0), "Contradictory model")
                    values[abs(lit)] = lit > 0
    return all(any(values.get(abs(lit)) == (lit > 0) for lit in clause) for clause in clauses)


def records(stderr, prefix):
    return [json.loads(line[len(prefix):]) for line in stderr.splitlines() if line.startswith(prefix)]


def check_profile(value, enabled):
    require(value["enabled"] == enabled and value["complete"], "Incorrect final profiler state")
    require(value["cpu_s"] >= value["profiled_cpu_s"] >= 0, "Invalid CPU interval")
    require(value["samples_total"] == sum(value["phase_samples"].values()), "Sample partition mismatch")
    require(set(value["phase_samples"]) == set(value["phase_cpu_estimate_s"]) == PHASES, "Phase schema mismatch")
    require(not value["sample_overflow"], "Sample counters overflowed")
    if value["samples_total"]:
        estimates = value["phase_cpu_estimate_s"]
        require(all(math.isfinite(v) and v >= 0 for v in estimates.values()), "Invalid estimated CPU")
        require(math.isclose(sum(estimates.values()), value["profiled_cpu_s"], abs_tol=2e-8),
                "Exclusive estimates do not partition observed CPU")
        require(math.isclose(value["analyze_inclusive_cpu_estimate_s"], estimates["analyze"] + estimates["minimize"], abs_tol=2e-9),
                "Nested minimization double-counted or lost")
    else:
        require(all(v is None for v in value["phase_cpu_estimate_s"].values()), "Missing samples reported as zero work")
    if not enabled:
        require(value["samples_total"] == 0 and value["profiled_cpu_s"] == 0, "Disabled profiler sampled CPU")


def solve(binary, cnf, proof, minimize, enabled=None, seconds=0):
    command = [str(binary), str(cnf), "--mode", "core", "--stats", "--time", str(seconds)]
    if proof is not None:
        command += ["--proof", str(proof)]
    if not minimize:
        command.append("--x5-no-minimize")
    if enabled:
        command.append("--x5-profile")
    proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
    require(proc.returncode in (0, 10, 20), ("Solver error", command, proc.returncode, proc.stderr[-1500:]))
    native = records(proc.stderr, "X41_STATS ")
    x5 = records(proc.stderr, "X5_STATS ")
    require(len(native) == len(x5) == 1, "Missing canonical search statistics")
    trajectory = {k: v for k, v in native[0].items() if k not in ("elapsed_s", "probe_seconds")}
    final = records(proc.stderr, "X5_PROFILE ")
    if enabled is not None:
        require(len(final) == 1, "Missing or duplicate final profile")
        check_profile(final[0], enabled)
        require(final[0]["status"] == native[0]["status"], "Profile status disagrees with native status")
        for key in ("conflicts", "decisions", "propagations", "learnt", "restarts", "reduce_removed"):
            require(final[0]["counters"][key] == native[0][key], "Counter mismatch: " + key)
        for key in ("minimized_literals", "minimize_visits"):
            require(final[0]["counters"][key] == x5[0][key], "Counter mismatch: " + key)
    else:
        require(not final, "Frozen baseline unexpectedly emits new profile")
    return proc, trajectory, x5[0], final[0] if final else None


def verify_proof(cnf, proof):
    checked = subprocess.run([str(CHECKER), str(cnf), str(proof)], capture_output=True, text=True, timeout=20)
    require("s VERIFIED" in checked.stdout and (checked.returncode == 0 or "c trivial UNSAT" in checked.stdout),
            ("Independent DRAT verification failed", checked.returncode, checked.stdout[-1000:], checked.stderr[-1000:]))


def main():
    require(hashlib.sha256((ROOT / "src/drnas_x5.cpp").read_bytes()).hexdigest() == FROZEN_SHA,
            "Frozen baseline source changed")
    cases = [("empty_sat", 0, []), ("empty_unsat", 0, [[]]),
             ("unit_sat", 2, [[1], [-1, 2]]), ("unit_unsat", 1, [[1], [-1]]),
             ("binary_unsat", 2, [[1, 2], [1, -2], [-1, 2], [-1, -2]]),
             ("tautology", 3, [[1, -1], [2, 2], [-2, 3]])]
    rng = random.Random(550014)
    for index in range(18):
        n = 3 + index % 5
        clauses = []
        for _ in range(4 * n + index % 5):
            literals = rng.sample(range(1, n + 1), min(n, 1 + rng.randrange(3)))
            clauses.append([v if rng.getrandbits(1) else -v for v in literals])
        cases.append((f"oracle_{index}", n, clauses))
    n, clauses = pigeonhole(7, 6)
    cases.append(("php_7_6", n, clauses))
    checked_runs = checked_proofs = 0
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        for name, n, clauses in cases:
            cnf = td / (name + ".cnf")
            cnf.write_text(f"p cnf {n} {len(clauses)}\n" + "".join(" ".join(map(str, clause)) + " 0\n" for clause in clauses))
            # The larger pigeonhole case has a direct mathematical UNSAT oracle.
            expected = (10 if brute(n, clauses) else 20) if n <= 7 else 20
            for minimize in (False, True):
                baseline_proof = td / "base.drat"
                base, base_stats, base_x5, _ = solve(BASE, cnf, baseline_proof, minimize)
                require(base.returncode == expected, ("Baseline disagrees with oracle", name))
                proof_bytes = baseline_proof.read_bytes()
                if expected == 10:
                    require(model_ok(base.stdout, clauses), "Invalid baseline model")
                else:
                    verify_proof(cnf, baseline_proof)
                    checked_proofs += 1
                checked_runs += 1
                for enabled, with_proof in ((False, True), (True, True), (True, False)):
                    proof = td / "clone.drat" if with_proof else None
                    clone, stats, x5, profile = solve(PROFILE, cnf, proof, minimize, enabled)
                    require(clone.returncode == base.returncode and clone.stdout == base.stdout,
                            ("Status/model trajectory drift", name, minimize, enabled, with_proof))
                    require(stats == base_stats and x5 == base_x5, ("Search trajectory drift", name, minimize, enabled, with_proof))
                    if with_proof:
                        require(proof.read_bytes() == proof_bytes, ("Learned proof transcript changed", name, minimize, enabled))
                        if expected == 20:
                            verify_proof(cnf, proof)
                            checked_proofs += 1
                    if enabled:
                        require(profile["counters"]["proof_flushes"] == int(with_proof), "Proof flush accounting mismatch")
                        require(with_proof or profile["phase_calls"]["proof"] == 0, "Proof-disabled arm has proof work")
                        require(minimize or profile["phase_calls"]["minimize"] == 0, "Disabled minimization has work")
                    checked_runs += 1
        n, clauses = pigeonhole(13, 12)
        stress = td / "cpu_stress.cnf"
        stress.write_text(f"p cnf {n} {len(clauses)}\n" + "".join(" ".join(map(str, clause)) + " 0\n" for clause in clauses))
        proc, _, _, final = solve(PROFILE, stress, td / "stress.drat", False, True, seconds=1.2)
        require(proc.returncode == 0 and final["status"] == "UNKNOWN", "Stress did not stop naturally at native deadline")
        require(final["cpu_s"] > 0.02 and final["samples_total"] > 0, "CPU stress did not deliver SIGPROF samples")
        progress = records(proc.stderr, "X5_PROFILE_PROGRESS ")
        require(progress and progress[0]["status"] == "START", "Missing initial diagnostic snapshot")
        require(any(row["elapsed_s"] >= 1.0 for row in progress), "Missing periodic timeout progress")
        for left, right in zip(progress, progress[1:] + [final]):
            require(right["elapsed_s"] >= left["elapsed_s"] and right["samples_total"] >= left["samples_total"], "Nonmonotonic snapshots")
            require(all(right["phase_samples"][key] >= left["phase_samples"][key] for key in PHASES), "Nonmonotonic phase samples")
        checked_runs += 1
    result = {"status": "PASS", "cases": len(cases), "solver_runs": checked_runs,
              "independent_drat_checks": checked_proofs, "exact_status_model_proof_search_stats": True,
              "profile_off_on_and_minimize_off_on": True, "proof_off_trajectory": True,
              "native_timeout_progress": True, "cpu_sample_partition": True,
              "stress_samples": final["samples_total"], "stress_cpu_s": final["cpu_s"]}
    (ROOT / "build/test_x5_profile_result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("X5_PROFILE_SELFTEST_PASS " + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
