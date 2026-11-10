#!/usr/bin/env python3
"""Independent Python tests for DRNAS's ORIGINAL self-contained C++ CDCL.
Never invokes Kissat, CaDiCaL, CMS, or any non-DRNAS solver.
Small UNSAT verified by exhaustive truth-table enumeration; large UNSAT is
recorded as unverified, not as an independently certified achievement.
"""
import argparse
import hashlib
import json
import os
import pathlib
import random
import re
import subprocess
import tempfile
import time

ROOT = pathlib.Path("mre_drnas_native_core_r1")
BIN = ROOT / "bin/drnas_native_core_r1"
def need(ok, msg):
    if not ok:
        raise RuntimeError("DRNAS_NATIVE_R1_TEST_FAIL_CLOSED " + msg)
def read_dimacs(path):
    tokens = []
    variables = None
    count = None
    for line in pathlib.Path(path).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("c"):
            continue
        if line.lstrip().startswith("p"):
            parts = line.split()
            need(len(parts) == 4 and parts[1] == "cnf", "bad DIMACS header")
            variables, count = int(parts[2]), int(parts[3])
        else:
            tokens.extend(map(int, line.split()))
    need(variables is not None and count is not None, "no header")
    clauses, cur = [], []
    for lit in tokens:
        if lit == 0:
            clauses.append(cur)
            cur = []
        else:
            need(abs(lit) <= variables, "out of range input")
            cur.append(lit)
    need(not cur and len(clauses) == count, "original CNF count invalid")
    return variables, clauses
def holds(clauses, assignment):
    return all(any((assignment.get(abs(lit)) == (lit > 0)) for lit in clause)
               for clause in clauses)
def brute(n, clauses):
    need(n <= 13, "brute force limited to 13 variables")
    for mask in range(1 << n):
        assign = {v: bool(mask & (1 << (v - 1))) for v in range(1, n + 1)}
        if holds(clauses, assign):
            return True
    return False
def cnf_text(n, clauses):
    lines = ["c native DRNAS test original", f"p cnf {n} {len(clauses)}"]
    for c in clauses:
        lines.append(" ".join(map(str, c)) + (" " if c else "") + "0")
    return "\n".join(lines) + "\n"
def trial(path, seconds):
    begin = time.perf_counter()
    r = subprocess.run([str(BIN.resolve()), str(pathlib.Path(path).resolve()),
                        "--time", str(seconds)], capture_output=True,
                        text=True, timeout=seconds + 3)
    elapsed = time.perf_counter() - begin
    need(r.returncode in (0, 10, 20),
         "unexpected solver exit "+str(r.returncode)+" stderr="+r.stderr[-600:])
    match = re.search(r"^c DRNAS_NATIVE_R1_RESULT (.+)$", r.stdout, re.M)
    need(match is not None, "no DRNAS source-native result")
    metrics = {}
    for field in match.group(1).split():
        if "=" in field:
            k, v = field.split("=", 1)
            metrics[k] = v
    status = metrics["status"]
    need(status in ("SAT", "UNSAT", "UNKNOWN"), "unknown status")
    need(r.returncode == {"SAT": 10, "UNSAT": 20, "UNKNOWN": 0}[status],
         "status/exit mismatch")
    need(metrics.get("third_party_solver_calls") == "0",
         "foreign solver dependency detected")
    need(metrics.get("UNSAT_independent_LRAT") == "0",
         "unproven UNSAT must not be described as certified")
    n, clauses = read_dimacs(path)
    assign = {}
    if status == "SAT":
        for line in r.stdout.splitlines():
            if line.startswith("v "):
                for literal in map(int, line[2:].split()):
                    if literal:
                        need(abs(literal) not in assign, "duplicate model var")
                        assign[abs(literal)] = (literal > 0)
        need(len(assign) == n and holds(clauses, assign),
             "SAT does NOT satisfy original CNF")
    need(elapsed <= seconds + 1.2, "time limit overrun")
    return dict(status=status, process_E2E_s=round(elapsed, 6),
                solver_s=float(metrics["solver_s"]),
                e2e_solver_native_s=float(metrics["e2e_s"]),
                decisions=int(metrics["decisions"]),
                conflicts=int(metrics["conflicts"]),
                learned=int(metrics["learned"]),
                restarts=int(metrics["restarts"]),
                third_party_solver_calls=0)
