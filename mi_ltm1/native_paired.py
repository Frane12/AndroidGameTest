"""MI-LTM1: actual paired native DRNAS CDCL A vs A + bounded XOR consequences.

All consequences are derived from COMPLETE CNF XOR encodings, and small
instances are independently checked by exhaustive original-CNF enumeration.
No UNSAT result is called LRAT certified. Pairing: same SHA, same seed, 1 CPU.
No persistent policy used yet: this evaluates whether the first intervention
has practical value, before adding learned routing.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import tempfile
import time

from bench_formulas import cases, dimacs, oracle, satisfies
from probe import probe_cnf

BIN = Path("mre_atlas15/bin/drnas_atlas15").resolve()
CAP = 3.0
REPS = 2


def implied_cnf(consequence):
    vars_ = consequence["variables"]
    rhs = consequence["rhs"]
    if not vars_:
        return [()] if rhs else []
    if len(vars_) == 1:
        return [(vars_[0] if rhs else -vars_[0],)]
    if len(vars_) == 2:
        a, b = vars_
        return [(-a, -b), (a, b)] if rhs else [(-a, b), (a, -b)]
    return []


def parse_model(output):
    assignments = {}
    for line in output.splitlines():
        if not line.startswith("v "):
            continue
        for token in line.split()[1:]:
            lit = int(token)
            if lit:
                if abs(lit) in assignments and assignments[abs(lit)] != (lit > 0):
                    raise AssertionError("Conflicting model literals")
                assignments[abs(lit)] = lit > 0
    return assignments


def solve(path, seed, cap):
    # Same CPU per trial; total E2E measured from caller, includes preprocessing.
    def limit():
        resource.setrlimit(resource.RLIMIT_CPU, (int(cap) + 2, int(cap) + 3))
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    cmd = [str(BIN), str(path), "--mode", "A", "--time", str(cap),
           "--seed", str(seed)]
    started = time.perf_counter()
    try:
        p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=cap+2,
                           preexec_fn=limit)
        rc, out = p.returncode, p.stdout
        if rc not in (0, 10, 20):
            raise RuntimeError("native CDCL rc=%s stderr=%s" % (rc, p.stderr[-1200:]))
    except subprocess.TimeoutExpired:
        rc, out = 0, ""
    return rc, out, time.perf_counter() - started


def run():
    if not BIN.exists():
        raise FileNotFoundError("Build native ATLAS15 first: " + str(BIN))
    trials = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for family, case_id, n, original in cases():
            raw = dimacs(original, n)
            sha = hashlib.sha256(raw.encode()).hexdigest()
            models = list(oracle(original, n))
            for rep in range(REPS):
                seed = int.from_bytes(hashlib.sha256(("%s/%d" % (sha, rep)).encode()).digest()[:8], "big")
                # Alternate order to limit run-order bias.
                order = ("BASE", "MI_XOR") if rep % 2 == 0 else ("MI_XOR", "BASE")
                paired = {}
                for arm in order:
                    begin = time.perf_counter()
                    extra = []
                    probe_s = 0.0
                    if arm == "MI_XOR":
                        probe = probe_cnf(raw)
                        probe_s = time.perf_counter() - begin
                        for cons in probe["consequences"]:
                            # Every implication must hold on all source models.
                            assert all(sum(model[x] for x in cons["variables"]) % 2 == cons["rhs"]
                                       for model in models), (family, case_id, cons)
                            extra.extend(implied_cnf(cons))
                        # Don't inject duplicate clauses.
                        original_set = set(original)
                        extra = list(dict.fromkeys(c for c in extra if c not in original_set))
                    work = original + extra
                    path = root / ("%s_%s_%d.cnf" % (family, arm, rep))
                    path.write_text(dimacs(work, n))
                    rc, out, child = solve(path, seed, CAP)
                    e2e = time.perf_counter() - begin
                    expected = 10 if models else 20
                    if rc not in (0, expected):
                        raise AssertionError(("SAT/UNSAT discrepancy", family, case_id, arm, rc, expected))
                    if rc == 10:
                        assignments = parse_model(out)
                        assert len(assignments) == n and satisfies(original, assignments)
                    solved = rc == expected
                    # Proof by exhaustive enumeration is used ONLY because n<=8.
                    item = {"family": family, "case": case_id, "sha256": sha, "rep": rep,
                            "arm": arm, "status": "SAT_ORACLE" if rc == 10 else
                            "UNSAT_ORACLE" if rc == 20 else "UNKNOWN",
                            "solved": solved, "e2e_s": round(e2e, 7),
                            "par2_s": round(e2e if solved else 2 * CAP, 7),
                            "probe_s": round(probe_s, 7),
                            "added_clauses": len(extra),
                            "one_cpu": True, "original_cnf_verified": True,
                            "independent_lrat": False}
                    paired[arm] = item
                    trials.append(item)
                    print("MI_LTM1_NATIVE_TRIAL " + json.dumps(item, sort_keys=True), flush=True)
    summary = {}
    for arm in ("BASE", "MI_XOR"):
        group = [x for x in trials if x["arm"] == arm]
        summary[arm] = {"trials": len(group), "solved": sum(x["solved"] for x in group),
                        "par2_total_s": round(sum(x["par2_s"] for x in group), 6),
                        "e2e_total_s": round(sum(x["e2e_s"] for x in group), 6),
                        "median_e2e_ms": round(statistics.median(x["e2e_s"] for x in group)*1000, 6),
                        "added_clauses": sum(x["added_clauses"] for x in group)}
    report = {"source": "32 deterministic 8-variable original CNF cases, 2 repeats, native ATLAS15 CDCL A",
              "formula_count": 32, "repeats": REPS, "cap_s": CAP,
              "note": "Small proof-of-concept cohort; UNSAT established only with exhaustive small-n oracle; not LRAT. MI includes Python probe overhead; no learning/policy arm yet.",
              "summary": summary, "trials": trials}
    Path("MI_LTM1_NATIVE_PAIRED.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    print("MI_LTM1_NATIVE_FINAL " + json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    run()