def fuzz():
    ROOT.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([str(BIN.resolve()), "--selftest"],
                       capture_output=True, text=True, timeout=45)
    need(r.returncode == 0 and
         "DRNAS_NATIVE_R1_SELFTEST_PASS " in r.stdout,
         "C++ exhaustive selftest failed: " + r.stderr[-800:])
    print(r.stdout.strip(), flush=True)
    rng = random.Random(0xD2A5A7)
    solved_sat, solved_unsat, nontrivial = 0, 0, 0
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        for i in range(560):
            n = rng.randint(1, 10)
            k = rng.randrange(0, 5 * n + 10)
            clauses = []
            for _ in range(k):
                width = rng.randrange(0, min(9, n + 4))
                clause = [rng.choice((-1, 1)) * rng.randint(1, n)
                          for _ in range(width)]
                clauses.append(clause)
            original = pathlib.Path(td) / "random.cnf"
            original.write_text(cnf_text(n, clauses))
            expected = brute(n, clauses)
            out = trial(original, 1.5)
            need(out["status"] == ("SAT" if expected else "UNSAT"),
                 f"independent brute mismatch testcase={i} vars={n} clauses={k}")
            solved_sat += expected
            solved_unsat += not expected
            nontrivial += bool(out["conflicts"])
            if i % 140 == 0:
                print("DRNAS_NATIVE_R1_FUZZ_PROGRESS "
                      +json.dumps(dict(case=i,unsat=solved_unsat,
                                       cases_with_conflicts=nontrivial)), flush=True)
    need(solved_sat and solved_unsat and nontrivial,
         "fuzz did not exercise SAT, UNSAT and conflict learning")
    print("DRNAS_NATIVE_R1_FUZZ_PASS "
          +json.dumps(dict(cases=560,independent_truth_tables=560,
                           SAT=solved_sat,UNSAT=solved_unsat,
                           cases_with_conflicts=nontrivial)),flush=True)
def originals():
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(pathlib.Path("mre_mixab4/manifest.json").read_text())
    cases = manifest["original_cases"]
    need(len(cases) == 6, "expected MIXAB4 six reference easy original inputs")
    outcomes = []
    for case in sorted(cases, key=lambda x: x["sha256"]):
        original = pathlib.Path("mre_mixab4/cases") / case["filename"]
        need(original.is_file(), "missing original frozen CNF")
        need(hashlib.sha256(original.read_bytes()).hexdigest() == case["sha256"],
             "original SHA mismatch")
        for rep in range(2):
            out = trial(original, 3.0)
            out.update(sha256=case["sha256"], rep=rep, cap_s=3.0,
                       original_sha_checked=True,
                       UNSAT_independent_LRAT=False,
                       source_selection="previously_reference_easy_not_blind")
            outcomes.append(out)
            print("DRNAS_NATIVE_R1_ORIGINAL_TRIAL "+json.dumps(out,sort_keys=True),
                  flush=True)
            (ROOT/"original-trials.json").write_text(
                json.dumps(outcomes,indent=2,sort_keys=True)+"\n")
    need(len(outcomes) == 12, "missing original SHA attempts")
    print("DRNAS_NATIVE_R1_ORIGINAL_PASS "+json.dumps(dict(
          trials=12,source_sha=6,
          SAT_original_verified=sum(t["status"]=="SAT" for t in outcomes),
          raw_UNSAT_no_independent_proof=sum(t["status"]=="UNSAT" for t in outcomes),
          timeout=sum(t["status"]=="UNKNOWN" for t in outcomes),
          one_logical_CPU=True,backend_solver_dependencies=0)),flush=True)
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode",choices=("fuzz","original"))
    a = p.parse_args()
    if a.mode == "fuzz": fuzz()
    else: originals()
